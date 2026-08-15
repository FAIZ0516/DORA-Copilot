import { useMemo, useState } from "react";
import { Loader2, Send, Sparkles } from "lucide-react";
import zaraWordmark from "../../assets/zara-wordmark.png";

const SUGGESTIONS = [
  "Make this shorter.",
  "Explain this for management.",
  "Rewrite this as three concise bullet points.",
  "Focus more on blockers.",
  "Explain this in simpler language.",
  "Remove repetitive wording.",
];

export default function ReportAssistantPanel({ report, selectedSection, busy, onSelectSection, onRefine }) {
  const [instruction, setInstruction] = useState("");
  const narrative = useMemo(() => report.sections.filter((section) => ["executive_summary", "rich_text", "key_finding", "risk", "recommendation", "action_list"].includes(section.type)), [report.sections]);

  function submit(event) {
    event?.preventDefault();
    if (!instruction.trim() || !selectedSection) return;
    onRefine(selectedSection, instruction.trim());
    setInstruction("");
  }

  return (
    <aside className="report-assistant-panel" aria-label="Zara Report Assistant">
      <header><span><Sparkles /></span><div><p><img src={zaraWordmark} alt="ZARA" /><strong>AI</strong></p><h3>Refine the report</h3><small>Report intelligence assistant</small></div></header>
      <p>Choose one narrative section, then describe the rewrite you want. Zara will update only that section using its verified sources.</p>
      <label><span>Selected section</span><select value={selectedSection?.id || ""} onChange={(event) => onSelectSection(narrative.find((section) => section.id === event.target.value) || null)}><option value="">Choose a narrative section</option>{narrative.map((section) => <option key={section.id} value={section.id}>{section.title}</option>)}</select></label>
      <div className="report-assistant-suggestions">{SUGGESTIONS.map((text) => <button key={text} type="button" disabled={!selectedSection || busy} onClick={() => setInstruction(text)}>{text}</button>)}</div>
      <form onSubmit={submit}><textarea rows="4" value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="Ask Zara to refine the selected section…" /><button type="submit" className="primary" disabled={!selectedSection || !instruction.trim() || busy}>{busy ? <Loader2 className="is-spinning" /> : <Send />}Refine section</button></form>
      <div className="report-assistant-guard"><strong>Verified facts are protected</strong><span>Zara can change narrative wording and emphasis, but cannot edit structured statuses or metric values.</span></div>
    </aside>
  );
}
