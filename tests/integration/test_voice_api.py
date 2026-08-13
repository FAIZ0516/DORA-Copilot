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

    asyncio.run(voice_module._handle_utterance(_Socket(), session, b"\x00\x01" * 16000))

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

    asyncio.run(voice_module._handle_utterance(_Socket(), session, b"\x00\x01" * 16000))
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

    asyncio.run(voice_module._handle_utterance(_Socket(), session, b"\x00\x01" * 16000))

    joined = " ".join(sent)
    assert "assistant.interrupted" in joined
    assert "stale answer nobody asked for any more" not in joined
