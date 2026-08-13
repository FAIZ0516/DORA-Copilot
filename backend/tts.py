"""ElevenLabs streaming TTS with persistent free-tier usage accounting."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import ssl

import httpx
import truststore
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database.db import TTSUsage


logger = logging.getLogger(__name__)


class TTSNotConfiguredError(RuntimeError):
    """Raised when the ElevenLabs API key is absent."""


class TTSQuotaExceededError(RuntimeError):
    """Raised before a request would exceed the configured monthly allowance."""


class TTSProviderError(RuntimeError):
    """Raised when ElevenLabs rejects or cannot complete the request."""


@dataclass(frozen=True)
class UsageSnapshot:
    used: int
    remaining: int


@dataclass(frozen=True)
class AudioStream:
    chunks: AsyncIterator[bytes]
    usage: UsageSnapshot
    request_id: str | None


def _period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _usage_row(session: Session) -> TTSUsage:
    """Load the monthly counter, tolerating a first-request creation race."""

    period = _period()
    row = session.scalar(
        select(TTSUsage).where(TTSUsage.period == period).with_for_update()
    )
    if row is not None:
        return row

    row = TTSUsage(period=period, characters_used=0)
    session.add(row)
    try:
        session.flush()
        return row
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(TTSUsage).where(TTSUsage.period == period).with_for_update()
        )
        if existing is None:
            raise
        return existing


def reserve_characters(session: Session, count: int) -> UsageSnapshot:
    """Reserve a conservative character estimate before generation."""

    row = _usage_row(session)
    projected = row.characters_used + count
    if projected > settings.elevenlabs_monthly_char_limit:
        session.rollback()
        raise TTSQuotaExceededError(
            f"Monthly voice limit reached ({row.characters_used:,}/"
            f"{settings.elevenlabs_monthly_char_limit:,} characters used)."
        )
    row.characters_used = projected
    session.commit()
    return UsageSnapshot(
        used=projected,
        remaining=settings.elevenlabs_monthly_char_limit - projected,
    )


def adjust_characters(session: Session, delta: int) -> UsageSnapshot:
    """Correct a reservation using ElevenLabs' character-cost response header."""

    row = _usage_row(session)
    row.characters_used = max(0, row.characters_used + delta)
    session.commit()
    return UsageSnapshot(
        used=row.characters_used,
        remaining=max(0, settings.elevenlabs_monthly_char_limit - row.characters_used),
    )


# Resolved once per process. A free ElevenLabs plan refuses "library" voices
# over the API with HTTP 402, and the voice picker on their site shows library
# voices most prominently -- so a perfectly reasonable choice silently breaks
# speech. Rather than fail, fall back to a premade voice on the account.
_resolved_voice_id: str | None = None


async def _premade_voice_id(wanted: str | None = None) -> str | None:
    """The closest usable premade voice to the one that was refused.

    Falls back on similarity rather than "whatever is first": a Malay woman's
    voice replaced by a male American one is a worse answer than a female one
    that at least matches. Premade voices are English-accented, but the
    configured multilingual model still pronounces other languages, so gender
    is the attribute worth preserving.

    Opens its own client: the shared error path closes the caller's before
    this runs.
    """

    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        async with httpx.AsyncClient(
            timeout=settings.elevenlabs_timeout_seconds, verify=ssl_context
        ) as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": settings.elevenlabs_api_key},
            )
            if response.status_code != 200:
                return None
            voices = response.json().get("voices", [])
    except httpx.HTTPError:
        return None

    target = next((v for v in voices if v.get("voice_id") == wanted), None)
    wanted_labels = (target or {}).get("labels") or {}
    usable = [v for v in voices if v.get("category") == "premade" and v.get("voice_id")]
    if not usable:
        return None

    def score(voice: dict) -> tuple[int, int]:
        labels = voice.get("labels") or {}
        return (
            1 if labels.get("language") == wanted_labels.get("language") else 0,
            1 if labels.get("gender") == wanted_labels.get("gender") else 0,
        )

    best = max(usable, key=score)
    return str(best["voice_id"])


async def create_audio_stream(text: str, session: Session) -> AudioStream:
    """Open ElevenLabs' response stream and return a browser-ready MP3 iterator."""

    global _resolved_voice_id

    if not settings.elevenlabs_api_key:
        raise TTSNotConfiguredError("ELEVENLABS_API_KEY is not configured.")

    estimated_cost = len(text)
    usage = reserve_characters(session, estimated_cost)
    # Use Windows' trusted certificate store. This supports corporate/local
    # TLS roots without weakening certificate verification.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client = httpx.AsyncClient(
        timeout=settings.elevenlabs_timeout_seconds,
        verify=ssl_context,
    )
    voice_id = _resolved_voice_id or settings.elevenlabs_voice_id
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    request = client.build_request(
        "POST",
        url,
        params={"output_format": settings.elevenlabs_output_format},
        headers={
            "xi-api-key": settings.elevenlabs_api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": settings.elevenlabs_model_id,
        },
    )

    try:
        response = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        adjust_characters(session, -estimated_cost)
        await client.aclose()
        raise TTSProviderError("Could not connect to ElevenLabs.") from exc

    if response.is_error:
        payload = await response.aread()
        await response.aclose()
        await client.aclose()
        adjust_characters(session, -estimated_cost)
        detail = payload.decode("utf-8", errors="replace")[:300]
        # A free ElevenLabs plan cannot use "library" voices over the API, only
        # the premade ones on the account. The raw 402 body says nothing about
        # which setting is wrong, so name it -- this cost a debugging session.
        if response.status_code == 402 and "library voices" in detail.lower():
            fallback = await _premade_voice_id(voice_id)
            if fallback and fallback != voice_id:
                logger.warning(
                    "ElevenLabs voice %s is a library voice this plan cannot use; "
                    "falling back to premade voice %s. Set ELEVENLABS_VOICE_ID to a "
                    "premade voice to silence this.",
                    voice_id,
                    fallback,
                )
                _resolved_voice_id = fallback
                # Retry once with a voice the plan allows.
                return await create_audio_stream(text, session)
            raise TTSProviderError(
                f"The configured ElevenLabs voice ({voice_id}) is a library voice, "
                "which a free plan cannot use over the API, and no premade voice "
                "could be found on the account. Set ELEVENLABS_VOICE_ID to a premade "
                "voice, or upgrade the plan."
            )
        raise TTSProviderError(
            f"ElevenLabs returned HTTP {response.status_code}: {detail}"
        )

    try:
        actual_cost = int(response.headers.get("character-cost", estimated_cost))
    except ValueError:
        actual_cost = estimated_cost
    if actual_cost != estimated_cost:
        usage = adjust_characters(session, actual_cost - estimated_cost)

    async def relay() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return AudioStream(
        chunks=relay(),
        usage=usage,
        request_id=response.headers.get("request-id"),
    )
