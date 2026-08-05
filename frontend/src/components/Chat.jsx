import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Mic,
  MicOff,
  RotateCcw,
  Sparkles,
  Square,
  Volume2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import DataTable from "./DataTable";
import MetricChart from "./MetricChart";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const SESSION_KEY = "dora-copilot-session";
const ROLE_STORAGE_KEY = "echo-selected-role";
const ROLE_CAPABILITIES = {
  technical: [
    { icon: "📊", title: "Sprint Health", description: "Investigate delivery flow and sprint-level signals." },
    {
      icon: "🚀",
      title: "Deployment Trends",
      description: "Explore release cadence and changes over time.",
    },
    {
      icon: "⚠️",
      title: "Engineering Bottlenecks",
      description: "Surface bottlenecks and evidence-backed delivery risks.",
    },
    {
      icon: "🤖",
      title: "AI Recommendations",
      description: "Generate prioritized actions from validated metrics.",
    },
  ],
  business: [
    {
      icon: "📈",
      title: "Executive Summary",
      description: "Translate delivery evidence into decision-ready summaries.",
    },
    {
      icon: "💰",
      title: "Productivity",
      description: "Understand delivery trends and team-level performance.",
    },
    { icon: "⚠️", title: "Delivery Risks", description: "Identify material delivery risks and supporting evidence." },
    {
      icon: "💡",
      title: "Management Recommendations",
      description: "Turn findings into clear management priorities.",
    },
  ],
};

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  text:
    "Hello — I’m your **DeepSeek-powered DoraDB agent**. Ask about your delivery data in your own words. I retrieve and validate read-only evidence, then the AI interprets it for your exact question.",
};

function createSessionId() {
  if (typeof window === "undefined") return `session-${Date.now()}`;
  const existing = window.localStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const id = window.crypto?.randomUUID?.() || `session-${Date.now()}-${Math.random()}`;
  window.localStorage.setItem(SESSION_KEY, id);
  return id;
}

function makeMessage(role, text, extras = {}) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    ...extras,
  };
}

function readSelectedRole() {
  if (typeof window === "undefined") return "technical";
  return window.localStorage.getItem(ROLE_STORAGE_KEY) === "business"
    ? "business"
    : "technical";
}

