import { useEffect, useMemo, useState } from "react";
import { Check, FileText, Loader2, Sparkles } from "lucide-react";
import { loadDashboardFilters, loadDashboardSquads } from "../../services/dashboard";

const ALL_SCOPE_LABELS = new Set(["all squads", "all sprints", "all releases", "all available dates", "all visible features", "all features", "all tickets", "all ticket types", "all statuses", "all priorities"]);
const cleanScope = (scope) => Object.fromEntries(Object.entries(scope).filter(([, value]) => value && !ALL_SCOPE_LABELS.has(String(value).trim().toLowerCase())));

export default function NewReport({ catalogue, pending, busy, initialScope, onCreate, onCancel }) {
  const [scope, setScope] = useState({ project: "DCPM", squad: "", sprint: "", ...(initialScope || {}) });
  const [template, setTemplate] = useState("weekly_scrum");
  const [squads, setSquads] = useState([]);
  const [filters, setFilters] = useState({ sprints: [] });
  const [optionsError, setOptionsError] = useState("");
  const weekly = useMemo(() => (catalogue?.templates || []).find((item) => item.id === "weekly_scrum"), [catalogue]);

  useEffect(() => {
    loadDashboardSquads(scope.project)
      .then((result) => setSquads(result.squads || []))
      .catch((error) => setOptionsError(error.message));
  }, [scope.project]);

  useEffect(() => {
    loadDashboardFilters({ project: scope.project, squad: scope.squad || undefined })
      .then(setFilters)
      .catch((error) => setOptionsError(error.message));
  }, [scope.project, scope.squad]);

  function submit(event) {
    event.preventDefault();
    if (!scope.project || !scope.squad || !scope.sprint) return;
    const chosen = (catalogue?.templates || []).find((item) => item.id === template) || weekly;
    onCreate({
      template,
      title: `Weekly Scrum Report — ${scope.squad} — ${scope.sprint}`,
      audience: chosen?.default_audience || "delivery_manager",
      tone: chosen?.default_tone || "professional",
      detail_level: "standard",
      include_recommendations: true,
      scope: cleanScope(scope),
    }, { generate: true });
  }

  return (
    <form className="report-new" onSubmit={submit}>
      <header className="report-new-intro"><span><Sparkles /></span><div><h2>Prepare a report in ZARA Report Studio</h2><p>Choose a verified scope and fixed template. Zara retrieves report evidence from the server after creation.</p></div></header>
      {pending && <p className="report-new-pending"><Check /> The selected verified Zara source will remain attached as supporting evidence.</p>}
      <fieldset><legend>Report configuration</legend><div className="report-config-grid">
        <label><span>Project</span><select required value={scope.project} onChange={(event) => setScope({ ...scope, project: event.target.value, squad: "", sprint: "" })}><option value="DCPM">DCPM</option></select></label>
        <label><span>Squad</span><select required value={scope.squad} onChange={(event) => setScope({ ...scope, squad: event.target.value, sprint: "" })}><option value="">Select squad</option>{squads.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
        <label><span>Sprint</span><select required value={scope.sprint} disabled={!scope.squad} onChange={(event) => setScope({ ...scope, sprint: event.target.value })}><option value="">Select sprint</option>{(filters.sprints || []).map((item) => <option key={item.value} value={item.value}>{item.value}</option>)}</select></label>
        <label><span>Template</span><select required value={template} onChange={(event) => setTemplate(event.target.value)}><option value="weekly_scrum">Weekly Scrum Report</option></select></label>
      </div>{optionsError && <p className="report-option-error">Available options could not be loaded: {optionsError}</p>}</fieldset>
      <section className="report-question-preview"><h3>Weekly Scrum content</h3><ul><li>Delivery at a Glance</li><li>Feature Delivery Status</li><li>Executive Summary</li><li>Key Highlights / What the Data Shows</li><li>Risks Requiring Attention</li><li>Recommended Actions</li><li>Data Quality and Limitations</li></ul></section>
      <div className="report-new-actions"><button type="button" onClick={onCancel}>Cancel</button><button type="submit" className="primary" disabled={busy || !scope.squad || !scope.sprint}>{busy ? <Loader2 className="is-spinning" /> : <FileText />}Create report</button></div>
    </form>
  );
}
