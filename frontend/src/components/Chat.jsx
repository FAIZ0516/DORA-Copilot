import { useEffect, useRef, useState } from "react";
import { ArrowUp, CheckCircle2, CircleAlert, Copy, Mic, MicOff, RefreshCw, RotateCcw, Sparkles, Square, Volume2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import DataTable from "./DataTable";
import MetricChart from "./MetricChart";
import RoleDashboard from "./RoleDashboard";
import SuggestedQuestionChips from "./chat/SuggestedQuestionChips";
import ConversationPanel from "./history/ConversationPanel";
import ThreePanelWorkspace from "./layout/ThreePanelWorkspace";
import { getRoleDashboardConfig } from "../config/roleDashboardConfig";
import { useDashboardContext } from "../dashboardContext";
import { usePanelLayout } from "../hooks/usePanelLayout";
import { WORKSPACE_PLACEHOLDERS } from "../workspaceSuggestions";
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
  text: "Hello. I’m **Zara**, your delivery analysis and reporting assistant. Ask about the selected dashboard, delivery risks, Jira evidence, or management reporting in your own words.",
};

function makeMessage(role, text, extras = {}) {
  return { id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, role, text, createdAt: new Date().toISOString(), ...extras };
}

export default function Chat({
  projects = [],
  databaseConnected = false,
  selectedRole = "technical",
  operationalRole = "scrum_master",
  onWorkspaceChange,
  onRoleChange,
}) {
  const dashboard = useDashboardContext();
  const layout = usePanelLayout();
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
  const [copiedId, setCopiedId] = useState(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);
  const audioRef = useRef(null);
  const audioRequestControllerRef = useRef(null);
  const audioUrlCacheRef = useRef(new Map());
  const pendingDashboardContextRef = useRef(null);
  const SpeechRecognition = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [messages, isSending]);

  useEffect(() => {
    if (projects.length && !projects.some((item) => item.key === project)) {
      setProject(projects[0].key);
      dashboard.setSelectedProject(projects[0].key);
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
        if (savedId && recent.some((item) => item.id === savedId)) await openConversation(savedId);
      } catch (error) {
        if (!active) return;
        setConversationError(error.message);
        setConversationStatus("error");
      }
    }
    restore();
    return () => { active = false; };
  }, []);

  useEffect(() => () => {
    recognitionRef.current?.stop();
    audioRequestControllerRef.current?.abort();
    audioRef.current?.pause();
    for (const url of audioUrlCacheRef.current.values()) URL.revokeObjectURL(url);
    audioUrlCacheRef.current.clear();
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
      const restored = conversation.dashboard_context || {};
      setActiveConversationId(conversation.id);
      dashboard.setConversationId(conversation.id);
      window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversation.id);
      setMessages(messagesFromConversation(conversation));
      setProject(conversation.project_scope?.project_key || "DCPM");
      dashboard.setSelectedProject(conversation.project_scope?.project_key || "DCPM");
      dashboard.setSelectedSquad(restored.squad || "");
      dashboard.setSelectedRelease(restored.release || "");
      dashboard.setSelectedSprint(restored.sprint || "");
      dashboard.setDateRange({ from: restored.date_from || "", to: restored.date_to || "" });
      if (restored.active_view) dashboard.setActiveView(restored.active_view);
      if (restored.selected_metric) dashboard.setSelectedMetric(restored.selected_metric);
      onWorkspaceChange?.(conversation.workspace);
      if (restored.role === "head_of_department" || restored.role === "scrum_master") onRoleChange?.(restored.role);
      setConversationStatus("ready");
      setConversationError("");
    } catch (error) {
      setConversationError(error.message);
      setConversationStatus("error");
    }
  }

  async function sendMessage(rawText, dashboardOverride = null) {
    const text = rawText.trim();
    if (!text || isSending) return;
    const history = messages.filter((message) => message.id !== "welcome" && !message.error).slice(-12).map((message) => ({ role: message.role, content: message.text }));
    const requestContext = dashboardOverride || pendingDashboardContextRef.current || dashboard.dashboardContext();
    pendingDashboardContextRef.current = null;
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
        dashboard_context: requestContext,
      });
      const conversationId = payload.metadata?.conversation_id;
      if (conversationId && conversationId !== activeConversationId) {
        setActiveConversationId(conversationId);
        dashboard.setConversationId(conversationId);
        window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
      }
      setMessages((current) => [...current, makeMessage("assistant", payload.answer, {
        chart: payload.chart,
        table: payload.table,
        warnings: payload.warnings,
        validation: payload.validation,
        metadata: payload.metadata,
      })]);
      await loadRecent();
    } catch (error) {
      setMessages((current) => [...current, makeMessage("assistant", `I couldn’t complete that request. ${error.message}`, { error: true })]);
    } finally {
      setIsSending(false);
    }
  }

  function stopAudio() {
    audioRequestControllerRef.current?.abort();
    audioRequestControllerRef.current = null;
    if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0; audioRef.current = null; }
    setSpeakingId(null);
  }

  function startNewConversation() {
    stopAudio();
    window.localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
    setActiveConversationId(null);
    dashboard.setConversationId(null);
    setMessages([welcomeMessage]);
    setInput("");
    setSpeechError("");
  }

  async function clearConversation() {
    if (activeConversationId && !window.confirm("Archive this conversation? Other recent conversations will remain available.")) return;
    if (activeConversationId) {
      try { await archiveConversation(activeConversationId); await loadRecent(); }
      catch (error) { setConversationError(error.message); setConversationStatus("error"); return; }
    }
    startNewConversation();
  }

  async function archiveHistoryConversation(id) {
    if (!window.confirm("Archive this conversation?")) return;
    try {
      await archiveConversation(id);
      if (id === activeConversationId) startNewConversation();
      await loadRecent();
    } catch (error) {
      setConversationError(error.message);
      setConversationStatus("error");
    }
  }

  function fillQuestion(question, dashboardOverride = null) {
    setInput(question);
    pendingDashboardContextRef.current = dashboardOverride;
    layout.showPanel("chat");
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }

  function navigateWorkspace(destination) {
    if (destination === "assistant") {
      layout.showPanel("chat");
      window.requestAnimationFrame(() => inputRef.current?.focus());
      return;
    }
    layout.showPanel("dashboard");
    window.requestAnimationFrame(() => {
      if (destination === "reports") {
        document.getElementById("generate-report-button")?.click();
      } else {
        document.getElementById("dashboard-top")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  function changeRole(role) {
    const nextRole = role === "head_of_department" ? "head_of_department" : "scrum_master";
    onRoleChange?.(nextRole);
    onWorkspaceChange?.(nextRole === "head_of_department" ? "business" : "technical");
  }

  function toggleListening() {
    setSpeechError("");
    if (!SpeechRecognition) { setSpeechError("Voice input is not supported here. Chrome and Edge work best."); return; }
    if (isListening) { recognitionRef.current?.stop(); return; }
    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => setInput(Array.from(event.results).map((result) => result[0].transcript).join(""));
    recognition.onerror = (event) => setSpeechError(event.error === "not-allowed" ? "Microphone permission was denied." : "Voice input stopped unexpectedly.");
    recognition.onend = () => setIsListening(false);
    recognitionRef.current = recognition;
    recognition.start();
  }

  async function speak(message) {
    if (speakingId === message.id) { stopAudio(); return; }
    stopAudio();
    setSpeechError("");
    setSpeakingId(message.id);
    try {
      let audioUrl = audioUrlCacheRef.current.get(message.id);
      if (!audioUrl) {
        const controller = new AbortController();
        audioRequestControllerRef.current = controller;
        const plainText = message.text.replace(/\[(.*?)\]\(.*?\)/g, "$1").replace(/[#*_`>|[\]]/g, " ").replace(/\s+/g, " ").trim().slice(0, 2000);
        const response = await fetch(`${API_BASE}/api/tts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: plainText }), signal: controller.signal });
        if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(payload.detail || `Voice request failed with status ${response.status}`); }
        audioUrl = URL.createObjectURL(await response.blob());
        audioUrlCacheRef.current.set(message.id, audioUrl);
        audioRequestControllerRef.current = null;
      }
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      audio.onended = stopAudio;
      audio.onerror = () => { setSpeechError("The generated audio could not be played."); stopAudio(); };
      await audio.play();
    } catch (error) {
      if (error.name !== "AbortError") setSpeechError(`Voice playback unavailable: ${error.message}`);
      stopAudio();
    }
  }

  async function copyMessage(message) {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopiedId(message.id);
      window.setTimeout(() => setCopiedId((current) => current === message.id ? null : current), 1600);
    } catch { setSpeechError("The response could not be copied to the clipboard."); }
  }

  function retryLastMessage() {
    const lastUserMessage = [...messages].reverse().find((message) => message.role === "user");
    if (lastUserMessage) sendMessage(lastUserMessage.text);
  }

  const isEmpty = !messages.some((message) => message.role === "user");
  const roleConfig = getRoleDashboardConfig(operationalRole);
  const inputPlaceholder = WORKSPACE_PLACEHOLDERS[selectedRole] || WORKSPACE_PLACEHOLDERS.technical;
  const latestAssistantId = [...messages].reverse().find((message) => message.role === "assistant" && message.id !== "welcome")?.id;

  const historyPanel = <ConversationPanel conversations={conversations} status={conversationStatus} error={conversationError} activeConversationId={activeConversationId} operationalRole={operationalRole} onRoleChange={changeRole} onNew={startNewConversation} onOpen={openConversation} onArchive={archiveHistoryConversation} onRetry={loadRecent} onNavigate={navigateWorkspace} />;
  const dashboardPanel = (
    <div className="dashboard-panel-shell">
      <RoleDashboard role={operationalRole} projectKey={project} projects={projects} databaseConnected={databaseConnected} onProjectChange={setProject} onAsk={fillQuestion} disabled={isSending} />
    </div>
  );
  const chatPanel = (
    <div className="echo-copilot-panel">
      <div className="copilot-toolbar">
        <div><Sparkles aria-hidden="true" /><span>Zara · {roleConfig.label} context</span></div>
        <div><span className={`copilot-data-status ${databaseConnected ? "connected" : "offline"}`}><i aria-hidden="true" />{databaseConnected ? "DoraDB read-only" : "Data service offline"}</span><button type="button" onClick={clearConversation}><RotateCcw aria-hidden="true" /> Clear</button></div>
      </div>

      <div className="copilot-message-list" aria-live="polite">
        {isEmpty && <section className="copilot-empty-state"><span><Sparkles aria-hidden="true" /></span><p>Zara Assistant</p><h2>Understand what needs attention</h2><div>Ask about the current dashboard, explain a risk, or generate a report grounded in the selected scope.</div><SuggestedQuestionChips questions={roleConfig.initialQuestions} onSuggestionClick={fillQuestion} /></section>}
        {!isEmpty && messages.map((message) => (
          <article className={`copilot-message ${message.role} ${message.error ? "message-error" : ""}`} key={message.id}>
            <div className="copilot-message-avatar" aria-hidden="true">{message.role === "assistant" ? "AI" : "YOU"}</div>
            <div className="copilot-message-body">
              <div className="copilot-message-meta"><span>{message.role === "assistant" ? "Zara" : "You"}</span><div>
                {message.role === "assistant" && <button type="button" onClick={() => copyMessage(message)} aria-label="Copy response" title="Copy response"><Copy aria-hidden="true" /><span>{copiedId === message.id ? "Copied" : "Copy"}</span></button>}
                {message.role === "assistant" && <button type="button" onClick={() => speak(message)} aria-label={speakingId === message.id ? "Stop speaking" : "Read response aloud"} title="Read response aloud">{speakingId === message.id ? <Square aria-hidden="true" /> : <Volume2 aria-hidden="true" />}</button>}
              </div></div>
              <div className="copilot-message-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown></div>
              {message.warnings?.length > 0 && <div className="warning-panel"><CircleAlert aria-hidden="true" /><div><strong>Data note</strong>{message.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div></div>}
              <MetricChart chart={message.chart} />
              <DataTable table={message.table} />
              {message.error && <button className="message-retry-button" type="button" onClick={retryLastMessage}><RefreshCw aria-hidden="true" /> Retry last question</button>}
              {message.role === "assistant" && message.metadata?.analysis_steps > 0 && <div className="analysis-proof"><CheckCircle2 aria-hidden="true" /><span>{message.metadata.answer_source === "ai-provider-unavailable" ? "AI provider unavailable · no substitute answer created" : "Analyzed from read-only DoraDB · answer checked"}</span></div>}
              {message.id === latestAssistantId && !message.error && !isSending && <SuggestedQuestionChips label="Continue exploring" questions={roleConfig.followUpQuestions} onSuggestionClick={fillQuestion} />}
            </div>
          </article>
        ))}
        {isSending && <div className="thinking" role="status"><span /><span /><span /><p>Zara is analysing the current scope…</p></div>}
        <div ref={endRef} />
      </div>

      <div className="copilot-composer-wrap">
        {speechError && <p className="speech-error" role="alert">{speechError}</p>}
        <form className="copilot-composer" onSubmit={(event) => { event.preventDefault(); sendMessage(input); }}>
          <textarea ref={inputRef} aria-label="Ask about your delivery metrics" placeholder={inputPlaceholder} rows="1" value={input} maxLength={2000} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(input); } }} />
          <button className={`voice-button ${isListening ? "listening" : ""}`} type="button" onClick={toggleListening} aria-label={isListening ? "Stop voice input" : "Start voice input"}>{isListening ? <MicOff aria-hidden="true" /> : <Mic aria-hidden="true" />}</button>
          <button className="send-button" type="submit" disabled={!input.trim() || isSending} aria-label="Send message"><ArrowUp aria-hidden="true" /></button>
        </form>
        <p>Enter to send · Shift + Enter for a new line</p>
      </div>
    </div>
  );

  return <ThreePanelWorkspace layout={layout} history={historyPanel} dashboard={dashboardPanel} chat={chatPanel} />;
}
