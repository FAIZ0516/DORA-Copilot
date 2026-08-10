"""Text-to-speech endpoint (ElevenLabs, quota-gated)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database.db import get_db
from ..schemas import TTSRequest
from ..tts import (
    TTSNotConfiguredError,
    TTSProviderError,
    TTSQuotaExceededError,
    create_audio_stream,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tts"])


@router.post(
    "/tts",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"audio/mpeg": {}}},
        413: {"description": "Text exceeds the per-request voice limit"},
        429: {"description": "Monthly character allowance exhausted"},
        503: {"description": "ElevenLabs is not configured"},
    },
)
async def text_to_speech(
    request: TTSRequest,
    session: Session = Depends(get_db),
) -> StreamingResponse:
    if len(request.text) > settings.elevenlabs_max_chars_per_request:
        raise HTTPException(
            status_code=413,
            detail=(
                "Voice text is too long. "
                f"Maximum: {settings.elevenlabs_max_chars_per_request:,} characters."
            ),
        )
    try:
        audio = await create_audio_stream(request.text, session)
    except TTSNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TTSQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TTSProviderError as exc:
        logger.warning("ElevenLabs generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    headers = {
        "Cache-Control": "private, max-age=3600",
        "X-TTS-Characters-Used": str(audio.usage.used),
        "X-TTS-Characters-Remaining": str(audio.usage.remaining),
    }
    if audio.request_id:
        headers["X-ElevenLabs-Request-ID"] = audio.request_id
    return StreamingResponse(audio.chunks, media_type="audio/mpeg", headers=headers)


__all__ = ["router"]
