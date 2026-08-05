import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  AlertTriangle,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Database,
  Focus,
  Gauge,
  Mic,
  MicOff,
  Plus,
  RotateCcw,
  Sparkles,
  Square,
  Table2,
  Users,
  Volume2,
  Workflow,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import DataTable from "./DataTable";
import MetricChart from "./MetricChart";
import JiraDeliveryOverview from "./JiraDeliveryOverview";
import { WORKSPACE_PLACEHOLDERS, WORKSPACE_SUGGESTIONS } from "../workspaceSuggestions";
import {
  ACTIVE_CONVERSATION_KEY,
  archiveConversation,
  getConversation,
  listConversations,
  messagesFromConversation,
  sendChat,
} from "../services/conversations";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  text:
    "Hello. I’m your **ECHO DORA Copilot**. Ask about delivery data, Jira reporting, or DORA definitions in your own words.",
};

function makeMessage(role, text, extras = {}) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    ...extras,
  };
}

const SUGGESTION_ICONS = {
  alert: AlertTriangle,
  briefcase: BriefcaseBusiness,
  database: Database,
  focus: Focus,
  gauge: Gauge,
  table: Table2,
  users: Users,
  workflow: Workflow,
};

export default function Chat({
  projects = [],
  databaseConnected = false,
  selectedRole = "technical",
  onWorkspaceChange,
}) {
  const [messages, setMessages] = useState([welcomeMessage]);
  const [input, setInput] = useState("");
  const [project, setProject] = useState("");
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [conversationStatus, setConversationStatus] = useState("loading");
  const [conversationError, setConversationError] = useState("");
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

  useEffect(() => {
    let active = true;
    async function restore() {
      setConversationStatus("loading");
      try {
        const payload = await listConversations();
        if (!active) return;
        const recent = payload.conversations || [];
        setConversations(recent);
        setConversationStatus("ready");
        const savedId = window.localStorage.getItem(ACTIVE_CONVERSATION_KEY);
        if (savedId && recent.some((item) => item.id === savedId)) {
          await openConversation(savedId);
        }
      } catch (error) {
        if (!active) return;
        setConversationError(error.message);
        setConversationStatus("error");
      }
    }
    restore();
    return () => { active = false; };
  }, []);

  async function loadRecent() {
    try {
      const payload = await listConversations();
      setConversations(payload.conversations || []);
      setConversationStatus("ready");
      setConversationError("");
    } catch (error) {
      setConversationError(error.message);
      setConversationStatus("error");
    }
  }

  async function openConversation(id) {
    setConversationStatus("loading");
    try {
      const conversation = await getConversation(id);
      setActiveConversationId(conversation.id);
      window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversation.id);
      setMessages(messagesFromConversation(conversation));
      setProject(conversation.project_scope?.project_key || "");
      onWorkspaceChange?.(conversation.workspace);
      setConversationStatus("ready");
      setConversationError("");
    } catch (error) {
      setConversationError(error.message);
      setConversationStatus("error");
    }
  }

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
      const payload = await sendChat({
        message: text,
        conversation_id: activeConversationId,
        workspace: selectedRole,
        project_key: project || null,
        history,
      });
      const conversationId = payload.metadata?.conversation_id;
      if (conversationId && conversationId !== activeConversationId) {
        setActiveConversationId(conversationId);
        window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
      }
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
      await loadRecent();
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
    if (activeConversationId) {
      const confirmed = window.confirm("Archive this conversation? Other recent conversations will remain available.");
      if (!confirmed) return;
      try {
        await archiveConversation(activeConversationId);
        await loadRecent();
      } catch (error) {
        setConversationError(error.message);
        setConversationStatus("error");
        return;
      }
    }
    startNewConversation();
  }

  function startNewConversation() {
    stopAudio();
    window.localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
    setActiveConversationId(null);
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
  const suggestions = WORKSPACE_SUGGESTIONS[selectedRole] || WORKSPACE_SUGGESTIONS.technical;
  const inputPlaceholder = WORKSPACE_PLACEHOLDERS[selectedRole] || WORKSPACE_PLACEHOLDERS.technical;

  return (
    <div className={`chat-panel chat-panel-workspace ${isEmpty ? "chat-panel-empty" : ""}`}>
      <aside className="empty-chat-sidebar" aria-label="Recent conversations">
        <div>
          <p>Workspace</p>
          <h3>Recent Conversations</h3>
        </div>
        <button className="empty-chat-sidebar-note" type="button" onClick={startNewConversation}>
          <Plus size={16} aria-hidden="true" />
          <div><strong>New conversation</strong><span>Start with a clean context.</span></div>
        </button>
        <div className="recent-conversation-list">
          {conversationStatus === "loading" && <p role="status">Loading conversations...</p>}
          {conversationStatus === "error" && (
            <div className="recent-conversation-error" role="alert">
              <span>{conversationError}</span>
              <button type="button" onClick={loadRecent}>Retry</button>
            </div>
          )}
          {conversationStatus === "ready" && conversations.length === 0 && (
            <p>No saved conversations yet.</p>
          )}
          {conversations.map((conversation) => (
            <button
              className={conversation.id === activeConversationId ? "active" : ""}
              key={conversation.id}
              type="button"
              onClick={() => openConversation(conversation.id)}
              aria-current={conversation.id === activeConversationId ? "page" : undefined}
            >
              <strong>{conversation.title}</strong>
              <span>{conversation.workspace} workspace</span>
            </button>
          ))}
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
            <p>Hello, Aisyah</p>
            <h3>What are you looking for today?</h3>
          </header>
          <JiraDeliveryOverview
            projectKey={project}
            onPrompt={sendMessage}
            disabled={isSending}
          />
          <div className="empty-chat-suggestions">
            <p>Suggested Questions</p>
            <div className="suggestion-card-grid">
              {suggestions.map((suggestion, index) => (
                (() => {
                  const SuggestionIcon = SUGGESTION_ICONS[suggestion.icon];
                  return <button
                  key={suggestion.title}
                  type="button"
                  style={{ "--suggestion-index": index }}
                  onClick={() => sendMessage(suggestion.prompt)}
                  disabled={isSending}
                  aria-label={`${suggestion.title}: ${suggestion.description}`}
                >
                  <span className="suggestion-icon" aria-hidden="true">
                    <SuggestionIcon size={20} />
                  </span>
                  <span className="suggestion-copy">
                    <strong>{suggestion.title}</strong>
                    <span>{suggestion.description}</span>
                  </span>
                </button>;
                })()
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
                      ? "Google AI Studio unavailable · no template substituted"
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
            <p>ECHO is reasoning, querying when needed, and validating the answer...</p>
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
