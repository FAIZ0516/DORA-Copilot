"""Voice endpoints against the real app: auth, origin, and the governed turn."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.database.db import Base, Conversation, get_db
from backend.main import app
from backend.voice_session import registry

USER_A = {"X-Development-Session": "voice-user-alpha1"}
USER_B = {"X-Development-Session": "voice-user-bravo1"}
ORIGIN = settings.cors_origin_list[0]


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'voice.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        test_client.session_factory = TestingSession
        yield test_client
    app.dependency_overrides.clear()
    for token in list(registry._sessions):  # noqa: SLF001 - test cleanup
        registry.close(token)


def test_capabilities_report_honestly_so_the_ui_can_degrade(monkeypatch, client):
    # Probe the real availability helpers only through stubs: loading Whisper
    # here would download a model and turn a unit run into a minutes-long one.
    import backend.api.voice as voice_module

    monkeypatch.setattr(voice_module, "stt_available", lambda: True)
    monkeypatch.setattr(voice_module, "vad_available", lambda: True)
    body = client.get("/api/voice/capabilities").json()
    assert body["enabled"] is True
    assert body["stt_available"] is True
    assert body["detail"] is None
    assert set(body) >= {"enabled", "stt_available", "vad_available", "tts_configured"}


def test_capabilities_explain_a_missing_model_rather_than_pretending(monkeypatch, client):
    import backend.api.voice as voice_module

    monkeypatch.setattr(voice_module, "stt_available", lambda: False)
    monkeypatch.setattr(voice_module, "vad_available", lambda: True)
    body = client.get("/api/voice/capabilities").json()
    assert body["stt_available"] is False
    assert "speech recognition" in body["detail"]


def test_opening_a_session_returns_an_opaque_token_and_audio_contract(client):
    response = client.post("/api/voice/session", json={"workspace": "technical"}, headers=USER_A)
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["session_token"]) >= 40
    assert body["sample_rate"] == settings.voice_sample_rate
    assert body["end_silence_ms"] == settings.voice_end_silence_ms
    assert body["frame_bytes"] > 0
    # No credential of any kind may travel to the browser.
    for secret in ("api_key", "password", "elevenlabs", "deepseek"):
        assert secret not in response.text.lower()


def test_opening_a_session_requires_authentication(client):
    response = client.post(
        "/api/voice/session", json={}, headers={"X-Development-Session": "bad"}
    )
    assert response.status_code == 400


def test_a_session_cannot_be_opened_on_someone_elses_conversation(client):
    session = client.session_factory()
    conversation = Conversation(id=uuid.uuid4(), title="theirs", user_id="voice-user-bravo1", state={})
    session.add(conversation)
    session.commit()
    conversation_id = conversation.id
    session.close()

    response = client.post(
        "/api/voice/session",
        json={"conversation_id": str(conversation_id)},
        headers=USER_A,
    )
    assert response.status_code == 404


def test_a_socket_without_an_allowed_origin_is_refused(client):
    token = client.post("/api/voice/session", json={}, headers=USER_A).json()["session_token"]
    with pytest.raises(Exception):
        with client.websocket_connect(
            f"/api/voice/session/{token}", headers={"Origin": "https://evil.example.com"}
        ):
            pass


def test_an_unknown_token_cannot_open_a_socket(client):
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/api/voice/session/not-a-real-token", headers={"Origin": ORIGIN}
        ):
            pass


def test_a_closed_session_token_stops_working(client):
    token = client.post("/api/voice/session", json={}, headers=USER_A).json()["session_token"]
    assert client.delete(f"/api/voice/session/{token}", headers=USER_A).status_code == 204
    with pytest.raises(Exception):
        with client.websocket_connect(
            f"/api/voice/session/{token}", headers={"Origin": ORIGIN}
        ):
            pass


def test_another_user_cannot_close_your_session(client):
    token = client.post("/api/voice/session", json={}, headers=USER_A).json()["session_token"]
    # Silently a no-op rather than an oracle telling them the token exists.
    assert client.delete(f"/api/voice/session/{token}", headers=USER_B).status_code == 204
    assert registry.get(token) is not None


def test_a_voice_turn_runs_through_the_governed_agent(monkeypatch, client):
    """The transcript must take the same path as a typed question."""

    import backend.api.voice as voice_module

    seen: dict[str, object] = {}

    def _fake_turn(**kwargs):
        seen.update(kwargs)
        return {
            "answer": "MBK has 1,434 open bugs.",
            "intent": "ANALYSIS",
            "chart": None,
            "table": None,
            "warnings": [],
            "validation": {"valid": True},
            "metadata": {"conversation_id": str(uuid.uuid4()), "message_id": str(uuid.uuid4())},
        }

    monkeypatch.setattr(voice_module, "run_chat_turn", _fake_turn)
    monkeypatch.setattr(voice_module, "transcribe_pcm", lambda *a, **k: "how many bugs does MBK have")
    monkeypatch.setattr(voice_module, "segment_for_speech", lambda text: [])

    import asyncio

    from backend.voice_session import VoiceState

    session = registry.create(user_id="voice-user-alpha1", conversation_id=None, project_key="DCPM")
    session.transition(VoiceState.LISTENING)

    sent: list[str] = []

    class _Socket:
        async def send_text(self, payload):
            sent.append(payload)

        async def send_json(self, payload):
            sent.append(str(payload))

    asyncio.run(voice_module._handle_utterance(voice_module._Sender(_Socket()), session, b"\x00\x01" * 16000))

    # The turn went through run_chat_turn with the caller's identity intact.
    assert seen["user_id"] == "voice-user-alpha1"
    assert seen["message"] == "how many bugs does MBK have"
    assert seen["project_key"] == "DCPM"
    joined = " ".join(sent)
    assert "transcript.final" in joined
    assert "assistant.text" in joined
    assert "MBK has 1,434 open bugs." in joined


def test_an_empty_transcript_never_reaches_the_agent(monkeypatch, client):
    import asyncio

    import backend.api.voice as voice_module
    from backend.voice_session import VoiceState

    called = False

    def _fail(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("silence must not be sent to the agent")

    monkeypatch.setattr(voice_module, "run_chat_turn", _fail)
    monkeypatch.setattr(voice_module, "transcribe_pcm", lambda *a, **k: "   ")

    session = registry.create(user_id="voice-user-alpha1", conversation_id=None)
    session.transition(VoiceState.LISTENING)

    class _Socket:
        async def send_text(self, payload):
            pass

        async def send_json(self, payload):
            pass

    asyncio.run(voice_module._handle_utterance(voice_module._Sender(_Socket()), session, b"\x00\x01" * 16000))
    assert called is False
    assert session.state is VoiceState.LISTENING


def test_a_cancelled_turn_discards_its_answer_instead_of_speaking_it(monkeypatch, client):
    """A DoraDB query cannot be killed mid-flight, so the result is dropped."""

    import asyncio

    import backend.api.voice as voice_module
    from backend.voice_session import VoiceState

    session = registry.create(user_id="voice-user-alpha1", conversation_id=None)
    session.transition(VoiceState.LISTENING)

    def _slow_turn(**_kwargs):
        # The user interrupts while the database work is still running.
        session.cancel(f"{session.token[:8]}-1")
        return {
            "answer": "stale answer nobody asked for any more",
            "intent": "ANALYSIS", "chart": None, "table": None,
            "warnings": [], "validation": {}, "metadata": {},
        }

    monkeypatch.setattr(voice_module, "run_chat_turn", _slow_turn)
    monkeypatch.setattr(voice_module, "transcribe_pcm", lambda *a, **k: "a real question")

    sent: list[str] = []

    class _Socket:
        async def send_text(self, payload):
            sent.append(payload)

        async def send_json(self, payload):
            sent.append(str(payload))

    asyncio.run(voice_module._handle_utterance(voice_module._Sender(_Socket()), session, b"\x00\x01" * 16000))

    joined = " ".join(sent)
    assert "assistant.interrupted" in joined
    assert "stale answer nobody asked for any more" not in joined


# --------------------------------------------------------------------------- #
# Audio captured while the assistant holds the floor                          #
# --------------------------------------------------------------------------- #
#
# The socket used to await the whole turn inside its receive loop. The browser
# streams continuously, so everything captured while the assistant thought and
# spoke -- including its own voice returning through the speakers -- queued up
# and was then replayed into the detector as if it had just been said. That is
# what made the assistant answer questions nobody asked, always starting after
# the first reply.


def _busy_frames(count):
    """Frames Silero would score as confident speech."""

    from backend.services.voice_audio import VAD_FRAME_BYTES

    return [b"\x40\x00" * (VAD_FRAME_BYTES // 2) for _ in range(count)]


def test_audio_arriving_while_the_assistant_works_is_never_transcribed(monkeypatch, client):
    """Nothing captured mid-turn may become the next question."""

    import asyncio

    import backend.api.voice as voice_module
    from backend.services.voice_audio import UtteranceDetector
    from backend.voice_session import VoiceState, registry

    transcribed = []
    monkeypatch.setattr(
        voice_module, "transcribe_pcm", lambda pcm, **_k: transcribed.append(pcm) or ""
    )

    session = registry.create(user_id="u", conversation_id=None, project_key=None)
    session.state = VoiceState.LISTENING

    # A turn that takes a while, exactly like a real agent call.
    async def _slow_turn(*_args, **_kwargs):
        await asyncio.sleep(0.2)

    async def _drive():
        turn = asyncio.create_task(_slow_turn())
        session.active_turn = "t-1"
        detector = UtteranceDetector()
        barge = UtteranceDetector(start_speech_ms=float(10_000))  # never fires
        heard = bytearray()
        for _frame in _busy_frames(200):
            if not turn.done():
                barge.feed(0.99)
                continue
            if detector.feed(0.99) == "start":
                heard.extend(_frame)
        await turn
        return bytes(heard)

    assert asyncio.run(_drive()) == b""
    # And the agent was never handed any of it.
    assert transcribed == []
    registry.close(session.token)


def test_interrupting_takes_sustained_speech_not_one_stray_frame():
    """The bar for barge-in is far higher than for starting an utterance.

    While the assistant is audible its own voice can reach the microphone. A
    frame or two of that must not count as the user cutting in.
    """

    from backend.config import settings
    from backend.services.voice_audio import UtteranceDetector

    barge = UtteranceDetector(start_speech_ms=float(settings.voice_barge_in_ms))
    normal = UtteranceDetector()

    # Three frames (~96 ms) is enough to begin a normal utterance ...
    assert [normal.feed(0.99) for _ in range(3)][-1] == "start"
    # ... and nowhere near enough to interrupt.
    assert all(barge.feed(0.99) is None for _ in range(3))

    # Sustained speech does interrupt.
    frames_needed = int(settings.voice_barge_in_ms / barge.frame_ms()) + 1
    assert any(barge.feed(0.99) == "start" for _ in range(frames_needed))


def test_the_socket_keeps_reading_while_a_turn_is_in_flight(monkeypatch, client):
    """The receive loop must not block on the turn.

    Blocking is what let a turn's worth of audio accumulate in the socket
    buffer; the backlog, not the microphone, was the source of the phantom
    speech.
    """

    import asyncio
    import inspect

    import backend.api.voice as voice_module

    body = inspect.getsource(voice_module.voice_socket)
    assert "asyncio.create_task(" in body, "the turn must not be awaited inline"
    assert "await _handle_utterance(" not in body

    # And the guard that keeps mid-turn audio out of the detector is present.
    assert "if busy():" in body


def test_the_echo_guard_does_not_apply_when_the_user_cut_in():
    """A turn the user interrupted ends with them mid-sentence.

    The guard exists to ignore the tail of the assistant's own voice after it
    finishes speaking. Applying it after a barge-in instead stays deaf through
    the start of what the user is saying: "no, stop, show me MBK instead"
    reached the agent as "instead please". Cancelling already stopped both the
    synthesis and the browser's playback, so there is nothing left to guard.
    """

    import inspect

    import backend.api.voice as voice_module

    body = inspect.getsource(voice_module.voice_socket)
    assert "cut_in = True" in body, "barge-in must record that it cut the turn short"
    assert "if not cut_in:" in body, "the guard must be skipped after a barge-in"


def test_noise_while_thinking_never_cancels_the_answer():
    """Only speech over the assistant's voice counts as an interruption.

    Transcribing and thinking are dead air the user is waiting through -- and
    thinking can run tens of seconds. Treating a cough or a passing remark as a
    barge-in there cancelled the turn, so the question was heard, understood,
    and then silently thrown away: the UI sat on "Thinking" and "Zara was
    interrupted" together, and no answer ever arrived.
    """

    import inspect

    import backend.api.voice as voice_module

    body = inspect.getsource(voice_module.voice_socket)
    guard = "if session.state != VoiceState.ASSISTANT_SPEAKING:"
    assert guard in body, "barge-in must be limited to the assistant speaking"
    # The guard has to come before the detector is fed, not after.
    assert body.index(guard) < body.index("elif barge_in.feed(probability)")


def test_the_interrupt_bar_is_only_reachable_while_speaking():
    """The detector resets outside speaking, so waiting noise cannot accumulate.

    Without the reset, a long think would leave the barge-in detector already
    primed and the first syllable of the answer would cancel it.
    """

    from backend.config import settings
    from backend.services.voice_audio import UtteranceDetector

    barge = UtteranceDetector(start_speech_ms=float(settings.voice_barge_in_ms))
    frames_needed = int(settings.voice_barge_in_ms / barge.frame_ms()) + 1

    # Noise during the wait, reset each frame the way the socket does.
    for _ in range(frames_needed * 3):
        barge.feed(0.99)
        barge.reset()
    assert barge.speaking is False

    # Speech once the assistant is actually talking still interrupts.
    assert any(barge.feed(0.99) == "start" for _ in range(frames_needed))


def test_the_session_stays_speaking_until_the_browser_says_it_stopped():
    """Delivery is not hearing, and the gap between them is the whole answer.

    Synthesis runs far faster than speech: a half-minute answer reaches the
    browser in about a second. Treating the last segment leaving as the end of
    the turn put the session back to listening while the user could still hear
    the assistant -- so a barge-in found nothing in flight, and the answer
    played to the end no matter what they did.
    """

    import inspect

    import backend.api.voice as voice_module

    speak = inspect.getsource(voice_module._speak)
    assert "session.awaiting_playback = turn_id" in speak
    # And it must no longer declare the session free the moment sending ends.
    tail = speak.split("assistant.audio_finished")[-1]
    assert "VoiceState.LISTENING" not in tail

    body = inspect.getsource(voice_module.voice_socket)
    assert "session.awaiting_playback is not None" in body, "busy() must cover playback"
    assert 'event.type == "playback.finished"' in body


def test_a_browser_that_never_reports_playback_does_not_wedge_the_session():
    """The deadline is the difference between a stuck session and a slow one."""

    import inspect

    import backend.api.voice as voice_module

    body = inspect.getsource(voice_module.voice_socket)
    assert "session.playback_deadline" in body
    assert "never reported finishing playback" in body
    assert voice_module.PLAYBACK_GRACE_SECONDS > 0


# --------------------------------------------------------------------------- #
# Reframing 512-sample chunks into 480-sample WebRTC frames                   #
# --------------------------------------------------------------------------- #


def _reframe(messages):
    """The socket's own reframing, exercised in isolation.

    Mirrors the loop in voice_socket: bytes accumulate in `pending`, whole
    frames are taken from the front, and the remainder waits for the next
    message.
    """

    from backend.services.voice_audio import VAD_FRAME_BYTES

    pending = bytearray()
    frames = []
    for message in messages:
        pending.extend(message)
        while len(pending) >= VAD_FRAME_BYTES:
            frames.append(bytes(pending[:VAD_FRAME_BYTES]))
            del pending[:VAD_FRAME_BYTES]
    return frames, bytes(pending)


def test_browser_chunks_are_reframed_without_losing_a_sample():
    """The browser sends 512 samples; WebRTC takes 480. They never line up.

    Every byte must appear once, in order, across the frames plus whatever is
    still pending -- a seam that drops or repeats samples is audible as a
    click and can split a word across an utterance boundary.
    """

    from backend.services.voice_audio import VAD_FRAME_BYTES

    # 40 messages of 512 samples each, every byte uniquely identifiable.
    stream = bytes(range(256)) * 160
    chunk = 512 * 2
    messages = [stream[i : i + chunk] for i in range(0, len(stream), chunk)]
    assert all(len(m) == chunk for m in messages), "fixture must be whole chunks"

    frames, pending = _reframe(messages)

    assert all(len(f) == VAD_FRAME_BYTES for f in frames)
    assert b"".join(frames) + pending == stream, "samples lost, duplicated or reordered"
    assert len(pending) < VAD_FRAME_BYTES


def test_an_incomplete_frame_waits_for_the_next_message():
    """One WebSocket message is not one VAD frame, and never was."""

    from backend.services.voice_audio import VAD_FRAME_BYTES

    half = VAD_FRAME_BYTES // 2
    frames, pending = _reframe([b"\x01" * half])
    assert frames == [] and len(pending) == half

    # The rest arrives; now exactly one frame is complete.
    frames, pending = _reframe([b"\x01" * half, b"\x02" * half])
    assert len(frames) == 1
    assert pending == b""
    assert frames[0] == b"\x01" * half + b"\x02" * half


def test_ragged_message_sizes_still_reframe_cleanly():
    """Nothing guarantees the browser's chunk size survives the network."""

    from backend.services.voice_audio import VAD_FRAME_BYTES

    stream = bytes(range(256)) * 40
    sizes, at, messages = [1, 7, 960, 61, 1024, 3, 2048], 0, []
    while at < len(stream):
        size = sizes[len(messages) % len(sizes)]
        messages.append(stream[at : at + size])
        at += size

    frames, pending = _reframe(messages)
    assert all(len(f) == VAD_FRAME_BYTES for f in frames)
    assert b"".join(frames) + pending == stream


def test_the_socket_uses_that_same_reframing():
    """The helper above must describe the real loop, not a parallel one."""

    import inspect

    import backend.api.voice as voice_module

    body = inspect.getsource(voice_module.voice_socket)
    assert "pending.extend(chunk)" in body
    assert "while len(pending) >= VAD_FRAME_BYTES:" in body
    assert "del pending[:VAD_FRAME_BYTES]" in body
