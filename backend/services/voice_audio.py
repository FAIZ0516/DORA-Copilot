"""Voice-activity detection and speech-to-text for the realtime voice session.

Both models run locally and are lazy-loaded once per process: importing them at
module scope would make every backend start pay for a model load even when
nobody uses voice, and would break the app entirely when the optional
dependencies are absent.

Neither of these is a language model. Whisper transcribes audio and Silero
detects speech; DeepSeek remains the only LLM, and every transcript still goes
through the governed agent.
"""

from __future__ import annotations

import logging
import os
import tempfile
import wave
from dataclasses import dataclass, field

from ..config import settings

logger = logging.getLogger(__name__)

# 16-bit mono PCM at the configured rate is what the browser worklet sends and
# what both models expect.
BYTES_PER_SAMPLE = 2
# Silero operates on fixed 512-sample frames at 16 kHz.
VAD_FRAME_SAMPLES = 512
VAD_FRAME_BYTES = VAD_FRAME_SAMPLES * BYTES_PER_SAMPLE
# Above this the frame is speech. Silero is well behaved around 0.5; lower
# values start treating keyboard noise as speech.
VAD_SPEECH_THRESHOLD = 0.5
# An utterance shorter than this is a cough, a click or a door -- never a
# question. Dropping it here is what stops empty turns reaching the agent.
MIN_UTTERANCE_MS = 250


class VoiceModelUnavailable(RuntimeError):
    """A local voice model is not installed or could not be loaded."""


# --------------------------------------------------------------------------- #
# Voice activity detection                                                    #
# --------------------------------------------------------------------------- #

_vad_model = None
_vad_load_error: str | None = None


def load_vad():
    """Load Silero once per process, remembering failure so we retry cheaply."""

    global _vad_model, _vad_load_error
    if _vad_model is not None:
        return _vad_model
    if _vad_load_error is not None:
        raise VoiceModelUnavailable(_vad_load_error)
    try:
        from silero_vad import load_silero_vad

        _vad_model = load_silero_vad(onnx=True)
        return _vad_model
    except Exception as exc:  # noqa: BLE001 - surfaced as a health error
        _vad_load_error = (
            "Silero VAD could not be loaded. Install the 'silero-vad' package "
            f"to enable voice mode ({exc.__class__.__name__})."
        )
        logger.warning("Silero VAD unavailable: %s", exc)
        raise VoiceModelUnavailable(_vad_load_error) from exc


def vad_available() -> bool:
    try:
        load_vad()
    except VoiceModelUnavailable:
        return False
    return True


def speech_probability(frame: bytes, *, model=None) -> float:
    """Probability that one 512-sample frame contains speech."""

    import numpy as np
    import torch

    model = model or load_vad()
    samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size != VAD_FRAME_SAMPLES:
        padded = np.zeros(VAD_FRAME_SAMPLES, dtype=np.float32)
        padded[: min(samples.size, VAD_FRAME_SAMPLES)] = samples[:VAD_FRAME_SAMPLES]
        samples = padded
    return float(model(torch.from_numpy(samples), settings.voice_sample_rate).item())


@dataclass
class UtteranceDetector:
    """Turns a stream of PCM frames into utterance start and end events.

    Deliberately a plain state machine over probabilities rather than anything
    clever: it has to be testable without loading a model, which is why
    ``feed`` takes the probability and the model call happens outside.
    """

    sample_rate: int = field(default_factory=lambda: settings.voice_sample_rate)
    end_silence_ms: int = field(default_factory=lambda: settings.voice_end_silence_ms)
    max_utterance_seconds: int = field(default_factory=lambda: settings.voice_max_utterance_seconds)
    speaking: bool = False
    _speech_ms: float = 0.0
    _silence_ms: float = 0.0
    _utterance_ms: float = 0.0

    # Speech has to persist briefly before it counts, so a single noisy frame
    # cannot interrupt the assistant.
    start_speech_ms: float = 96.0

    def frame_ms(self) -> float:
        return VAD_FRAME_SAMPLES / self.sample_rate * 1000.0

    def feed(self, probability: float) -> str | None:
        """Advance the detector. Returns 'start', 'end', 'timeout' or None."""

        step = self.frame_ms()
        is_speech = probability >= VAD_SPEECH_THRESHOLD

        if not self.speaking:
            self._speech_ms = self._speech_ms + step if is_speech else 0.0
            if self._speech_ms >= self.start_speech_ms:
                self.speaking = True
                self._silence_ms = 0.0
                self._utterance_ms = self._speech_ms
                self._speech_ms = 0.0
                return "start"
            return None

        self._utterance_ms += step
        if self._utterance_ms >= self.max_utterance_seconds * 1000:
            self.reset()
            return "timeout"
        if is_speech:
            self._silence_ms = 0.0
            return None
        self._silence_ms += step
        if self._silence_ms >= self.end_silence_ms:
            self.reset()
            return "end"
        return None

    def reset(self) -> None:
        self.speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._utterance_ms = 0.0


