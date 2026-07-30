"""ElevenLabs streaming TTS with persistent free-tier usage accounting."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
import ssl

import httpx
import truststore
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import TTSUsage


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


async def create_audio_stream(text: str, session: Session) -> AudioStream:
    """Open ElevenLabs' response stream and return a browser-ready MP3 iterator."""

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
    url = (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        f"{settings.elevenlabs_voice_id}"
    )
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
