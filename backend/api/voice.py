"""Realtime voice conversation.

Two endpoints. ``POST /api/voice/session`` is authenticated the same way as the
rest of the API and mints a short-lived opaque token bound to the caller and
their conversation. ``WS /api/voice/session/{token}`` carries only that token,
because browsers cannot attach the development-session header to a socket.

The socket streams microphone PCM in, runs Silero to find utterance boundaries,
transcribes with local Whisper, and then runs the transcript through
``chat_service.run_chat_turn`` -- the same governed workflow as POST /api/chat,
with the same approved queries, guardrails, evidence validation and
persistence. Nothing here talks to DeepSeek directly and nothing bypasses the
agent.

Blocking work (transcription, the agent turn, speech synthesis) runs in a
worker thread so the event loop keeps reading audio, which is what makes
interrupting the assistant possible mid-answer.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..chat_service import ConversationNotFound, run_chat_turn
from ..config import settings
from ..database.db import SessionLocal, get_db
from ..schemas import (
    VoiceCapabilityResponse,
    VoiceSessionRequest,
    VoiceSessionResponse,
)
from ..services.voice_audio import (
    VAD_FRAME_BYTES,
    UtteranceDetector,
    VoiceModelUnavailable,
    load_vad,
    speech_probabilities,
    stt_available,
    transcribe_pcm,
    vad_available,
)
from ..services.voice_speech import segment_for_speech
from ..tts import (
    TTSNotConfiguredError,
    TTSProviderError,
    TTSQuotaExceededError,
    create_audio_stream,
)
from ..voice_session import (
    ClientEvent,
    ServerEvent,
    VoiceSession,
    VoiceState,
    origin_allowed,
    registry,
)
from .dependencies import development_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

# Close codes. 4401 unauthorised, 4403 forbidden origin, 4404 unknown session.
CLOSE_UNAUTHORISED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404

# Stop buffering a runaway utterance well before memory becomes a problem.
MAX_UTTERANCE_BYTES = 16_000 * 2 * 120


@router.get("/capabilities", response_model=VoiceCapabilityResponse)
def capabilities() -> VoiceCapabilityResponse:
    """What voice mode can actually do here, so the UI can degrade honestly."""

    if not settings.voice_mode_enabled:
        return VoiceCapabilityResponse(
            enabled=False, stt_available=False, vad_available=False,
            tts_configured=bool(settings.elevenlabs_api_key),
            detail="Voice mode is disabled by configuration.",
        )
    stt = stt_available()
    vad = vad_available()
    detail = None
    if not stt or not vad:
        missing = [name for name, ok in (("speech recognition", stt), ("voice detection", vad)) if not ok]
        if not stt and settings.voice_stt_provider == "groq":
            detail = (
                "Hosted speech recognition is selected but GROQ_API_KEY is not "
                "configured on the server."
            )
        else:
            detail = (
                f"Voice mode needs local {' and '.join(missing)}, which could not be "
                "loaded. Install the voice dependencies from backend/requirements.txt."
            )
    return VoiceCapabilityResponse(
        enabled=True, stt_available=stt, vad_available=vad,
        tts_configured=bool(settings.elevenlabs_api_key), detail=detail,
    )


@router.post("/session", response_model=VoiceSessionResponse, status_code=201)
def open_session(
    request: VoiceSessionRequest,
    user_id: str = Depends(development_session),
    runtime_session: Session = Depends(get_db),
) -> VoiceSessionResponse:
    """Mint a socket token for the authenticated caller."""

    if not settings.voice_mode_enabled:
        raise HTTPException(status_code=503, detail="Voice mode is disabled.")

    # Fail here, not after the socket opens, so the UI can explain itself.
    if request.conversation_id is not None:
        from ..conversation_repository import ConversationRepository

        owned = ConversationRepository(runtime_session).get(
            request.conversation_id, user_id=user_id
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

    session = registry.create(
        user_id=user_id,
        conversation_id=request.conversation_id,
        workspace=request.workspace,
        project_key=request.project_key,
        dashboard_context=(
            request.dashboard_context.model_dump(mode="json", exclude_none=True)
            if request.dashboard_context
            else {}
        ),
    )
    return VoiceSessionResponse(
        session_token=session.token,
        expires_in_seconds=settings.voice_session_ttl_seconds,
        sample_rate=settings.voice_sample_rate,
        frame_bytes=VAD_FRAME_BYTES,
        end_silence_ms=settings.voice_end_silence_ms,
        max_utterance_seconds=settings.voice_max_utterance_seconds,
    )


@router.delete("/session/{token}", status_code=204)
def close_session(token: str, user_id: str = Depends(development_session)) -> None:
    """End a session early. Unknown tokens are a no-op, never a probe oracle."""

    session = registry.get(token)
    if session is not None and session.user_id == user_id:
        registry.close(token)


async def _send(socket: WebSocket, event: ServerEvent) -> None:
    await socket.send_text(event.dumps())


async def _set_state(socket: WebSocket, session: VoiceSession, target: VoiceState) -> None:
    if session.transition(target):
        await _send(socket, ServerEvent(type="state", state=target))


async def _speak(socket: WebSocket, session: VoiceSession, answer: str, turn_id: str) -> None:
    """Synthesise and stream the answer one segment at a time.

    Segments are requested lazily and the cancellation flag is checked before
    each one, so an interruption stops both the audio and any further
    ElevenLabs spend -- segments never requested are never billed.
    """

    segments = segment_for_speech(answer)
    if not segments:
        return
    await _send(
        socket,
        ServerEvent(type="assistant.audio_started", turn_id=turn_id, segments=segments),
    )
    await _set_state(socket, session, VoiceState.ASSISTANT_SPEAKING)

    for index, segment in enumerate(segments):
        if session.is_cancelled(turn_id):
            break
        try:
            # Each segment gets its own short-lived session: the quota rows are
            # committed per request, and holding one open across a long answer
            # would pin a connection for the whole turn.
            tts_session = SessionLocal()
            try:
                stream = await create_audio_stream(segment, tts_session)
                chunks = [chunk async for chunk in stream.chunks]
            finally:
                tts_session.close()
        except TTSQuotaExceededError as exc:
            await _send(socket, ServerEvent(type="error", detail=str(exc), recoverable=True))
            break
        except (TTSNotConfiguredError, TTSProviderError) as exc:
            await _send(socket, ServerEvent(type="error", detail=str(exc), recoverable=True))
            break
        except Exception:  # noqa: BLE001 - never leak provider internals
            logger.exception("Voice synthesis failed")
            await _send(
                socket,
                ServerEvent(
                    type="error", detail="The answer could not be spoken.", recoverable=True
                ),
            )
            break

        if session.is_cancelled(turn_id):
            break
        await socket.send_json(
            {
                "type": "assistant.audio_chunk",
                "turn_id": turn_id,
                "index": index,
                "mime": "audio/mpeg",
                "data": base64.b64encode(b"".join(chunks)).decode("ascii"),
            }
        )

    if session.is_cancelled(turn_id):
        await _send(socket, ServerEvent(type="assistant.interrupted", turn_id=turn_id))
        await _set_state(socket, session, VoiceState.INTERRUPTED)
    else:
        await _send(socket, ServerEvent(type="assistant.audio_finished", turn_id=turn_id))
    await _set_state(socket, session, VoiceState.LISTENING)


async def _handle_utterance(socket: WebSocket, session: VoiceSession, pcm: bytes) -> None:
    """Transcribe an utterance, answer it, and speak the answer."""

    turn_id = session.next_turn_id()
    await _set_state(socket, session, VoiceState.TRANSCRIBING)
    try:
        transcript = await asyncio.to_thread(transcribe_pcm, pcm)
    except VoiceModelUnavailable as exc:
        await _send(socket, ServerEvent(type="error", detail=str(exc), recoverable=False))
        await _set_state(socket, session, VoiceState.ERROR)
        return

    transcript = (transcript or "").strip()
    if not transcript:
        # Silence, a cough or a door. Never send an empty question to the agent.
        await _set_state(socket, session, VoiceState.LISTENING)
        return
    if session.is_cancelled(turn_id):
        await _set_state(socket, session, VoiceState.LISTENING)
        return

    await _send(socket, ServerEvent(type="transcript.final", turn_id=turn_id, text=transcript))
    await _send(socket, ServerEvent(type="assistant.thinking", turn_id=turn_id))
    await _set_state(socket, session, VoiceState.THINKING)

    def _turn() -> dict[str, Any]:
        # Its own database session: this runs in a worker thread, and a
        # SQLAlchemy session must not be shared across threads.
        runtime = SessionLocal()
        try:
            return run_chat_turn(
                runtime_session=runtime,
                user_id=session.user_id,
                message=transcript,
                conversation_id=session.conversation_id,
                workspace=session.workspace,
                project_key=session.project_key,
                dashboard_context=session.dashboard_context,
            )
        finally:
            runtime.close()

    try:
        result = await asyncio.to_thread(_turn)
    except ConversationNotFound:
        await _send(
            socket,
            ServerEvent(type="error", detail="That conversation is no longer available.", recoverable=False),
        )
        await _set_state(socket, session, VoiceState.ERROR)
        return
    except Exception:  # noqa: BLE001 - never leak internals over the socket
        logger.exception("Voice turn failed")
        await _send(
            socket,
            ServerEvent(
                type="error",
                detail="That question could not be answered just now.",
                recoverable=True,
            ),
        )
        await _set_state(socket, session, VoiceState.LISTENING)
        return

    # A DoraDB query cannot be safely killed once running, so an interrupted
    # turn is allowed to finish under its existing timeout and its result is
    # discarded here instead. The database safety timeout is never removed.
    if session.is_cancelled(turn_id):
        await _send(socket, ServerEvent(type="assistant.interrupted", turn_id=turn_id))
        await _set_state(socket, session, VoiceState.LISTENING)
        return

    metadata = result.get("metadata") or {}
    # Remember the conversation so the next utterance continues it rather than
    # starting a new one.
    if metadata.get("conversation_id") and session.conversation_id is None:
        from uuid import UUID as _UUID

        session.conversation_id = _UUID(str(metadata["conversation_id"]))

    await _send(
        socket,
        ServerEvent(
            type="assistant.text",
            turn_id=turn_id,
            text=result.get("answer") or "",
            conversation_id=str(metadata.get("conversation_id") or ""),
            message_id=str(metadata.get("message_id") or ""),
            chart=result.get("chart"),
            table=result.get("table"),
            warnings=list(result.get("warnings") or []),
        ),
    )
    await _speak(socket, session, result.get("answer") or "", turn_id)


@router.websocket("/session/{token}")
async def voice_socket(socket: WebSocket, token: str) -> None:
    """Drive one voice session: audio in, spoken governed answers out."""

    if not settings.voice_mode_enabled:
        await socket.close(code=CLOSE_FORBIDDEN, reason="Voice mode is disabled.")
        return
    # Browsers do not apply CORS to WebSockets, so Origin is checked by hand.
    if not origin_allowed(socket.headers.get("origin")):
        await socket.close(code=CLOSE_FORBIDDEN, reason="Origin not allowed.")
        return
    session = registry.get(token)
    if session is None:
        await socket.close(code=CLOSE_NOT_FOUND, reason="Voice session not found or expired.")
        return

    await socket.accept()
    try:
        load_vad()
    except VoiceModelUnavailable as exc:
        await _send(socket, ServerEvent(type="error", detail=str(exc), recoverable=False))
        await socket.close(code=CLOSE_UNAUTHORISED, reason="Voice models unavailable.")
        registry.close(token)
        return

    detector = UtteranceDetector()
    buffer = bytearray()
    pending = bytearray()
    speaking_turn: str | None = None

    await _send(
        socket,
        ServerEvent(type="session.ready", state=VoiceState.LISTENING, conversation_id=str(session.conversation_id or "")),
    )
    session.transition(VoiceState.LISTENING)

    try:
        while True:
            message = await socket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if (text := message.get("text")) is not None:
                try:
                    event = ClientEvent.model_validate_json(text)
                except ValidationError:
                    await _send(
                        socket,
                        ServerEvent(type="error", detail="Unrecognised voice event.", recoverable=True),
                    )
                    continue
                if event.type == "session.stop":
                    break
                if event.type == "response.cancel":
                    session.cancel(event.turn_id or speaking_turn)
                    await _set_state(socket, session, VoiceState.INTERRUPTED)
                continue

            chunk = message.get("bytes")
            if not chunk:
                continue
            pending.extend(chunk)

            # Silero needs exact frames; anything left over waits for more
            # audio. The whole message is scored in one worker call rather than
            # one hop per frame -- the hop overhead was larger than the
            # inference and showed up as lag before the assistant reacted.
            frames: list[bytes] = []
            while len(pending) >= VAD_FRAME_BYTES:
                frames.append(bytes(pending[:VAD_FRAME_BYTES]))
                del pending[:VAD_FRAME_BYTES]
            if not frames:
                continue
            try:
                scores = await asyncio.to_thread(speech_probabilities, frames)
            except VoiceModelUnavailable as exc:
                await _send(socket, ServerEvent(type="error", detail=str(exc), recoverable=False))
                return

            for frame, probability in zip(frames, scores):
                event = detector.feed(probability)
                if detector.speaking:
                    buffer.extend(frame)
                    if len(buffer) > MAX_UTTERANCE_BYTES:
                        event = "timeout"

                if event == "start":
                    buffer = bytearray(frame)
                    # Barge-in: speaking over the assistant cancels it here, on
                    # the server, as well as stopping playback in the browser.
                    if session.state == VoiceState.ASSISTANT_SPEAKING and speaking_turn:
                        session.cancel(speaking_turn)
                        await _send(
                            socket,
                            ServerEvent(type="assistant.interrupted", turn_id=speaking_turn),
                        )
                    await _set_state(socket, session, VoiceState.USER_SPEAKING)
                elif event in {"end", "timeout"}:
                    utterance = bytes(buffer)
                    buffer = bytearray()
                    if event == "timeout":
                        await _send(
                            socket,
                            ServerEvent(
                                type="error",
                                detail="That was longer than voice mode can handle in one turn.",
                                recoverable=True,
                            ),
                        )
                    speaking_turn = f"{session.token[:8]}-{session.turn + 1}"
                    await _handle_utterance(socket, session, utterance)
    except WebSocketDisconnect:
        logger.debug("Voice socket disconnected: %s", token[:8])
    except Exception:  # noqa: BLE001 - a socket failure must not take the app down
        logger.exception("Voice session failed")
    finally:
        # One place that always runs: the token dies with the socket.
        registry.close(token)
        try:
            await socket.close()
        except RuntimeError:  # pragma: no cover - already closed
            pass


__all__ = ["router"]
