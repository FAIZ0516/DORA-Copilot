import { Bot, ChevronRight, Mic, PanelRightClose, PanelRightOpen, Send, Sparkles, User } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { zaraAssistantService } from "../services/zaraAssistantService";
import type { AssistantMessage, DashboardContext } from "../types/assistant";

const suggestions = ["Why did blocked issues increase?", "Which squad needs attention?", "What changed from the previous sprint?", "Which issue type contributes most to delays?", "What should I investigate first?"];

interface Props {
  context: DashboardContext;
  collapsed: boolean;
  promptRequest?: { id: string; question: string } | null;
  onToggle: () => void;
  onCreateChart: () => void;
  onShowBlockers: () => void;
  onViewData: () => void;
}

export function ZaraPanel({ context, collapsed, promptRequest, onToggle, onCreateChart, onShowBlockers, onViewData }: Props) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const handledPrompt = useRef<string | null>(null);

  const ask = async (question: string) => {
    const clean = question.trim(); if (!clean || thinking) return;
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: clean }]);
    setDraft(""); setThinking(true);
    try {
      const response = await zaraAssistantService.ask(clean, context);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: response.answer, prototype: response.prototype, followUps: response.followUps }]);
    } catch (reason) {
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: reason instanceof Error ? reason.message : "Zara could not answer this question." }]);
    } finally { setThinking(false); }
  };

  useEffect(() => {
    if (promptRequest && promptRequest.id !== handledPrompt.current) { handledPrompt.current = promptRequest.id; void ask(promptRequest.question); }
  }, [promptRequest]);

  const followUp = (label: string) => {
    if (label === "Create a chart") return onCreateChart();
    if (label === "Show blockers only") return onShowBlockers();
    if (label === "View affected issues") return onViewData();
    void ask(label);
  };
  const submit = (event: FormEvent) => { event.preventDefault(); void ask(draft); };

  if (collapsed) return <aside className="zara-panel zara-panel--collapsed"><button onClick={onToggle} aria-label="Open Zara Assistant"><PanelRightOpen size={18} /><span>Zara</span></button></aside>;
  return <aside className="zara-panel">
    <header><div><span><Sparkles size={17} /></span><div><strong>Zara Assistant</strong><small><i /> Analyzing current view · Demo mode</small></div></div><button onClick={onToggle} aria-label="Collapse Zara Assistant"><PanelRightClose size={17} /></button></header>
    <div className="zara-conversation">{!messages.length ? <div className="assistant-empty"><span><Bot size={25} /></span><h2>Ask Zara about this data</h2><p>I understand the prepared output, visible charts, and selected categories.</p><div>{suggestions.map((question) => <button key={question} onClick={() => void ask(question)}>{question}<ChevronRight size={12} /></button>)}</div></div> : messages.map((message) => <article key={message.id} className={`assistant-message assistant-message--${message.role}`}><span>{message.role === "assistant" ? <Sparkles size={14} /> : <User size={14} />}</span><div>{message.prototype && <small>PROTOTYPE INSIGHT</small>}<p>{message.content}</p>{message.followUps && <div className="assistant-followups">{message.followUps.map((item) => <button key={item} onClick={() => followUp(item)}>{item}</button>)}</div>}</div></article>)}{thinking && <div className="assistant-thinking"><i /><i /><i /><span>Reviewing this view</span></div>}</div>
    <form className="assistant-composer" onSubmit={submit}><div><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask Zara about this dashboard…" aria-label="Ask Zara" /><button type="button" aria-label="Voice input"><Mic size={15} /></button><button type="submit" aria-label="Send question" disabled={!draft.trim() || thinking}><Send size={15} /></button></div><small>Prototype responses use structured dashboard context.</small></form>
  </aside>;
}
