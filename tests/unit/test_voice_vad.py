"""Voice-activity detection: WebRTC, and what it must not drag in with it.

The neural detector was replaced because a 512 MB Render instance was killed
with exit status 137 the moment a voice socket opened and the model
initialised. So these tests are as much about what is *absent* -- torch,
onnxruntime, silero, faster-whisper -- as about the detection itself.
"""

import math
import struct

import pytest

from backend.config import settings
from backend.services.voice_audio import (
    VAD_FRAME_BYTES,
    VAD_FRAME_MS,
    VAD_FRAME_SAMPLES,
    VAD_SPEECH_THRESHOLD,
    UtteranceDetector,
    VoiceModelUnavailable,
    WebRtcVad,
    speech_probabilities,
    vad_available,
)


def _pcm(kind: str, *, frames: int = 1, ms: int = VAD_FRAME_MS) -> bytes:
    """PCM the detector will read as speech or as silence."""

    rate = settings.voice_sample_rate
    count = rate * ms // 1000
    out = bytearray()
    for _ in range(frames):
        if kind == "silence":
            samples = [0] * count
        else:
            # A voiced tone with harmonics: WebRTC keys on periodicity and
            # band energy, so a pure sine is not a reliable stand-in.
            samples = [
                int(
                    9000 * math.sin(2 * math.pi * 200 * i / rate)
                    + 4000 * math.sin(2 * math.pi * 400 * i / rate)
                    + 2500 * math.sin(2 * math.pi * 800 * i / rate)
                )
                for i in range(count)
            ]
        out += struct.pack("<%dh" % count, *(max(-32768, min(32767, s)) for s in samples))
    return bytes(out)


# --------------------------------------------------------------------------- #
# Frame geometry                                                              #
# --------------------------------------------------------------------------- #


def test_the_frame_is_a_size_webrtc_actually_accepts():
    """WebRTC takes 10, 20 or 30 ms and rejects everything else.

    Silero's 512 samples is not one of them, which is why the socket reframes
    the stream rather than scoring what the browser happens to send.
    """

    assert VAD_FRAME_MS in (10, 20, 30)
    assert VAD_FRAME_SAMPLES == settings.voice_sample_rate * VAD_FRAME_MS // 1000
    assert VAD_FRAME_BYTES == VAD_FRAME_SAMPLES * 2
    assert VAD_FRAME_SAMPLES != 512, "512 samples is Silero's frame, not WebRTC's"


def test_the_detector_accepts_a_real_frame_of_that_size():
    assert WebRtcVad().probability(_pcm("silence")) in (0.0, 1.0)


# --------------------------------------------------------------------------- #
# Classification                                                              #
# --------------------------------------------------------------------------- #


def test_silence_is_not_speech():
    assert WebRtcVad(aggressiveness=2).probability(_pcm("silence")) == 0.0


def test_a_voiced_tone_is_speech():
    assert WebRtcVad(aggressiveness=2).probability(_pcm("voice")) == 1.0


def test_the_answer_is_reported_as_a_probability():
    """WebRTC says yes or no; the state machine above reads probabilities.

    Mapping to 1.0 and 0.0 keeps UtteranceDetector testable without any
    detector at all, which is why it was left expecting a float.
    """

    detector = WebRtcVad(aggressiveness=2)
    for kind in ("silence", "voice"):
        value = detector.probability(_pcm(kind))
        assert value in (0.0, 1.0)
        assert (value >= VAD_SPEECH_THRESHOLD) is (kind == "voice")


def test_frames_are_scored_in_order_in_one_call():
    spoken = WebRtcVad(aggressiveness=2).probabilities(
        [_pcm("silence"), _pcm("voice"), _pcm("voice")]
    )
    assert spoken == [0.0, 1.0, 1.0]


def test_speech_is_held_briefly_after_it_stops():
    """WebRTC has a hangover of a few frames, and that is wanted here.

    Measured at roughly 150 ms. It cannot shorten an utterance, only extend
    it slightly, so a trailing syllable is never clipped -- and 150 ms is well
    inside the 700 ms of silence that ends a turn, so it does not delay the
    answer. The cost is a little extra trailing audio sent to transcription.
    """

    detector = WebRtcVad(aggressiveness=2)
    detector.probabilities([_pcm("voice")] * 2)
    tail = [detector.probability(_pcm("silence")) for _ in range(10)]
    assert tail[0] == 1.0, "expected hangover immediately after speech"
    assert tail[-1] == 0.0, "hangover must not last indefinitely"
    assert sum(tail) <= 6, f"hangover ran {sum(tail)} frames"


