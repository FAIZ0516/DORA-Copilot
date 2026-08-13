"""Voice-session lifecycle, state machine, and the audio plumbing.

Nothing here loads a model or calls a paid service: Silero, Whisper and
ElevenLabs are all mocked or bypassed.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from backend.config import settings
from backend.services.voice_audio import (
    MIN_UTTERANCE_MS,
    VAD_FRAME_SAMPLES,
    UtteranceDetector,
    pcm_to_wav_file,
    transcribe_pcm,
)
from backend.services.voice_speech import markdown_to_speech, segment_for_speech
from backend.voice_session import (
    ClientEvent,
    ServerEvent,
    VoiceSessionRegistry,
    VoiceState,
    can_transition,
    origin_allowed,
)


# --------------------------------------------------------------------------- #
# Registry and tokens                                                         #
# --------------------------------------------------------------------------- #


def test_a_session_token_is_opaque_and_unguessable() -> None:
    registry = VoiceSessionRegistry()
    first = registry.create(user_id="alpha", conversation_id=None)
    second = registry.create(user_id="alpha", conversation_id=None)
    assert first.token != second.token
    assert len(first.token) >= 40
    # The token must not encode who it belongs to.
    assert "alpha" not in first.token


def test_an_unknown_token_resolves_to_nothing() -> None:
    registry = VoiceSessionRegistry()
    assert registry.get("not-a-real-token") is None


def test_a_session_expires_and_is_dropped() -> None:
    registry = VoiceSessionRegistry()
    session = registry.create(user_id="alpha", conversation_id=None, ttl_seconds=60)
    session.expires_at = time.monotonic() - 1
    assert registry.get(session.token) is None
    assert len(registry) == 0


def test_closing_a_session_invalidates_its_token() -> None:
    registry = VoiceSessionRegistry()
    session = registry.create(user_id="alpha", conversation_id=None)
    registry.close(session.token)
    assert registry.get(session.token) is None
    assert session.state is VoiceState.CLOSED


def test_expired_sessions_are_purged_in_bulk() -> None:
    registry = VoiceSessionRegistry()
    stale = [registry.create(user_id="alpha", conversation_id=None) for _ in range(3)]
    live = registry.create(user_id="alpha", conversation_id=None)
    for session in stale:
        session.expires_at = time.monotonic() - 1
    assert registry.purge_expired() == 3
    assert registry.get(live.token) is not None
    assert len(registry) == 1


def test_a_session_remembers_its_owner_and_conversation() -> None:
    registry = VoiceSessionRegistry()
    conversation = uuid4()
    session = registry.create(
        user_id="alpha", conversation_id=conversation, workspace="business",
        project_key="DCPM", dashboard_context={"squad": "MBK"},
    )
    assert session.user_id == "alpha"
    assert session.conversation_id == conversation
    assert session.dashboard_context == {"squad": "MBK"}


# --------------------------------------------------------------------------- #
# Origin                                                                      #
# --------------------------------------------------------------------------- #


def test_only_configured_origins_may_open_a_socket() -> None:
    allowed = settings.cors_origin_list[0]
    assert origin_allowed(allowed)
    assert origin_allowed(allowed.rstrip("/") + "/")
    assert not origin_allowed("https://evil.example.com")
    # Browsers always send Origin; a missing one is not a browser.
    assert not origin_allowed(None)
    assert not origin_allowed("")


# --------------------------------------------------------------------------- #
# State machine                                                               #
# --------------------------------------------------------------------------- #


def test_a_turn_follows_the_expected_path() -> None:
    path = [
        VoiceState.IDLE, VoiceState.LISTENING, VoiceState.USER_SPEAKING,
        VoiceState.TRANSCRIBING, VoiceState.THINKING,
        VoiceState.ASSISTANT_SPEAKING, VoiceState.LISTENING,
    ]
    for current, target in zip(path, path[1:]):
        assert can_transition(current, target), f"{current} -> {target}"


def test_interruption_is_reachable_from_every_active_state() -> None:
    # Barge-in is the point of the feature; it must never be blocked.
    for state in (
        VoiceState.TRANSCRIBING, VoiceState.THINKING, VoiceState.ASSISTANT_SPEAKING
    ):
        assert can_transition(state, VoiceState.INTERRUPTED)
    assert can_transition(VoiceState.INTERRUPTED, VoiceState.LISTENING)


def test_a_closed_session_goes_nowhere() -> None:
    for state in VoiceState:
        assert not can_transition(VoiceState.CLOSED, state)


def test_an_illegal_transition_is_refused_not_silently_applied() -> None:
    registry = VoiceSessionRegistry()
    session = registry.create(user_id="alpha", conversation_id=None)
    assert session.state is VoiceState.IDLE
    # Idle cannot jump straight to speaking an answer.
    assert session.transition(VoiceState.ASSISTANT_SPEAKING) is False
    assert session.state is VoiceState.IDLE
    assert session.transition(VoiceState.LISTENING) is True


# --------------------------------------------------------------------------- #
# Cancellation                                                                #
# --------------------------------------------------------------------------- #


def test_cancelling_marks_only_the_named_turn() -> None:
    registry = VoiceSessionRegistry()
    session = registry.create(user_id="alpha", conversation_id=None)
    first = session.next_turn_id()
    second = session.next_turn_id()
    session.cancel(first)
    assert session.is_cancelled(first)
    # A late cancel for a finished turn must not kill the one after it.
    assert not session.is_cancelled(second)


def test_cancelling_nothing_is_harmless() -> None:
    registry = VoiceSessionRegistry()
    session = registry.create(user_id="alpha", conversation_id=None)
    session.cancel(None)
    assert not session.is_cancelled(session.next_turn_id())


# --------------------------------------------------------------------------- #
# Utterance detection                                                         #
# --------------------------------------------------------------------------- #


def _run(detector: UtteranceDetector, probabilities: list[float]) -> list[str]:
    return [event for p in probabilities if (event := detector.feed(p))]


def test_speech_must_persist_before_it_counts_as_a_start() -> None:
    detector = UtteranceDetector()
    # One noisy frame is a keyboard, not a question.
    assert detector.feed(0.9) is None
    assert not detector.speaking


def test_a_sustained_utterance_starts_and_ends_on_silence() -> None:
    detector = UtteranceDetector(end_silence_ms=100)
    frames = detector.frame_ms()
    speech = [0.9] * 10
    silence = [0.01] * (int(100 / frames) + 2)
    events = _run(detector, speech + silence)
    assert events[0] == "start"
    assert events[-1] == "end"
    assert not detector.speaking


def test_a_brief_pause_does_not_end_the_utterance() -> None:
    detector = UtteranceDetector(end_silence_ms=700)
    _run(detector, [0.9] * 10)
    assert detector.speaking
    # A pause for breath is not the end of a sentence.
    assert _run(detector, [0.01] * 3) == []
    assert detector.speaking


def test_an_endless_utterance_times_out() -> None:
    detector = UtteranceDetector(max_utterance_seconds=1)
    frames_per_second = int(1000 / detector.frame_ms())
    events = _run(detector, [0.9] * (frames_per_second + 20))
    assert "start" in events
    assert "timeout" in events
    # The cap closes the current utterance so it can be transcribed; someone
    # who keeps talking simply starts a new one rather than being muted.
    assert events.index("timeout") > events.index("start")


def test_background_noise_never_creates_a_turn() -> None:
    detector = UtteranceDetector()
    assert _run(detector, [0.1] * 200) == []
    assert not detector.speaking


# --------------------------------------------------------------------------- #
# Transcription                                                               #
# --------------------------------------------------------------------------- #


class _Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class _Whisper:
    def __init__(self, text: str = "how many bugs does MBK have") -> None:
        self.text = text
        self.calls: list[str] = []

    def transcribe(self, path, **_kwargs):
        self.calls.append(path)
        return [_Segment(self.text)], {}


def _pcm(milliseconds: int) -> bytes:
    return b"\x00\x01" * int(settings.voice_sample_rate * milliseconds / 1000)


def test_a_too_short_utterance_never_reaches_the_model() -> None:
    model = _Whisper()
    assert transcribe_pcm(_pcm(MIN_UTTERANCE_MS - 50), model=model) == ""
    assert model.calls == [], "a cough must not be transcribed"


def test_a_real_utterance_is_transcribed_and_the_file_removed() -> None:
    import os

    model = _Whisper()
    text = transcribe_pcm(_pcm(1000), model=model)
    assert text == "how many bugs does MBK have"
    assert len(model.calls) == 1
    # Temporary audio must not be left on disk.
    assert not os.path.exists(model.calls[0])


def test_the_temporary_file_is_removed_even_when_transcription_fails() -> None:
    import os

    captured: list[str] = []

    class _Broken:
        def transcribe(self, path, **_kwargs):
            captured.append(path)
            raise RuntimeError("model exploded")

    with pytest.raises(RuntimeError):
        transcribe_pcm(_pcm(1000), model=_Broken())
    assert captured and not os.path.exists(captured[0])


def test_temporary_audio_names_are_unique_per_call() -> None:
    import os

    first = pcm_to_wav_file(_pcm(100))
    second = pcm_to_wav_file(_pcm(100))
    try:
        # A shared fixed name would let concurrent sessions overwrite each other.
        assert first != second
    finally:
        os.unlink(first)
        os.unlink(second)


# --------------------------------------------------------------------------- #
# Speech segmentation                                                         #
# --------------------------------------------------------------------------- #


def test_markdown_is_stripped_before_speaking() -> None:
    spoken = markdown_to_speech("## Summary\n\n- **812** of 1,876 done\n- `status_category` matters")
    for marker in ("##", "**", "`", "- "):
        assert marker not in spoken
    # Underscored identifiers are unreadable aloud.
    assert "status category" in spoken
    assert "status_category" not in spoken


def test_a_table_is_spoken_as_cells_not_pipes() -> None:
    spoken = markdown_to_speech("| Squad | Bugs |\n|---|---|\n| MBK | 1434 |")
    assert "|" not in spoken
    assert "MBK, 1434" in spoken


def test_an_answer_is_split_into_speakable_segments() -> None:
    segments = segment_for_speech(
        "MBK completed 812 tickets. Twelve bugs remain open. The oldest is 96 days old."
    )
    assert len(segments) >= 2
    # Ordering is what makes streamed playback coherent.
    assert segments[0].startswith("MBK completed")
    assert all(len(segment) <= 240 for segment in segments)


def test_abbreviations_do_not_split_a_sentence() -> None:
    segments = segment_for_speech("Check the status, e.g. Done or To Do, before deciding.")
    assert len(segments) == 1


def test_an_empty_answer_produces_no_segments_to_bill_for() -> None:
    assert segment_for_speech("") == []
    assert segment_for_speech("   \n  ") == []


def test_a_very_long_sentence_is_broken_at_clauses() -> None:
    long_text = ", ".join(f"clause number {index} with some words" for index in range(30))
    segments = segment_for_speech(long_text)
    assert len(segments) > 1
    assert all(len(segment) <= 240 for segment in segments)


# --------------------------------------------------------------------------- #
# Wire events                                                                 #
# --------------------------------------------------------------------------- #


def test_client_events_are_validated_not_trusted() -> None:
    assert ClientEvent.model_validate({"type": "session.stop"}).type == "session.stop"
    with pytest.raises(Exception):
        ClientEvent.model_validate({"type": "definitely.not.an.event"})


def test_server_events_omit_empty_fields_on_the_wire() -> None:
    payload = ServerEvent(type="session.ready", state=VoiceState.LISTENING).dumps()
    assert "session.ready" in payload
    assert "chart" not in payload


def test_the_speak_path_reads_the_stream_field_that_actually_exists() -> None:
    """AudioStream exposes `chunks`; `iterator` silently never existed.

    The mistake was invisible until TTS itself started working, because the
    provider error fired first. Pinning it here keeps that from recurring.
    """

    import inspect

    import backend.api.voice as voice_module
    from backend.tts import AudioStream

    assert "chunks" in AudioStream.__annotations__
    assert "iterator" not in AudioStream.__annotations__
    source = inspect.getsource(voice_module._speak)
    assert "stream.chunks" in source
    assert "stream.iterator" not in source


def test_a_library_voice_failure_names_the_setting_to_change() -> None:
    """A free ElevenLabs plan refuses library voices with an opaque 402."""

    import inspect

    from backend import tts

    source = inspect.getsource(tts.create_audio_stream)
    assert "library voices" in source
    assert "ELEVENLABS_VOICE_ID" in source


def test_a_library_voice_falls_back_instead_of_failing_the_answer() -> None:
    """A free plan refuses library voices, and their picker promotes them.

    Two reasonable voice choices in a row were refused with HTTP 402, so the
    product now recovers rather than going mute.
    """

    import inspect

    from backend import tts

    source = inspect.getsource(tts.create_audio_stream)
    assert "_premade_voice_id(voice_id)" in source
    assert "_resolved_voice_id = fallback" in source
    # The retry must not loop: it only fires when the fallback differs.
    assert "fallback != voice_id" in source
    # The lookup opens its own client -- the shared error path already closed
    # the caller's before this point.
    lookup = inspect.getsource(tts._premade_voice_id)
    assert "httpx.AsyncClient" in lookup
    assert 'category") == "premade"' in lookup


def test_the_fallback_voice_matches_the_one_it_replaces() -> None:
    """Replacing a Malay woman's voice with a male American one is a worse
    answer than picking a female voice that at least matches."""

    import inspect

    from backend import tts

    source = inspect.getsource(tts._premade_voice_id)
    # Similarity, not "whatever came back first".
    assert "def score(" in source
    assert 'labels.get("gender") == wanted_labels.get("gender")' in source
    assert 'labels.get("language") == wanted_labels.get("language")' in source
    assert "max(usable, key=score)" in source
    # Only voices the plan can actually use are candidates.
    assert 'category") == "premade"' in source
    # The refused voice is passed in so its labels can be matched.
    caller = inspect.getsource(tts.create_audio_stream)
    assert "_premade_voice_id(voice_id)" in caller
