import { FileText, Sparkles, X } from "lucide-react";

const REPORT_TYPES = [
  ["Executive Summary", "Create an executive summary for management"],
  ["Sprint Performance Report", "Create a sprint performance report"],
  ["Risk and Action Report", "Create a risk and action report"],
  ["Management Update", "Create a concise weekly management update"],
];

export default function ReportGenerationDrawer({ open, scope, onClose, onGenerate }) {
  if (!open) return null;
  return (
    <div className="report-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="report-generation-drawer" role="dialog" aria-modal="true" aria-labelledby="report-drawer-title">
        <header><span><FileText aria-hidden="true" /></span><div><p>Zara reporting</p><h2 id="report-drawer-title">Generate a report</h2></div><button type="button" onClick={onClose} aria-label="Close report generator"><X aria-hidden="true" /></button></header>
        <section><h3>Current context</h3><div className="report-scope-chips">{Object.entries(scope || {}).filter(([, value]) => value && typeof value !== "object").map(([key, value]) => <span key={key}>{key.replaceAll("_", " ")}: {String(value)}</span>)}</div></section>
        <section><h3>Choose a report type</h3><div className="report-type-list">{REPORT_TYPES.map(([label, prompt]) => <button key={label} type="button" onClick={() => { onGenerate(`${prompt} using only the currently selected dashboard scope, validated metrics, visible delivery risks, productivity support signals, and data-quality caveats. Make the report editable and clearly separate observed facts from recommendations.`); onClose(); }}><FileText aria-hidden="true" /><span><strong>{label}</strong><small>Uses the active dashboard context</small></span><Sparkles aria-hidden="true" /></button>)}</div></section>
        <p className="report-drawer-note">Zara generates the report in the assistant so you can ask for revisions, a shorter version, a different audience, or clearer actions.</p>
      </aside>
    </div>
  );
}