export default function Chat({ projects, databaseConnected }) {
  const [messages, setMessages] = useState([welcomeMessage]);
  const [input, setInput] = useState("");
  const [selectedRole] = useState(readSelectedRole);
  const [project, setProject] = useState("");
  const [sessionId, setSessionId] = useState(createSessionId);
  const [isSending, setIsSending] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [speechError, setSpeechError] = useState("");
  const [speakingId, setSpeakingId] = useState(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);
  const audioRef = useRef(null);
  const audioRequestControllerRef = useRef(null);
  const audioUrlCacheRef = useRef(new Map());

  const SpeechRecognition =
    typeof window !== "undefined" &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, isSending]);

  useEffect(() => {
    if (projects.length && !projects.some((item) => item.key === project)) {
      setProject(projects[0].key);
    }
  }, [project, projects]);

  useEffect(
    () => () => {
      recognitionRef.current?.stop();
      audioRequestControllerRef.current?.abort();
      audioRef.current?.pause();
      for (const url of audioUrlCacheRef.current.values()) URL.revokeObjectURL(url);
      audioUrlCacheRef.current.clear();
    },
    [],
  );

  async function sendMessage(rawText) {
    const text = rawText.trim();
    if (!text || isSending) return;
    const history = messages
      .filter((message) => message.id !== "welcome" && !message.error)
      .slice(-12)
      .map((message) => ({ role: message.role, content: message.text }));

    setMessages((current) => [...current, makeMessage("user", text)]);
    setInput("");
    setSpeechError("");
    setIsSending(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          project_key: project || null,
          history,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Request failed with status ${response.status}`);
      }
      const payload = await response.json();
      setMessages((current) => [
        ...current,
        makeMessage("assistant", payload.answer, {
          chart: payload.chart,
          table: payload.table,
          warnings: payload.warnings,
          validation: payload.validation,
          metadata: payload.metadata,
        }),
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        makeMessage(
          "assistant",
          `I couldn’t complete that request. ${error.message}`,
          { error: true },
        ),
      ]);
    } finally {
      setIsSending(false);
    }
  }

  async function clearConversation() {
    stopAudio();
    try {
      await fetch(`${API_BASE}/api/reset-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {
      // Clearing local history remains useful even when the backend is offline.
    }
    const nextId = window.crypto?.randomUUID?.() || `session-${Date.now()}`;
    window.localStorage.setItem(SESSION_KEY, nextId);
    setSessionId(nextId);
    setMessages([welcomeMessage]);
    setInput("");
    setSpeechError("");
  }

  function toggleListening() {
    setSpeechError("");
    if (!SpeechRecognition) {
      setSpeechError("Voice input is not supported here. Chrome and Edge work best.");
      return;
    }
    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => {
      setInput(
        Array.from(event.results)
          .map((result) => result[0].transcript)
          .join(""),
      );
    };
    recognition.onerror = (event) => {
      setSpeechError(
        event.error === "not-allowed"
          ? "Microphone permission was denied."
          : "Voice input stopped unexpectedly.",
      );
    };
    recognition.onend = () => setIsListening(false);
    recognitionRef.current = recognition;
    recognition.start();
  }

  function stopAudio() {
    audioRequestControllerRef.current?.abort();
    audioRequestControllerRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    setSpeakingId(null);
  }

  async function speak(message) {
    if (speakingId === message.id) {
      stopAudio();
      return;
    }
    stopAudio();
    setSpeechError("");
    setSpeakingId(message.id);
    try {
      let audioUrl = audioUrlCacheRef.current.get(message.id);
      if (!audioUrl) {
        const controller = new AbortController();
        audioRequestControllerRef.current = controller;
        const plainText = message.text
          .replace(/\[(.*?)\]\(.*?\)/g, "$1")
          .replace(/[#*_`>|[\]]/g, " ")
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 2000);
        const response = await fetch(`${API_BASE}/api/tts`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: plainText }),
          signal: controller.signal,
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || `Voice request failed with status ${response.status}`);
        }
        audioUrl = URL.createObjectURL(await response.blob());
        audioUrlCacheRef.current.set(message.id, audioUrl);
        audioRequestControllerRef.current = null;
      }
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      audio.onended = stopAudio;
      audio.onerror = () => {
        setSpeechError("The generated audio could not be played.");
        stopAudio();
      };
      await audio.play();
    } catch (error) {
      if (error.name === "AbortError") return;
      setSpeechError(`Voice playback unavailable: ${error.message}`);
      stopAudio();
    }
  }

  const isEmpty = !messages.some((message) => message.role === "user");
  const capabilities = ROLE_CAPABILITIES[selectedRole];
  const emptyQuestion =
    selectedRole === "business"
      ? "What business insight are you looking for today?"
      : "What would you like to analyse today?";
  const inputPlaceholder =
    selectedRole === "business"
      ? "Ask about executive summaries, KPIs or engineering performance..."
      : "Ask about DORA metrics, sprint performance, deployment trends...";

  return (
    <div className={`chat-panel chat-panel-workspace ${isEmpty ? "chat-panel-empty" : ""}`}>
      <aside className="empty-chat-sidebar" aria-label="Recent conversations">
        <div>
          <p>Workspace</p>
          <h3>Recent Conversations</h3>
        </div>
        <div className="empty-chat-sidebar-note">
          <Sparkles size={16} aria-hidden="true" />
          <div>
            <strong>New conversation</strong>
            <span>Your recent chats will appear here.</span>
          </div>
        </div>
        <span className="empty-chat-role-label">{selectedRole} workspace</span>
      </aside>
      <div className="chat-toolbar">
        <div className="project-picker">
          <label htmlFor="project-select">Project scope</label>
          <div className="select-wrap">
            <select
              id="project-select"
              value={project}
              onChange={(event) => setProject(event.target.value)}
            >
              {projects.map((item) => (
                <option key={item.key || "all"} value={item.key}>
                  {item.label} · {item.detail}
                </option>
              ))}
            </select>
            <ChevronDown size={16} aria-hidden="true" />
          </div>
        </div>
        <div className="toolbar-actions">
          <span className="data-freshness">
            <CheckCircle2 size={15} />
            {databaseConnected ? "DoraDB ready" : "DoraDB credentials required"}
          </span>
          <button className="clear-button" type="button" onClick={clearConversation}>
            <RotateCcw size={15} /> Clear conversation
          </button>
        </div>
      </div>

      <div className="message-list" aria-live="polite">
        <section
          className={`empty-chat-state ${isEmpty ? "" : "is-hidden"}`}
          aria-hidden={!isEmpty}
        >
          <header className="empty-chat-greeting">
            <p>Hello <span aria-hidden="true">👋</span></p>
            <h3>{emptyQuestion}</h3>
          </header>
          <div className="empty-chat-suggestions">
            <p>Workspace capabilities</p>
            <div className="suggestion-card-grid">
              {capabilities.map((capability, index) => (
                <article
                  className="suggestion-card"
                  key={capability.title}
                  style={{ "--suggestion-index": index }}
                >
                  <span className="suggestion-icon" aria-hidden="true">
                    {capability.icon}
                  </span>
                  <span className="suggestion-copy">
                    <strong>{capability.title}</strong>
                    <span>{capability.description}</span>
                  </span>
                </article>
              ))}
            </div>
          </div>
        </section>

        <div className={`conversation-intro ${isEmpty ? "empty-chat-existing-hidden" : ""}`}>
          <span className="intro-icon"><Sparkles size={25} /></span>
          <div>
            <h3>Your delivery intelligence agent</h3>
            <p>Type or speak your question naturally. There is no required prompt template.</p>
          </div>
        </div>

        {messages.map((message) => (
          <article
            className={`message ${message.role} ${message.error ? "message-error" : ""} ${isEmpty ? "empty-chat-existing-hidden" : ""}`}
            key={message.id}
          >
            <div className="message-avatar" aria-hidden="true">
              {message.role === "assistant" ? "AI" : "YOU"}
            </div>
            <div className="message-body">
              <div className="message-meta">
                <span>{message.role === "assistant" ? "DORA Copilot" : "You"}</span>
                {message.role === "assistant" && (
                  <button
                    className="speak-button"
                    type="button"
                    onClick={() => speak(message)}
                    aria-label={speakingId === message.id ? "Stop speaking" : "Read response aloud"}
                  >
                    {speakingId === message.id ? <Square size={13} /> : <Volume2 size={15} />}
                  </button>
                )}
              </div>
              <div className="message-content">
                <ReactMarkdown>{message.text}</ReactMarkdown>
              </div>
              {message.warnings?.length > 0 && (
                <div className="warning-panel">
                  <CircleAlert size={17} />
                  <div>
                    <strong>Data note</strong>
                    {message.warnings.map((warning) => <p key={warning}>{warning}</p>)}
                  </div>
                </div>
              )}
              <MetricChart chart={message.chart} />
              <DataTable table={message.table} />
              {message.role === "assistant" && message.metadata?.analysis_steps > 0 && (
                <div className="analysis-proof">
                  <ShieldCheckIcon />
                  <span>
                    {message.metadata.answer_source === "ai-provider-unavailable"
                      ? "DeepSeek unavailable · no template substituted"
                      : "Analyzed from DoraDB · AI answer checked"}
                  </span>
                </div>
              )}
            </div>
          </article>
        ))}

        {isSending && (
          <div className="thinking" role="status">
            <span /><span /><span />
            <p>DeepSeek is reasoning, querying when needed, and validating the answer…</p>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="composer-wrap">
        {speechError && <p className="speech-error" role="alert">{speechError}</p>}
        <form className="composer" onSubmit={(event) => {
          event.preventDefault();
          sendMessage(input);
        }}>
          <textarea
            ref={inputRef}
            aria-label="Ask about your delivery metrics"
            placeholder={inputPlaceholder}
            rows="1"
            value={input}
            maxLength={2000}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage(input);
              }
            }}
          />
          <button
            className={`voice-button ${isListening ? "listening" : ""}`}
            type="button"
            onClick={toggleListening}
            aria-label={isListening ? "Stop voice input" : "Start voice input"}
          >
            {isListening ? <MicOff size={20} /> : <Mic size={20} />}
          </button>
          <button
            className="send-button"
            type="submit"
            disabled={!input.trim() || isSending}
            aria-label="Send message"
          >
            <ArrowUp size={20} />
          </button>
        </form>
        <p className="composer-hint">
          Enter to send · Shift + Enter for a new line · Follow-ups use structured session memory
        </p>
      </div>
    </div>
  );
}

function ShieldCheckIcon() {
  return <CheckCircle2 size={14} aria-hidden="true" />;
}
