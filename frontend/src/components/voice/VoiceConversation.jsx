import { Loader2, Mic, MicOff, Radio, Square, TriangleAlert } from "lucide-react";
import useRealtimeVoiceSession from "../../hooks/useRealtimeVoiceSession";

/**
 * Hands-free voice conversation.
 *
 * One click starts it and the microphone stays open: speech is detected,
 * transcribed and submitted automatically, and the answer is spoken back.
 * Speaking over the assistant stops it immediately. The text composer stays
 * available throughout, so this is an addition to the chat rather than a mode
 * the user can get stuck in.
 */

const STATE_LABEL = {
  idle: "Ready",
  listening: "Listening",
  user_speaking: "You're speaking",
  transcribing: "Getting that down",
  thinking: "Thinking",
  assistant_speaking: "Zara is speaking",
  interrupted: "Stopped — go ahead",
  error: "Voice problem",
  closed: "Ended",
};

export default function VoiceConversation({ onTranscript, onAnswer, sessionPayload }) {
  const voice = useRealtimeVoiceSession({ onTranscript, onAnswer, sessionPayload });
  const { capabilities } = voice;

  // Unavailable is a normal outcome, not an error: the text composer is right
  // there, so say what is missing and stay out of the way.
  if (capabilities && !voice.available) {
    return (
      <div className="voice-panel voice-panel--unavailable" role="status">
        <MicOff aria-hidden="true" />
        <p>
          {capabilities.detail || "Voice conversation is not available on this server."}{" "}
          You can still type your question below.
        </p>
      </div>
    );
  }

  const busy = voice.status === "starting";
  const speaking = voice.state === "assistant_speaking";

  return (
    <section className={`voice-panel voice-panel--${voice.state}`} aria-label="Voice conversation">
      <div className="voice-panel-status">
        <span className={`voice-indicator voice-indicator--${voice.state}`} aria-hidden="true">
          {voice.state === "thinking" || voice.state === "transcribing" ? (
            <Loader2 className="is-spinning" />
          ) : (
            <Radio />
          )}
        </span>
        <div>
          <strong aria-live="polite">{STATE_LABEL[voice.state] || "Ready"}</strong>
          {voice.transcript ? (
            <p className="voice-transcript" aria-live="polite">“{voice.transcript}”</p>
          ) : (
            <p className="voice-hint">
              {voice.isActive
                ? "Just speak — there is no send button. Talk over Zara to interrupt."
                : "Start a voice conversation and speak naturally."}
            </p>
          )}
        </div>
      </div>

      {voice.interrupted && (
        <p className="voice-flag" role="status">
          <TriangleAlert aria-hidden="true" /> Zara was interrupted.
        </p>
      )}

      {voice.error && (
        <p className="voice-flag voice-flag--error" role="alert">
          <TriangleAlert aria-hidden="true" /> {voice.error}
        </p>
      )}

      <div className="voice-panel-actions">
        {voice.isActive ? (
          <>
            <button type="button" className="voice-stop" onClick={voice.stop}>
              <Square aria-hidden="true" /> End voice conversation
            </button>
            {/* An explicit stop for anyone who would rather not talk over her. */}
            <button
              type="button"
              onClick={voice.interrupt}
              disabled={!speaking}
              aria-label="Stop Zara speaking"
            >
              <MicOff aria-hidden="true" /> Stop speaking
            </button>
          </>
        ) : (
          <button type="button" className="voice-start" onClick={voice.start} disabled={busy}>
            {busy ? <Loader2 className="is-spinning" aria-hidden="true" /> : <Mic aria-hidden="true" />}
            {busy ? "Starting…" : "Start voice conversation"}
          </button>
        )}
      </div>
    </section>
  );
}
