"""Voice-activity detection: Silero without PyTorch, loaded once and safely."""

import pytest




# --------------------------------------------------------------------------- #
# Running Silero without PyTorch                                              #
# --------------------------------------------------------------------------- #


def _frames(count, *, loud=True, seed=7):
    """Frames of noise or silence, in the shape the browser worklet sends."""

    import numpy as np

    from backend.services.voice_audio import VAD_FRAME_SAMPLES

    rng = np.random.default_rng(seed)
    out = []
    for _ in range(count):
        samples = rng.normal(0, 0.25, VAD_FRAME_SAMPLES) if loud else np.zeros(VAD_FRAME_SAMPLES)
        out.append((samples * 32767).astype(np.int16).tobytes())
    return out


def test_voice_detection_never_loads_pytorch():
    """PyTorch is the largest thing this process could load, and it is not needed.

    silero-vad's own wrapper runs the ONNX graph through onnxruntime and uses
    torch only to carry arrays in and out. Importing it cost a few hundred
    megabytes of resident memory on a small instance for no arithmetic.
    """

    import subprocess
    import sys

    # A clean interpreter: this test process may have imported torch elsewhere.
    probe = (
        "import sys;"
        "from backend.services.voice_audio import SileroVad;"
        "d = SileroVad();"
        "d.probabilities([bytes(1024)]);"
        "print('torch' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("False"), "voice detection imported torch"


def test_each_conversation_scores_its_own_audio():
    """Silero is recurrent, so its state cannot be shared between sessions.

    The state used to live on the one process-wide model object. Two people in
    voice mode at once would have interleaved their audio through it and
    corrupted each other's utterance boundaries.
    """

    from backend.services.voice_audio import SileroVad

    speech = _frames(8)

    alone = SileroVad()
    expected = alone.probabilities(speech)

    # The same audio, scored while a second conversation runs against the same
    # shared ONNX session, must produce the same numbers.
    first, second = SileroVad(), SileroVad()
    interleaved = []
    for frame in speech:
        interleaved.append(first.probability(frame))
        second.probability(b"\x00\x00" * 512)  # the other conversation, silent

    assert interleaved == expected


def test_resetting_returns_the_detector_to_a_blank_state():
    """Between turns the detector must forget, or the last turn colours the next."""

    from backend.services.voice_audio import SileroVad

    detector = SileroVad()
    speech = _frames(6)

    first_pass = detector.probabilities(speech)
    detector.reset()
    second_pass = detector.probabilities(speech)

    assert first_pass == second_pass


def test_each_frame_is_scored_with_the_previous_frames_context():
    """Silero conditions on the last 64 samples of the frame before.

    Dropping that does not raise -- it silently returns different, worse
    probabilities, which is exactly the kind of change that shows up as
    mis-detected speech rather than as a failure.
    """

    import numpy as np

    from backend.services.voice_audio import VAD_CONTEXT_SAMPLES, VAD_FRAME_SAMPLES, SileroVad

    seen = []

    class _Recorder:
        def run(self, _outputs, inputs):
            seen.append(inputs["input"].shape)
            # onnxruntime returns [probability, next_state].
            return [
                np.zeros((1, 1), dtype=np.float32),
                np.zeros((2, 1, 128), dtype=np.float32),
            ]

    detector = SileroVad(session=_Recorder())
    detector.probabilities(_frames(3))

    assert seen == [(1, VAD_FRAME_SAMPLES + VAD_CONTEXT_SAMPLES)] * 3


def test_a_transient_load_failure_is_retried_rather_than_remembered():
    """One bad import must not disable voice for the life of the process.

    A single "import numpy failed" while two sockets opened together left the
    capability endpoint reporting no voice detection until the server was
    restarted -- the UI said "Voice mode needs local voice detection" on a
    machine where it loads perfectly.
    """

    import backend.services.voice_audio as voice_audio

    session, error = voice_audio._vad_session, voice_audio._vad_load_error
    try:
        voice_audio._vad_session = None
        voice_audio._vad_load_error = None
        attempts = []

        def _flaky():
            attempts.append(1)
            if len(attempts) == 1:
                raise ImportError("import numpy failed")
            return "session"

        original = voice_audio._vad_model_path
        voice_audio._vad_model_path = _flaky
        try:
            with pytest.raises(voice_audio.VoiceModelUnavailable):
                voice_audio.load_vad()
            # The package is installed, so the failure is treated as transient.
            assert voice_audio._vad_load_error is None
            assert voice_audio.vad_available() is True
        finally:
            voice_audio._vad_model_path = original
    finally:
        voice_audio._vad_session, voice_audio._vad_load_error = session, error


def test_a_genuinely_missing_package_is_remembered():
    """Retrying an absent package on every frame would be pure waste."""

    import backend.services.voice_audio as voice_audio

    session, error = voice_audio._vad_session, voice_audio._vad_load_error
    find_spec = voice_audio.importlib.util.find_spec
    try:
        voice_audio._vad_session = None
        voice_audio._vad_load_error = None
        voice_audio.importlib.util.find_spec = lambda name: None

        with pytest.raises(voice_audio.VoiceModelUnavailable):
            voice_audio.load_vad()
        assert voice_audio._vad_load_error is not None
        assert voice_audio.vad_available() is False
    finally:
        voice_audio.importlib.util.find_spec = find_spec
        voice_audio._vad_session, voice_audio._vad_load_error = session, error


def test_the_first_load_is_serialised():
    """Two sockets opening together must not import onnxruntime concurrently."""

    import inspect

    import backend.services.voice_audio as voice_audio

    assert isinstance(voice_audio._vad_lock, type(__import__("threading").Lock()))
    body = inspect.getsource(voice_audio.load_vad)
    assert "with _vad_lock:" in body
    # And the double-check inside the lock, so the second caller reuses the
    # session rather than building another.
    assert body.index("with _vad_lock:") < body.index("import onnxruntime")