# --------------------------------------------------------------------------- #
# Speech to text                                                              #
# --------------------------------------------------------------------------- #

_whisper_model = None
_whisper_load_error: str | None = None


def load_whisper():
    """Load faster-whisper once per process."""

    global _whisper_model, _whisper_load_error
    if _whisper_model is not None:
        return _whisper_model
    if _whisper_load_error is not None:
        raise VoiceModelUnavailable(_whisper_load_error)
    try:
        # The model is fetched from the Hugging Face hub on first use, and this
        # environment terminates TLS at a corporate proxy whose root is in the
        # Windows trust store but not in certifi -- the same reason llm.py and
        # tts.py build truststore SSL contexts. Those are per-client, so they do
        # not help a download made inside the hub library; injecting into the
        # stdlib makes every client here use the OS trust store.
        import truststore

        truststore.inject_into_ssl()

        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        return _whisper_model
    except Exception as exc:  # noqa: BLE001 - surfaced as a health error
        _whisper_load_error = (
            "Local speech recognition is unavailable. Install 'faster-whisper' "
            f"and ensure the '{settings.whisper_model}' model can load "
            f"({exc.__class__.__name__})."
        )
        logger.warning("faster-whisper unavailable: %s", exc)
        raise VoiceModelUnavailable(_whisper_load_error) from exc


def stt_available() -> bool:
    try:
        load_whisper()
    except VoiceModelUnavailable:
        return False
    return True


def pcm_to_wav_file(pcm: bytes, *, sample_rate: int | None = None) -> str:
    """Write PCM to a private temporary WAV file and return its path.

    ``mkstemp`` gives a unique, non-guessable name owned by this process -- a
    fixed shared filename would let concurrent sessions overwrite each other.
    The caller is responsible for deleting it.
    """

    rate = sample_rate or settings.voice_sample_rate
    handle, path = tempfile.mkstemp(prefix="zara-voice-", suffix=".wav")
    os.close(handle)
    with wave.open(path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(BYTES_PER_SAMPLE)
        output.setframerate(rate)
        output.writeframes(pcm)
    return path


def transcribe_pcm(pcm: bytes, *, sample_rate: int | None = None, model=None) -> str:
    """Transcribe 16-bit mono PCM. Blocking -- call it off the event loop."""

    rate = sample_rate or settings.voice_sample_rate
    duration_ms = len(pcm) / BYTES_PER_SAMPLE / rate * 1000
    if duration_ms < MIN_UTTERANCE_MS:
        # Too short to be a question; never send this to the agent.
        return ""

    engine = model or load_whisper()
    path = pcm_to_wav_file(pcm, sample_rate=rate)
    try:
        segments, _info = engine.transcribe(path, beam_size=1, vad_filter=False)
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        # Always remove it, including when transcription raised.
        try:
            os.unlink(path)
        except OSError:  # pragma: no cover - best effort cleanup
            logger.debug("Could not remove temporary audio file %s", path)


__all__ = [
    "MIN_UTTERANCE_MS",
    "VAD_FRAME_BYTES",
    "VAD_FRAME_SAMPLES",
    "VAD_SPEECH_THRESHOLD",
    "UtteranceDetector",
    "VoiceModelUnavailable",
    "load_vad",
    "load_whisper",
    "pcm_to_wav_file",
    "speech_probability",
    "stt_available",
    "transcribe_pcm",
    "vad_available",
]
