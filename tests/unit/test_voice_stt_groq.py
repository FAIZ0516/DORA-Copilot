"""Hosted speech recognition.

No test here reaches Groq: every HTTP call is intercepted. The point of the
provider is that a small instance loads no model, so these also pin that the
capability checks stay cheap.
"""

from __future__ import annotations

import io
import wave

import httpx
import pytest

from backend.config import settings
from backend.services import voice_audio
from backend.services.voice_audio import (
    VoiceModelUnavailable,
    pcm_to_wav_bytes,
    stt_available,
    transcribe_pcm,
    transcribe_with_groq,
    vad_available,
)


def _pcm(milliseconds: int = 1000) -> bytes:
    return b"\x00\x01" * int(settings.voice_sample_rate * milliseconds / 1000)


@pytest.fixture()
def groq(monkeypatch):
    """Configure the hosted provider with a fake key that never leaves here."""

    monkeypatch.setattr(settings, "voice_stt_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")
    return settings


def _intercept(monkeypatch, handler):
    """Replace the transport so no request can reach the network."""

    class _Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, url, **kwargs):
            return handler(url, **kwargs)

    monkeypatch.setattr(voice_audio.httpx, "Client", _Client)


def _response(status: int, payload: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status, json=payload if payload is not None else {},
        request=httpx.Request("POST", "https://example.invalid"),
    )


# --------------------------------------------------------------------------- #
# Capability checks must not load a model                                     #
# --------------------------------------------------------------------------- #


def test_hosted_recognition_needs_only_a_key(groq, monkeypatch):
    assert stt_available() is True
    monkeypatch.setattr(settings, "groq_api_key", "")
    assert stt_available() is False


def test_capability_checks_load_nothing(groq, monkeypatch):
    """The health endpoint used to load Whisper just to answer, which is the
    behaviour that exhausted memory on a small instance."""

    def _explode(*_a, **_k):
        raise AssertionError("a capability check must not load a model")

    monkeypatch.setattr(voice_audio, "load_whisper", _explode)
    monkeypatch.setattr(voice_audio, "load_vad", _explode)
    assert stt_available() is True
    assert vad_available() in {True, False}


# --------------------------------------------------------------------------- #
# Audio packaging                                                             #
# --------------------------------------------------------------------------- #


def test_audio_is_wrapped_in_memory_not_written_to_disk():
    data = pcm_to_wav_bytes(_pcm(500))
    with wave.open(io.BytesIO(data), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == settings.voice_sample_rate


# --------------------------------------------------------------------------- #
# The request                                                                 #
# --------------------------------------------------------------------------- #


def test_a_transcript_comes_back_without_loading_a_model(groq, monkeypatch):
    seen: dict = {}

    def handler(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return _response(200, {"text": "how many bugs does MBK have"})

    _intercept(monkeypatch, handler)
    assert transcribe_pcm(_pcm()) == "how many bugs does MBK have"
    assert seen["url"].endswith("/audio/transcriptions")
    assert seen["data"]["model"] == settings.groq_stt_model
    # A pinned language stops a short clip being read as another one.
    assert seen["data"]["language"] == settings.voice_language
    assert "file" in seen["files"]


def test_the_key_travels_only_in_the_authorization_header(groq, monkeypatch):
    seen: dict = {}
    _intercept(monkeypatch, lambda url, **kw: (seen.update(kw), _response(200, {"text": "hi"}))[1])
    transcribe_pcm(_pcm())
    assert seen["headers"]["Authorization"].startswith("Bearer ")
    # Never in the URL or the form body, where it would be logged.
    assert "test-key-not-real" not in str(seen.get("data"))


def test_copy_paste_whitespace_is_removed_from_the_key(groq, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(settings, "groq_api_key", "\r\n test-key-not-real \t")
    _intercept(monkeypatch, lambda url, **kw: (seen.update(kw), _response(200, {"text": "hi"}))[1])

    transcribe_pcm(_pcm())

    assert seen["headers"]["Authorization"] == "Bearer test-key-not-real"


def test_a_short_utterance_never_leaves_the_machine(groq, monkeypatch):
    def _fail(*_a, **_k):
        raise AssertionError("a cough must not be uploaded")

    _intercept(monkeypatch, _fail)
    assert transcribe_pcm(_pcm(100)) == ""


def test_phantom_phrases_are_dropped_as_they_are_locally(groq, monkeypatch):
    _intercept(monkeypatch, lambda url, **kw: _response(200, {"text": "Thank you."}))
    assert transcribe_pcm(_pcm()) == ""


# --------------------------------------------------------------------------- #
# Failures stay quiet about the key and the audio                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "rejected"), (429, "rate limited"), (500, "HTTP 500")],
)
def test_provider_failures_are_actionable_and_sanitised(groq, monkeypatch, status, expected):
    _intercept(monkeypatch, lambda url, **kw: _response(status, {"error": "secret-ish detail"}))
    with pytest.raises(VoiceModelUnavailable) as failure:
        transcribe_pcm(_pcm())
    message = str(failure.value)
    assert expected in message
    # Neither the key nor the provider body may surface to the user or the log.
    assert "test-key-not-real" not in message
    assert "secret-ish detail" not in message


def test_a_network_failure_is_reported_without_internals(groq, monkeypatch):
    def handler(url, **_kwargs):
        raise httpx.ConnectError("connection refused to 1.2.3.4")

    _intercept(monkeypatch, handler)
    with pytest.raises(VoiceModelUnavailable) as failure:
        transcribe_pcm(_pcm())
    assert "1.2.3.4" not in str(failure.value)


def test_selecting_groq_without_a_key_fails_before_any_request(monkeypatch):
    monkeypatch.setattr(settings, "voice_stt_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(VoiceModelUnavailable) as failure:
        transcribe_with_groq(_pcm())
    assert "GROQ_API_KEY" in str(failure.value)


# --------------------------------------------------------------------------- #
# The local engine still works                                                #
# --------------------------------------------------------------------------- #


class _Segment:
    def __init__(self, text): self.text, self.no_speech_prob, self.avg_logprob = text, 0.0, -0.2


class _Whisper:
    def transcribe(self, audio, **_kwargs):
        return [_Segment("local transcription still works")], {}


def test_the_local_engine_is_unchanged_by_the_new_provider(monkeypatch):
    monkeypatch.setattr(settings, "voice_stt_provider", "faster-whisper")
    assert transcribe_pcm(_pcm(), model=_Whisper()) == "local transcription still works"


def test_an_explicit_model_wins_over_the_configured_provider(groq, monkeypatch):
    def _fail(*_a, **_k):
        raise AssertionError("an explicit model must not be overridden by the provider")

    _intercept(monkeypatch, _fail)
    assert transcribe_pcm(_pcm(), model=_Whisper()) == "local transcription still works"


def test_a_rejected_key_points_at_the_usual_cause(groq, monkeypatch):
    """Settings load once at import, so a key rotated after start-up is stale.

    That was the cause every time this fired, and the bare "key was rejected"
    sent us hunting the key itself instead of the process holding it.
    """

    _intercept(monkeypatch, lambda url, **kw: _response(401, {"error": "invalid api key"}))
    with pytest.raises(VoiceModelUnavailable) as failure:
        transcribe_pcm(_pcm())
    message = str(failure.value)
    assert "restart the backend" in message
    assert "GROQ_API_KEY" in message
    # Still no secret and no provider body.
    assert "test-key-not-real" not in message
    assert "invalid api key" not in message