def test_a_mis_sized_frame_is_padded_rather_than_raising():
    """A wrong size means a caller bug; dropping the audio would be worse.

    WebRTC raises on anything but an exact frame, and an exception here would
    take the whole socket down mid-conversation.
    """

    detector = WebRtcVad(aggressiveness=2)
    assert detector.probability(_pcm("voice")[: VAD_FRAME_BYTES // 2]) in (0.0, 1.0)
    assert detector.probability(_pcm("voice") * 2) in (0.0, 1.0)


def test_each_conversation_scores_its_own_audio():
    """WebRTC carries an adaptive noise estimate, so it is not shared."""

    speech = [_pcm("voice") for _ in range(6)]
    alone = WebRtcVad(aggressiveness=2)
    expected = alone.probabilities(speech)

    first, second = WebRtcVad(aggressiveness=2), WebRtcVad(aggressiveness=2)
    interleaved = []
    for frame in speech:
        interleaved.append(first.probability(frame))
        second.probability(_pcm("silence"))  # the other conversation, quiet
    assert interleaved == expected


def test_resetting_between_turns_is_safe():
    """Kept so callers need not know which detector they hold."""

    detector = WebRtcVad(aggressiveness=2)
    detector.probabilities([_pcm("voice")] * 3)
    detector.reset()
    assert detector.probability(_pcm("voice")) == 1.0


def test_the_convenience_helper_still_scores_a_batch():
    assert speech_probabilities([_pcm("silence")]) == [0.0]


# --------------------------------------------------------------------------- #
# The state machine on top is unchanged                                       #
# --------------------------------------------------------------------------- #


def test_speech_and_silence_drive_utterance_start_and_end():
    """Start, then end after the configured silence. Unchanged by the swap."""

    detector = UtteranceDetector()
    frame_ms = detector.frame_ms()
    assert frame_ms == pytest.approx(VAD_FRAME_MS)

    started = None
    for _ in range(int(detector.start_speech_ms / frame_ms) + 1):
        started = detector.feed(1.0) or started
    assert started == "start"
    assert detector.speaking is True

    ended = None
    for _ in range(int(settings.voice_end_silence_ms / frame_ms) + 1):
        ended = detector.feed(0.0) or ended
    assert ended == "end"
    assert detector.speaking is False


def test_a_single_noisy_frame_cannot_start_an_utterance():
    """Speech has to persist, or a door closing becomes a question."""

    detector = UtteranceDetector()
    assert detector.feed(1.0) is None


def test_barge_in_needs_far_more_speech_than_a_normal_start():
    """While the assistant is audible its own voice can reach the microphone."""

    barge = UtteranceDetector(start_speech_ms=float(settings.voice_barge_in_ms))
    normal = UtteranceDetector()

    for _ in range(int(normal.start_speech_ms / normal.frame_ms()) + 1):
        normal.feed(1.0)
    assert normal.speaking is True

    for _ in range(3):
        assert barge.feed(1.0) is None

    needed = int(settings.voice_barge_in_ms / barge.frame_ms()) + 1
    assert any(barge.feed(1.0) == "start" for _ in range(needed))


# --------------------------------------------------------------------------- #
# Availability                                                                #
# --------------------------------------------------------------------------- #


def test_availability_is_answered_without_importing_anything():
    """The capability endpoint must not allocate a detector to answer."""

    import inspect

    from backend.services import voice_audio

    body = inspect.getsource(voice_audio.vad_available)
    assert "find_spec" in body
    assert "import webrtcvad" not in body
    assert vad_available() is True


def test_a_missing_package_is_reported_with_something_to_do(monkeypatch):
    import backend.services.voice_audio as voice_audio

    error = voice_audio._vad_load_error
    find_spec = voice_audio.importlib.util.find_spec
    try:
        voice_audio._vad_load_error = None
        voice_audio.importlib.util.find_spec = lambda name: None
        monkeypatch.setitem(__import__("sys").modules, "webrtcvad", None)

        with pytest.raises(VoiceModelUnavailable) as failure:
            voice_audio.load_vad()
        assert "webrtcvad-wheels" in str(failure.value)
        assert voice_audio.vad_available() is False
    finally:
        voice_audio.importlib.util.find_spec = find_spec
        voice_audio._vad_load_error = error


def test_a_transient_failure_is_retried_rather_than_remembered(monkeypatch):
    """One bad import must not disable voice for the life of the process."""

    import sys

    import backend.services.voice_audio as voice_audio

    error = voice_audio._vad_load_error
    find_spec = voice_audio.importlib.util.find_spec
    try:
        voice_audio._vad_load_error = None
        # The import fails, but the package is on disk -- an import race rather
        # than an absent dependency.
        monkeypatch.setitem(sys.modules, "webrtcvad", None)
        voice_audio.importlib.util.find_spec = lambda name: object()

        with pytest.raises(VoiceModelUnavailable):
            voice_audio.load_vad()
        assert voice_audio._vad_load_error is None, "a transient failure must not stick"
        assert voice_audio.vad_available() is True
    finally:
        voice_audio.importlib.util.find_spec = find_spec
        voice_audio._vad_load_error = error


def test_the_first_import_is_serialised():
    """Two sockets opening together must not import the extension at once."""

    import inspect
    import threading

    import backend.services.voice_audio as voice_audio

    assert isinstance(voice_audio._vad_lock, type(threading.Lock()))
    body = inspect.getsource(voice_audio.load_vad)
    assert "with _vad_lock:" in body
    assert body.index("with _vad_lock:") < body.index("import webrtcvad")


# --------------------------------------------------------------------------- #
# What must never be loaded                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("heavy", ["torch", "onnxruntime", "silero_vad", "faster_whisper"])
def test_a_groq_and_webrtc_start_loads_nothing_heavy(heavy):
    """The whole point of the change.

    With hosted transcription and WebRTC detection, none of these belongs in
    the process. Any one of them returning is what put the instance over
    512 MB and had Render kill it with status 137.
    """

    import subprocess
    import sys

    probe = (
        "import sys;"
        "import backend.main;"
        "from backend.services.voice_audio import WebRtcVad;"
        "d = WebRtcVad();"
        "d.probabilities([bytes(%d)]);"
        "print(','.join(m for m in ('torch','onnxruntime','silero_vad','faster_whisper')"
        " if m in sys.modules))" % VAD_FRAME_BYTES
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=180,
        env={
            **__import__("os").environ,
            "VOICE_STT_PROVIDER": "groq",
            "VOICE_VAD_PROVIDER": "webrtc",
        },
    )
    assert result.returncode == 0, result.stderr[-800:]
    loaded = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert heavy not in loaded, f"{heavy} was imported: {loaded!r}"
