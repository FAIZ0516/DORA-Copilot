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

The turn itself also runs as a background task rather than being awaited inside
the receive loop. That matters for correctness, not just responsiveness: the
browser streams audio continuously, so a loop that stops reading while the
assistant thinks and speaks accumulates that whole period in the socket buffer
and then replays it as if it had just been spoken.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections import deque
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
    VAD_FRAME_SAMPLES,
    SileroVad,
    UtteranceDetector,
    VoiceModelUnavailable,
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


class _Sender:
    """Serialises socket writes.

    The receive loop and the in-flight turn both send, and concurrent writes to
    one WebSocket interleave frames and corrupt the stream.
    """

    def __init__(self, socket: WebSocket) -> None:
        self._socket = socket
        self._lock = asyncio.Lock()

    async def event(self, event: ServerEvent) -> None:
        async with self._lock:
            await self._socket.send_text(event.dumps())

    async def json(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            await self._socket.send_json(payload)


async def _send(sender: _Sender, event: ServerEvent) -> None:
    await sender.event(event)


async def _set_state(sender: _Sender, session: VoiceSession, target: VoiceState) -> None:
    if session.transition(target):
        await _send(sender, ServerEvent(type="state", state=target))


async def _speak(sender: _Sender, session: VoiceSession, answer: str, turn_id: str) -> None:
    """Synthesise and stream the answer one segment at a time.

    Segments are requested lazily and the cancellation flag is checked before
    each one, so an interruption stops both the audio and any further
    ElevenLabs spend -- segments never requested are never billed.
    """

    segments = segment_for_speech(answer)
    if not segments:
        return
    await _send(
        sender,
        ServerEvent(type="assistant.audio_started", turn_id=turn_id, segments=segments),
    )
    await _set_state(sender, session, VoiceState.ASSISTANT_SPEAKING)

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
            await _send(sender, ServerEvent(type="error", detail=str(exc), recoverable=True))
            break
        except (TTSNotConfiguredError, TTSProviderError) as exc:
            await _send(sender, ServerEvent(type="error", detail=str(exc), recoverable=True))
            break
        except Exception:  # noqa: BLE001 - never leak provider internals
            logger.exception("Voice synthesis failed")
            await _send(
                sender,
                ServerEvent(
                    type="error", detail="The answer could not be spoken.", recoverable=True
                ),
            )
            break

        if session.is_cancelled(turn_id):
            break
        await sender.json(
            {
                "type": "assistant.audio_chunk",
                "turn_id": turn_id,
                "index": index,
                "mime": "audio/mpeg",
                "data": base64.b64encode(b"".join(chunks)).decode("ascii"),
            }
        )

    if session.is_cancelled(turn_id):
        await _send(sender, ServerEvent(type="assistant.interrupted", turn_id=turn_id))
        await _set_state(sender, session, VoiceState.INTERRUPTED)
    else:
        await _send(sender, ServerEvent(type="assistant.audio_finished", turn_id=turn_id))
    await _set_state(sender, session, VoiceState.LISTENING)


async def _handle_utterance(sender: _Sender, session: VoiceSession, pcm: bytes) -> None:
    """Transcribe an utterance, answer it, and speak the answer."""

    turn_id = session.next_turn_id()
    session.active_turn = turn_id
    await _set_state(sender, session, VoiceState.TRANSCRIBING)
    try:
        transcript = await asyncio.to_thread(transcribe_pcm, pcm)
    except VoiceModelUnavailable as exc:
        await _send(sender, ServerEvent(type="error", detail=str(exc), recoverable=False))
        await _set_state(sender, session, VoiceState.ERROR)
        return

    transcript = (transcript or "").strip()
    if not transcript:
        # Silence, a cough or a door. Never send an empty question to the agent.
        await _set_state(sender, session, VoiceState.LISTENING)
        return
    if session.is_cancelled(turn_id):
        await _set_state(sender, session, VoiceState.LISTENING)
        return

    await _send(sender, ServerEvent(type="transcript.final", turn_id=turn_id, text=transcript))
    await _send(sender, ServerEvent(type="assistant.thinking", turn_id=turn_id))
    await _set_state(sender, session, VoiceState.THINKING)

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
            sender,
            ServerEvent(type="error", detail="That conversation is no longer available.", recoverable=False),
        )
        await _set_state(sender, session, VoiceState.ERROR)
        return
    except Exception:  # noqa: BLE001 - never leak internals over the socket
        logger.exception("Voice turn failed")
        await _send(
            sender,
            ServerEvent(
                type="error",
                detail="That question could not be answered just now.",
                recoverable=True,
            ),
        )
        await _set_state(sender, session, VoiceState.LISTENING)
        return

    # A DoraDB query cannot be safely killed once running, so an interrupted
    # turn is allowed to finish under its existing timeout and its result is
    # discarded here instead. The database safety timeout is never removed.
    if session.is_cancelled(turn_id):
        await _send(sender, ServerEvent(type="assistant.interrupted", turn_id=turn_id))
        await _set_state(sender, session, VoiceState.LISTENING)
        return

    metadata = result.get("metadata") or {}
    # Remember the conversation so the next utterance continues it rather than
    # starting a new one.
    if metadata.get("conversation_id") and session.conversation_id is None:
        from uuid import UUID as _UUID

        session.conversation_id = _UUID(str(metadata["conversation_id"]))

    await _send(
        sender,
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
    await _speak(sender, session, result.get("answer") or "", turn_id)


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
    sender = _Sender(socket)
    try:
        # Its own detector. Silero is recurrent, and a shared one would let two
        # simultaneous conversations interleave their audio through one state.
        vad = SileroVad()
    except VoiceModelUnavailable as exc:
        await _send(sender, ServerEvent(type="error", detail=str(exc), recoverable=False))
        await socket.close(code=CLOSE_UNAUTHORISED, reason="Voice models unavailable.")
        registry.close(token)
        return

    detector = UtteranceDetector()
    # A second, deliberately harder-to-trigger detector used only while the
    # assistant holds the floor. Interrupting takes sustained speech; a stray
    # frame of the assistant's own voice returning through the speakers does
    # not clear this bar.
    barge_in = UtteranceDetector(start_speech_ms=float(settings.voice_barge_in_ms))
    buffer = bytearray()
    pending = bytearray()
    # A rolling window of the frames just gone, so an utterance can begin
    # slightly before the detector noticed it.
    recent: deque[bytes] = deque(
        maxlen=max(1, int(settings.voice_preroll_ms / (VAD_FRAME_SAMPLES / settings.voice_sample_rate * 1000)))
    )
    turn_task: asyncio.Task[None] | None = None
    deaf_until = 0.0
    audio_bytes = 0
    # Whether the turn now finishing was cut short by the user rather than
    # ending on its own. It decides whether the echo guard applies.
    cut_in = False

    def busy() -> bool:
        return turn_task is not None and not turn_task.done()

    await _send(
        sender,
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
                        sender,
                        ServerEvent(type="error", detail="Unrecognised voice event.", recoverable=True),
                    )
                    continue
                if event.type == "session.stop":
                    break
                if event.type == "response.cancel":
                    session.cancel(event.turn_id or session.active_turn)
                    await _set_state(sender, session, VoiceState.INTERRUPTED)
                continue

            chunk = message.get("bytes")
            if not chunk:
                continue
            audio_bytes += len(chunk)

            # A turn that has just finished leaves the room echoing and the
            # detectors mid-utterance. Start the next one from silence.
            if turn_task is not None and turn_task.done():
                turn_task = None
                session.active_turn = None
                detector.reset()
                barge_in.reset()
                vad.reset()
                buffer.clear()
                pending.clear()
                if not cut_in:
                    # Silence and echo, not a run-up to anything.
                    recent.clear()
                # Only wait out the echo if the assistant finished on its own.
                # A turn the user cut into ends with them mid-sentence, and
                # staying deaf through it clipped the front of what they said --
                # "no, stop, show me MBK instead" arrived as "instead please".
                # There is also nothing left to guard against: cancelling
                # stopped the synthesis and the browser's playback with it.
                if not cut_in:
                    deaf_until = time.monotonic() + settings.voice_echo_guard_ms / 1000
                cut_in = False

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
                scores = await asyncio.to_thread(vad.probabilities, frames)
            except VoiceModelUnavailable as exc:
                await _send(sender, ServerEvent(type="error", detail=str(exc), recoverable=False))
                return

            for frame, probability in zip(frames, scores):
                # While the assistant is transcribing, thinking or speaking,
                # nothing arriving here is a question. It is room noise, or the
                # assistant's own voice coming back through the speakers.
                # Transcribing it is what produced answers to things nobody
                # said. The only thing worth detecting now is a real
                # interruption.
                if busy():
                    # Once the user has cut in, what follows is them talking,
                    # and the turn takes a moment to wind down. Keeping those
                    # frames is what preserves the front of the interruption.
                    if cut_in:
                        recent.append(frame)
                    else:
                        recent.clear()

                    # Only speech over the assistant's actual voice is an
                    # interruption. While it is transcribing or thinking there
                    # is nothing to interrupt and the user is waiting for an
                    # answer -- treating a cough or a passing remark as a
                    # barge-in there cancels the turn and they never get one.
                    # Thinking can run tens of seconds, so that window is wide.
                    if session.state != VoiceState.ASSISTANT_SPEAKING:
                        # Reset rather than accumulate, or noise from the wait
                        # would cancel the answer the moment it started.
                        barge_in.reset()
                    elif barge_in.feed(probability) == "start":
                        barge_in.reset()
                        interrupted = session.active_turn
                        if interrupted:
                            session.cancel(interrupted)
                            await _send(
                                sender,
                                ServerEvent(type="assistant.interrupted", turn_id=interrupted),
                            )
                        # The audio that triggered this is discarded rather than
                        # kept as the start of a question: at this exact moment
                        # the assistant is still audible, so it is the least
                        # trustworthy audio in the session. The speaker is still
                        # talking, and the next frames start their utterance
                        # cleanly.
                        detector.reset()
                        buffer.clear()
                        cut_in = True
                    continue

                # The assistant has just stopped; let the room fall quiet.
                if time.monotonic() < deaf_until:
                    continue

                event = detector.feed(probability)
                if event == "start":
                    # Start the utterance with the audio from just before it was
                    # detected. Silero has to hear speech before it can report
                    # it, so by the time it does, the first syllable is already
                    # behind us -- that is where the missing first words went.
                    buffer = bytearray(b"".join(recent))
                    buffer.extend(frame)
                    recent.clear()
                    await _set_state(sender, session, VoiceState.USER_SPEAKING)
                    continue

                if detector.speaking:
                    buffer.extend(frame)
                    if len(buffer) > MAX_UTTERANCE_BYTES:
                        event = "timeout"
                else:
                    recent.append(frame)

                if event in {"end", "timeout"}:
                    utterance = bytes(buffer)
                    buffer = bytearray()
                    if event == "timeout":
                        await _send(
                            sender,
                            ServerEvent(
                                type="error",
                                detail="That was longer than voice mode can handle in one turn.",
                                recoverable=True,
                            ),
                        )
                    # Answered in the background so this loop keeps reading the
                    # microphone. Awaiting it here is what let a whole turn's
                    # worth of audio queue up and then be replayed as speech.
                    turn_task = asyncio.create_task(
                        _handle_utterance(sender, session, utterance)
                    )
    except WebSocketDisconnect:
        logger.debug("Voice socket disconnected: %s", token[:8])
    except Exception:  # noqa: BLE001 - a socket failure must not take the app down
        logger.exception("Voice session failed")
    finally:
        if not audio_bytes:
            # A session that opened, sat there and closed without a single
            # frame. Silent on both sides, and indistinguishable from the
            # assistant ignoring the user, so it gets said out loud.
            logger.warning(
                "Voice session %s received no audio at all -- microphone capture "
                "never started in the browser.",
                token[:8],
            )
        # One place that always runs: the token dies with the socket.
        if turn_task is not None and not turn_task.done():
            turn_task.cancel()
        registry.close(token)
        try:
            await socket.close()
        except RuntimeError:  # pragma: no cover - already closed
            pass


__all__ = ["router"]
