import { useCallback, useEffect, useRef, useState } from "react";
import { VoiceTransport, fetchVoiceCapabilities } from "../services/realtimeVoice";

/**
 * Realtime voice session state for the UI.
 *
 * Holds only what the interface needs to render. Transcripts and answers are
 * handed to the caller so they land in the normal conversation — voice mode
 * must not keep a second copy of the chat.
 */

const INITIAL = {
  status: "idle", // idle | starting | active | error
  state: "idle", // server-reported voice state
  transcript: "",
  error: "",
  interrupted: false,
  turnId: null,
};

// Bounded, so a backend that is down cannot spin forever.
const MAX_RECONNECTS = 3;

export function useRealtimeVoiceSession({ onTranscript, onAnswer, sessionPayload } = {}) {
  const [voice, setVoice] = useState(INITIAL);
  const [capabilities, setCapabilities] = useState(null);
  const transportRef = useRef(null);
  const attemptsRef = useRef(0);
  const mountedRef = useRef(true);
  // Latest callbacks without re-creating the transport on every render.
  const handlersRef = useRef({ onTranscript, onAnswer, sessionPayload });
  handlersRef.current = { onTranscript, onAnswer, sessionPayload };

  useEffect(() => {
    fetchVoiceCapabilities()
      .then(setCapabilities)
      .catch(() => setCapabilities({ enabled: false, detail: "Voice mode is unavailable." }));
  }, []);

  const teardown = useCallback(async () => {
    const transport = transportRef.current;
    transportRef.current = null;
    if (transport) await transport.stop();
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      // Unmount must release the microphone, not merely stop rendering it.
      mountedRef.current = false;
      teardown();
    };
  }, [teardown]);

  const handleEvent = useCallback((event) => {
    if (!mountedRef.current) return;
    switch (event.type) {
      case "session.ready":
        setVoice((current) => ({ ...current, status: "active", state: "listening", error: "" }));
        break;
      case "state":
        setVoice((current) => ({
          ...current,
          state: event.state,
          // Clear the interrupted badge once a new turn is genuinely under way.
          interrupted: event.state === "interrupted" ? true : current.interrupted,
        }));
        break;
      case "transcript.partial":
        setVoice((current) => ({ ...current, transcript: event.text || "" }));
        break;
      case "transcript.final":
        setVoice((current) => ({
          ...current, transcript: event.text || "", turnId: event.turn_id, interrupted: false,
        }));
        handlersRef.current.onTranscript?.(event.text || "");
        break;
      case "assistant.text":
        handlersRef.current.onAnswer?.(event);
        break;
      case "assistant.interrupted":
        // The server detects barge-in too, from the microphone. When it is the
        // one that noticed, the browser is still holding queued audio for the
        // abandoned turn, so this has to stop playback — otherwise the
        // assistant keeps talking over someone who has already cut in.
        transportRef.current?.stopPlayback();
        setVoice((current) => ({ ...current, interrupted: true }));
        break;
      case "assistant.audio_started":
        setVoice((current) => ({ ...current, turnId: event.turn_id }));
        break;
      case "error":
        setVoice((current) => ({
          ...current,
          error: event.detail || "Voice mode hit a problem.",
          status: event.recoverable === false ? "error" : current.status,
        }));
        break;
      default:
        break;
    }
  }, []);

  const start = useCallback(async () => {
    if (transportRef.current) return;
    setVoice({ ...INITIAL, status: "starting" });
    const transport = new VoiceTransport({
      onEvent: handleEvent,
      onError: (failure) => {
        if (!mountedRef.current) return;
        attemptsRef.current += 1;
        setVoice((current) => ({
          ...current,
          status: attemptsRef.current >= MAX_RECONNECTS ? "error" : current.status,
          error: failure.message,
        }));
      },
    });
    transportRef.current = transport;
    try {
      await transport.start(handlersRef.current.sessionPayload || {});
      attemptsRef.current = 0;
    } catch (failure) {
      transportRef.current = null;
      await transport.stop().catch(() => {});
      if (!mountedRef.current) return;
      setVoice({
        ...INITIAL,
        status: "error",
        // A denied microphone is the common case and deserves its own wording.
        error:
          failure?.name === "NotAllowedError"
            ? "Microphone access was blocked. Allow it in your browser, then start voice again."
            : failure.message || "Voice mode could not be started.",
      });
    }
  }, [handleEvent]);

  const stop = useCallback(async () => {
    await teardown();
    if (mountedRef.current) setVoice(INITIAL);
  }, [teardown]);

  /** Stop the assistant immediately — the barge-in path. */
  const interrupt = useCallback(() => {
    transportRef.current?.interrupt(voice.turnId);
    setVoice((current) => ({ ...current, interrupted: true }));
  }, [voice.turnId]);

  return {
    ...voice,
    capabilities,
    available: Boolean(capabilities?.enabled && capabilities?.stt_available && capabilities?.vad_available),
    start,
    stop,
    interrupt,
    isActive: voice.status === "active" || voice.status === "starting",
  };
}

export default useRealtimeVoiceSession;
