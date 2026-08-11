import { ArrowLeft, BarChart3, Bookmark, MessageSquareText, Play, Save, Sparkles, WandSparkles } from "lucide-react";

export type AppPage = "prepare" | "visualize" | "assistant" | "saved";
interface Props { active: AppPage; name: string; running: boolean; dirty: boolean; onNameChange: (name: string) => void; onNavigate: (page: AppPage) => void; onSave: () => void; onRun: () => void }

export function TopNavigation({ active, name, running, dirty, onNameChange, onNavigate, onSave, onRun }: Props) {
  return <header className="top-navigation top-navigation--unified">
    <a className="workspace-back-link" href="/" aria-label="Return to DORA Copilot"><ArrowLeft size={15} /></a>
    <div className="brand-lockup"><span className="brand-mark">Z</span><div><strong>Zara</strong><small>Data Workspace</small></div></div>
    <nav className="product-navigation" aria-label="Workspace sections"><button className={active === "prepare" ? "active" : ""} onClick={() => onNavigate("prepare")}><WandSparkles size={15} /> Prepare</button><button className={active === "visualize" ? "active" : ""} onClick={() => onNavigate("visualize")}><BarChart3 size={15} /> Visualize</button><button className={active === "assistant" ? "active" : ""} onClick={() => onNavigate("assistant")}><MessageSquareText size={15} /> Ask Zara</button><button className={active === "saved" ? "active" : ""} onClick={() => onNavigate("saved")}><Bookmark size={15} /> Saved Views</button></nav>
    <div className="nav-spacer" />
    <label className="workflow-name"><span>Workspace</span><input value={name} onChange={(event) => onNameChange(event.target.value)} aria-label="Workspace name" /></label>
    <span className="save-state">{dirty ? <><i /> Unsaved</> : "Saved"}</span>
    <button className="nav-button" onClick={onSave}><Save size={15} /> Save</button>
    {active === "prepare" && <button className="run-button" onClick={onRun} disabled={running}><Play size={15} fill="currentColor" /> {running ? "Running…" : "Run Workflow"}</button>}
    {/* A "Workspace settings" button used to sit here with no handler and no
        settings screen behind it. Removed rather than left as a dead control. */}
    <span className="ai-ready" title="Zara AI ready"><Sparkles size={14} /></span>
  </header>;
}
