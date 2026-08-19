"""Voice-activity detection and speech-to-text for the realtime voice session.

Both models run locally and are lazy-loaded once per process: importing them at
module scope would make every backend start pay for a model load even when
nobody uses voice, and would break the app entirely when the optional
dependencies are absent.

Neither of these is a language model. Whisper transcribes audio and Silero
detects speech; DeepSeek remains the only LLM, and every transcript still goes
through the governed agent.

Silero runs on onnxruntime directly rather than through its PyTorch wrapper.
The wrapper only ever used torch to carry arrays into onnxruntime and back, so
this is the same arithmetic without loading the largest dependency in the
project to act as a container.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
import os
import io
import ssl
import tempfile
import wave

import httpx
import truststore
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

_vad_session = None
_vad_load_error: str | None = None
# Serialises the first load. Two sockets opening together both reach for
# the model at once, and importing onnxruntime and numpy concurrently is
# what produced a bare "import numpy failed" in production.
_vad_lock = threading.Lock()

# Silero conditions each frame on the last 64 samples of the previous one, so
# the tensor it actually scores is 576 wide. Omitting this does not fail -- it
# quietly returns different, worse probabilities.
VAD_CONTEXT_SAMPLES = 64
# Shape of Silero's recurrent state: (2, batch, 128).
VAD_STATE_SHAPE = (2, 1, 128)


def _vad_model_path():
    """Locate the ONNX model inside the installed silero-vad package.

    ``find_spec`` reads the package's location without executing it, which is
    the point: importing ``silero_vad`` pulls in PyTorch, and PyTorch is the
    single largest thing this process would ever load.
    """

    from pathlib import Path

    spec = importlib.util.find_spec("silero_vad")
    if spec is None or not spec.submodule_search_locations:
        raise FileNotFoundError("the silero-vad package is not installed")
    root = Path(list(spec.submodule_search_locations)[0])
    # The 'half' variant is fp16 and not what the reference wrapper uses.
    models = sorted(p for p in root.rglob("*.onnx") if "half" not in p.name)
    if not models:
        raise FileNotFoundError(f"no ONNX model found under {root}")
    return models[0]


def load_vad():
    """Open the shared ONNX session once per process.

    Silero ships as an ONNX graph, and the library's own wrapper runs it
    through onnxruntime -- it uses PyTorch only to hold arrays on the way in
    and out, calling ``.numpy()`` before every inference. Going straight to
    onnxruntime with numpy is the same arithmetic (verified bit-identical)
    without a ~200 MB dependency loaded to act as a container.

    The session is shared because it is stateless. The recurrent state that is
    *not* stateless lives in ``SileroVad``, one per conversation.
    """

    global _vad_session, _vad_load_error
    if _vad_session is not None:
        return _vad_session
    if _vad_load_error is not None:
        raise VoiceModelUnavailable(_vad_load_error)

    with _vad_lock:
        # Another caller may have finished while this one waited.
        if _vad_session is not None:
            return _vad_session
        try:
            import onnxruntime

            options = onnxruntime.SessionOptions()
            # One thread each: frames are tiny and arrive continuously, so
            # thread pool coordination costs more than the inference it
            # parallelises.
            options.inter_op_num_threads = 1
            options.intra_op_num_threads = 1
            _vad_session = onnxruntime.InferenceSession(
                str(_vad_model_path()),
                providers=["CPUExecutionProvider"],
                sess_options=options,
            )
            return _vad_session
        except Exception as exc:  # noqa: BLE001 - surfaced as a health error
            message = (
                "Silero VAD could not be loaded. Install the 'silero-vad' "
                f"package to enable voice mode ({exc.__class__.__name__})."
            )
            # Only a missing package is permanent. Anything else -- an import
            # race, a transient file lock -- may succeed next time, and
            # remembering it disabled voice for the life of the process. That
            # is exactly what happened: one "import numpy failed" during
            # start-up left the capability endpoint reporting no voice
            # detection until the server was restarted.
            if importlib.util.find_spec("silero_vad") is None:
                _vad_load_error = message
            else:
                logger.warning(
                    "Silero VAD load failed and will be retried: %s", exc
                )
            raise VoiceModelUnavailable(message) from exc


def vad_available() -> bool:
    """Whether Silero can be loaded, without paying to load it here."""

    if _vad_session is not None:
        return True
    if _vad_load_error is not None:
        return False
    return importlib.util.find_spec("silero_vad") is not None


class SileroVad:
    """One conversation's voice-activity detector.

    Silero is recurrent: each frame's score depends on the state left by the
    frames before it. That state was previously held on the single shared model
    object, so two simultaneous voice sessions would have interleaved their
    audio through one detector and corrupted each other's utterance
    boundaries. It belongs to the session, so it lives here.
    """

    def __init__(self, session=None) -> None:
        self._session = session or load_vad()
        self.reset()

    def reset(self) -> None:
        """Forget the conversation so far. Used between utterances."""

        import numpy as np

        self._state = np.zeros(VAD_STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros((1, VAD_CONTEXT_SAMPLES), dtype=np.float32)

    def probabilities(self, frames: list[bytes]) -> list[float]:
        """Score consecutive frames in one call.

        The socket used to hand each 32 ms frame to a worker thread on its own
        -- roughly thirty thread hops a second, whose scheduling overhead
        dwarfed the inference. Scoring a whole socket message at once keeps the
        audio path ahead of the speaker. The frames must stay in order: the
        state carried between them is the whole point.
        """

        return [self.probability(frame) for frame in frames]

    def probability(self, frame: bytes) -> float:
        """Probability that one 512-sample frame contains speech."""

        import numpy as np

        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size != VAD_FRAME_SAMPLES:
            padded = np.zeros(VAD_FRAME_SAMPLES, dtype=np.float32)
            padded[: min(samples.size, VAD_FRAME_SAMPLES)] = samples[:VAD_FRAME_SAMPLES]
            samples = padded

        window = np.concatenate([self._context, samples.reshape(1, -1)], axis=1)
        output, self._state = self._session.run(
            None,
            {
                "input": window,
                "state": self._state,
                "sr": np.array(settings.voice_sample_rate, dtype=np.int64),
            },
        )
        self._context = window[..., -VAD_CONTEXT_SAMPLES:]
        return float(output[0][0])


def speech_probabilities(frames: list[bytes], *, detector: SileroVad | None = None) -> list[float]:
    """Score frames with a throwaway detector.

    Convenience for tests and one-shot scoring only. A live session must hold
    its own :class:`SileroVad`, or every batch starts from a blank state.
    """

    return (detector or SileroVad()).probabilities(frames)


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
    """Can this deployment transcribe, judged without loading anything.

    The health endpoint used to answer this by loading Whisper, which
    downloaded the model and allocated it just to say "yes" -- the behaviour
    that exhausted memory on a small instance. Groq needs only a key, and the
    local engine only needs its package present, which ``find_spec`` answers
    without importing it.
    """

    if settings.voice_stt_provider == "groq":
        return settings.groq_configured
    return importlib.util.find_spec("faster_whisper") is not None


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


# Whisper emits these verbatim over silence and background noise. They are
# training-data residue from subtitled video, not anything the user said.
_HALLUCINATIONS = frozenset(
    {
        "thank you.", "thanks for watching!", "thank you for watching.",
        "bye.", "bye bye.", "you", "okay.", "so.", ".", "!", "?",
        "subtitles by the amara.org community", "amara.org",
        "please subscribe.", "thanks for watching.", "mbc 뉴스 이덕영입니다.",
    }
)


def _clean_transcript(segments) -> str:
    """Keep confident speech, drop what Whisper narrated over silence."""

    kept: list[str] = []
    for segment in segments:
        text = (getattr(segment, "text", "") or "").strip()
        if not text:
            continue
        # faster-whisper reports these per segment; a segment can clear the
        # global thresholds and still be a confident-sounding invention.
        no_speech = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
        avg_logprob = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
        if no_speech >= settings.whisper_no_speech_threshold:
            continue
        if avg_logprob < settings.whisper_logprob_threshold:
            continue
        if text.lower().strip() in _HALLUCINATIONS:
            continue
        kept.append(text)
    return " ".join(kept).strip()


def pcm_to_wav_bytes(pcm: bytes, *, sample_rate: int | None = None) -> bytes:
    """Wrap raw PCM in a WAV container in memory, for upload."""

    rate = sample_rate or settings.voice_sample_rate
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(BYTES_PER_SAMPLE)
        output.setframerate(rate)
        output.writeframes(pcm)
    return buffer.getvalue()


def transcribe_with_groq(pcm: bytes, *, sample_rate: int | None = None) -> str:
    """Transcribe through Groq's hosted Whisper. Loads no model locally.

    This is what lets voice mode run on a small instance: the utterance is a
    few seconds of 16 kHz mono, so the upload is tiny and nothing is held in
    memory afterwards.

    Errors are deliberately generic. The key is never echoed, and neither is
    the provider body, which can quote request content.
    """

    if not settings.groq_configured:
        raise VoiceModelUnavailable(
            "Hosted speech recognition is selected but GROQ_API_KEY is not set."
        )

    audio = pcm_to_wav_bytes(pcm, sample_rate=sample_rate)
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        with httpx.Client(
            timeout=settings.groq_stt_timeout_seconds, verify=ssl_context
        ) as client:
            response = client.post(
                f"{settings.groq_base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files={"file": ("utterance.wav", audio, "audio/wav")},
                data={
                    "model": settings.groq_stt_model,
                    # Pinning the language stops a short clip being detected as
                    # the wrong one and returned as an invented translation.
                    **({"language": settings.voice_language} if settings.voice_language else {}),
                    "response_format": "json",
                    "temperature": "0",
                },
            )
    except httpx.HTTPError as exc:
        raise VoiceModelUnavailable(
            f"Could not reach the speech recognition service ({exc.__class__.__name__})."
        ) from exc

    if response.status_code == 401:
        # Settings are read once at import, so a key rotated after the server
        # started is still the old one in memory. That has been the cause every
        # time this fired, so say it rather than leaving it to be rediscovered.
        raise VoiceModelUnavailable(
            "The speech recognition key was rejected. If you just changed "
            "GROQ_API_KEY, restart the backend -- it still holds the previous "
            "key from when it started."
        )
    if response.status_code == 429:
        raise VoiceModelUnavailable(
            "Speech recognition is rate limited right now. Try again shortly."
        )
    if response.is_error:
        # Status only -- the body can echo request content.
        logger.warning("Groq transcription failed with HTTP %s", response.status_code)
        raise VoiceModelUnavailable(
            f"Speech recognition failed (HTTP {response.status_code})."
        )

    text = str((response.json() or {}).get("text") or "").strip()
    # The same phantom phrases Whisper produces locally over silence.
    return "" if text.lower() in _HALLUCINATIONS else text


def transcribe_pcm(pcm: bytes, *, sample_rate: int | None = None, model=None) -> str:
    """Transcribe 16-bit mono PCM. Blocking -- call it off the event loop."""

    rate = sample_rate or settings.voice_sample_rate
    duration_ms = len(pcm) / BYTES_PER_SAMPLE / rate * 1000
    if duration_ms < MIN_UTTERANCE_MS:
        # Too short to be a question; never send this to the agent.
        return ""

    # An explicit model always wins, so tests and the local engine keep working
    # regardless of which provider is configured.
    if model is None and settings.voice_stt_provider == "groq":
        return transcribe_with_groq(pcm, sample_rate=rate)

    engine = model or load_whisper()
    # Hand Whisper the samples directly rather than a file path. Passing a path
    # makes faster-whisper decode it with PyAV, which adds a temporary file, a
    # decode step and a native dependency -- one that is blocked outright by
    # Application Control on this machine. The audio is already the mono float
    # PCM the model wants, so none of that is needed.
    import numpy as np

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = engine.transcribe(
        samples,
        # Greedy decoding mishears; a small beam is much more accurate and
        # costs little on a few seconds of audio.
        beam_size=settings.whisper_beam_size,
        # Auto-detection on a short clip picks the wrong language and then
        # invents a "translation". Pin it unless explicitly left blank.
        language=settings.voice_language or None,
        # Whisper narrates silence with confident phantom text -- "Thank
        # you.", subtitle credits -- so let it drop non-speech itself.
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        # Each utterance is independent; carrying context across turns is
        # what produces repetition loops.
        condition_on_previous_text=False,
        no_speech_threshold=settings.whisper_no_speech_threshold,
        log_prob_threshold=settings.whisper_logprob_threshold,
    )
    return _clean_transcript(segments)


__all__ = [
    "MIN_UTTERANCE_MS",
    "VAD_CONTEXT_SAMPLES",
    "VAD_FRAME_BYTES",
    "VAD_FRAME_SAMPLES",
    "VAD_SPEECH_THRESHOLD",
    "SileroVad",
    "UtteranceDetector",
    "VoiceModelUnavailable",
    "load_vad",
    "load_whisper",
    "pcm_to_wav_file",
    "speech_probabilities",
    "stt_available",
    "pcm_to_wav_bytes",
    "transcribe_pcm",
    "transcribe_with_groq",
    "vad_available",
]
