import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleHelp,
  Database,
  Eye,
  FileText,
  Info,
  RefreshCw,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { useDashboardContext } from "../dashboardContext";
import {
  buildFeatureOptions,
  buildPrimaryKpis,
  buildRiskItems,
  filterIssuesForFeature,
} from "../dashboardPresentation";
import {
  loadDashboardFilters,
  loadDashboardIssues,
  loadDashboardSquads,
  loadPortfolioDashboard,
  loadSquadDashboard,
} from "../services/dashboard";
import { DeliveryAnalytics, ProductivityOverview } from "./DashboardVisuals";
import MetricInfoDrawer from "./MetricInfoDrawer";
import ReportGenerationDrawer from "./ReportGenerationDrawer";

function number(value, suffix = "") {
  if (value === null || value === undefined) return "Unavailable";
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}

function statusClass(status = "") {
  return status.toLowerCase().replaceAll(" ", "-");
}

function DashboardSkeleton() {
  return (
    <div className="role-dashboard-skeleton" role="status" aria-label="Loading dashboard">
      <div>{Array.from({ length: 4 }, (_, index) => <span key={index} />)}</div>
      <span className="skeleton-attention" />
      <span className="skeleton-table" />
    </div>
  );
}

function PrimaryKpiRow({ payload, onInfo, onAsk, squad }) {
  const cards = buildPrimaryKpis(payload, squad);
  return (
    <section className="primary-kpi-section" aria-labelledby="primary-kpi-title">
      <div className="section-heading-row compact"><div><p>Current delivery position</p><h3 id="primary-kpi-title">KPI Overview</h3></div></div>
      <div className="role-metric-grid">
        {cards.map((card) => (
          <article className={`role-metric-card tone-${card.tone}`} key={card.key}>
            <div><span>{card.title}</span><button type="button" onClick={() => onInfo({ key: card.key, value: card.value, ...card.definition })} aria-label={`Explain ${card.title}`} title={`What ${card.title} means`}><Info aria-hidden="true" /></button></div>
            <strong>{typeof card.value === "number" ? number(card.value, card.suffix) : card.value}</strong>
            <p>{card.comparison}</p>
            <button className="metric-ask-action" type="button" onClick={() => onAsk(card.definition?.suggested_questions?.[0] || `Explain ${card.title}.`, { selected_metric: card.key, current_metric_value: card.value })}><Sparkles aria-hidden="true" /> Ask Zara</button>
          </article>
        ))}
      </div>
    </section>
  );
}

function DashboardFilters({
  context,
  options,
  projects,
  squads,
  onProjectChange,
  onSquadChange,
  onRefresh,
  loading,
  featureOptions,
  selectedFeature,
  onFeatureChange,
  issueView,
  onIssueViewChange,
  onReset,
}) {
  const active = [
    context.selectedSquad,
    context.selectedSprint,
    selectedFeature,
    issueView !== "all" ? issueView : "",
    context.selectedRelease,
  ].filter(Boolean);
  return (
    <section className="dashboard-filter-area" aria-label="Dashboard controls">
      <div className="dashboard-filter-bar">
        <label><span>Squad</span><select value={context.selectedSquad} onChange={(event) => onSquadChange(event.target.value)}><option value="">All squads</option>{squads.map((squad) => <option key={squad.name} value={squad.name}>{squad.name}</option>)}</select></label>
        <label><span>Sprint</span><select value={context.selectedSprint} onChange={(event) => context.setSelectedSprint(event.target.value)}><option value="">All sprints</option>{(options?.sprints || []).map((item) => <option key={item.value} value={item.value}>{item.value}</option>)}</select></label>
        <label><span>Project</span><select value={context.selectedProject} onChange={(event) => onProjectChange(event.target.value)}>{(projects?.length ? projects : [{ key: context.selectedProject, label: context.selectedProject }]).map((item) => <option key={item.key} value={item.key}>{item.label || item.key}</option>)}</select></label>
        <label><span>Feature</span><select value={selectedFeature} onChange={(event) => onFeatureChange(event.target.value)} disabled={!featureOptions.length}><option value="">All visible features</option>{featureOptions.map((feature) => <option value={feature} key={feature}>{feature}</option>)}</select></label>
        <label><span>Ticket View</span><select value={issueView} onChange={(event) => onIssueViewChange(event.target.value)}><option value="all">All tickets</option><option value="features">Features</option><option value="bugs">Bugs</option><option value="tests">Tests</option></select></label>
        <details className="more-filters"><summary>More Filters <ChevronDown aria-hidden="true" /></summary><div>
          <label><span>Release</span><select value={context.selectedRelease} onChange={(event) => context.setSelectedRelease(event.target.value)}><option value="">All releases</option>{(options?.releases || []).map((item) => <option key={item.value} value={item.value}>{item.value}</option>)}</select></label>
          <label><span>Created from</span><input type="date" min={options?.date_range?.minimum || undefined} max={context.dateRange.to || options?.date_range?.maximum || undefined} value={context.dateRange.from} onChange={(event) => context.setDateRange((current) => ({ ...current, from: event.target.value }))} /></label>
          <label><span>Created to</span><input type="date" min={context.dateRange.from || options?.date_range?.minimum || undefined} max={options?.date_range?.maximum || undefined} value={context.dateRange.to} onChange={(event) => context.setDateRange((current) => ({ ...current, to: event.target.value }))} /></label>
          <button type="button" onClick={onRefresh} disabled={loading}><RefreshCw className={loading ? "is-spinning" : ""} aria-hidden="true" /> Refresh data</button>
        </div></details>
        <button className="filter-reset-button" type="button" onClick={onReset} disabled={!active.length}><RotateCcw aria-hidden="true" /> Reset</button>
      </div>
      <div className="active-filter-summary"><span>Active</span><b>{context.selectedProject}</b>{active.length ? active.map((item) => <b key={item}>{item.replaceAll("_", " ")}</b>) : <em>All squads · all available data</em>}</div>
    </section>
  );
}

function RiskAttentionPanel({ payload, onViewIssue, onAsk, viewLabel = "View Ticket", squad = "" }) {
  const risks = buildRiskItems(payload);
  return (
    <section className="dashboard-attention-panel" id="risks-requiring-attention" data-section="risks" aria-labelledby="attention-title">
      <header><div><AlertTriangle aria-hidden="true" /><div><p>Early risk detection</p><h3 id="attention-title">Risks Requiring Attention</h3></div></div><span>Transparent rules</span></header>
      {risks.length === 0 ? <div className="attention-empty"><CircleCheck aria-hidden="true" /> No significant delivery risks were detected from the currently available data.</div> : (
        <div className="attention-list">{risks.map((risk) => (
          <article key={risk.id} className={`severity-${risk.severity.toLowerCase()}`}>
            <div className="risk-severity"><i aria-hidden="true" /><span>{risk.severity}</span></div>
            <div className="risk-content"><strong>{risk.title}</strong><dl><div><dt>Evidence</dt><dd>{risk.evidence}</dd></div><div><dt>Potential impact</dt><dd>{risk.impact}</dd></div><div><dt>Suggested action</dt><dd>{risk.action}</dd></div></dl></div>
            <div className="risk-actions"><button type="button" onClick={() => onViewIssue(risk)}><Eye aria-hidden="true" /> {viewLabel}</button><button type="button" onClick={() => { const scopedSquad = risk.squad || squad; onAsk(`Explain ${scopedSquad ? `the delivery risk for the ${scopedSquad} squad` : "this delivery risk"} using the active dashboard evidence: ${risk.title}. Evidence: ${risk.evidence}. Separate observed facts, possible impact, missing context, and recommended action.`, { selected_metric: risk.metric, current_metric_value: risk.value, ...(scopedSquad ? { squad: scopedSquad } : {}) }); }}><Sparkles aria-hidden="true" /> Ask Zara</button></div>
          </article>
        ))}</div>
      )}
    </section>
  );
}

function PortfolioView({ payload, onSquad, onAsk }) {
  const [sortBy, setSortBy] = useState("attention");
  const rows = useMemo(() => {
    const copy = [...(payload.squad_comparison || [])];
    const statusOrder = { "Needs Attention": 0, "Data Incomplete": 1, Monitor: 2, Healthy: 3 };
    copy.sort((a, b) => sortBy === "attention"
      ? (statusOrder[a.status] ?? 4) - (statusOrder[b.status] ?? 4)
      : Number(sortBy === "completion_pct" ? a[sortBy] || 0 : b[sortBy] || 0) - Number(sortBy === "completion_pct" ? b[sortBy] || 0 : a[sortBy] || 0));
    return copy;
  }, [payload.squad_comparison, sortBy]);
  return (
    <>
      {/* Portfolio attention_items are squad rows, so each reason is tagged
          with its squad before flattening. "View Squad" then opens that
          squad's dashboard -- previously this button was wired to an empty
          function and did nothing at all. */}
      <section className="portfolio-risk-summary"><RiskAttentionPanel payload={{ ...payload, kpis: { ...payload.kpis, status: "Needs Attention" }, attention_items: (payload.attention_items || []).flatMap((item) => (item.reasons || []).map((reason) => ({ ...reason, squad: item.squad, status: item.status }))) }} viewLabel="View Squad" onViewIssue={(risk) => { const row = (payload.squad_comparison || []).find((item) => item.squad === risk.squad); if (row) onSquad(row); }} onAsk={onAsk} /></section>
      <section className="portfolio-comparison" aria-labelledby="squad-comparison-title"><header><div><p>Portfolio comparison</p><h3 id="squad-comparison-title">All Squads</h3></div><label>Sort by<select value={sortBy} onChange={(event) => setSortBy(event.target.value)}><option value="attention">Attention status</option><option value="completion_pct">Completion percentage</option><option value="open_bugs">Open bugs</option><option value="oldest_unresolved_days">Unresolved age</option></select></label></header><div className="portfolio-table-wrap"><table><thead><tr><th>Squad</th><th>End-state progress</th><th>In progress</th><th>To do</th><th>Open bugs</th><th>Oldest unresolved</th><th>Attention</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.squad} tabIndex="0" onClick={() => onSquad(row)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSquad(row); } }}><th>{row.squad}<small>View Squad Dashboard</small></th><td><div className="mini-progress"><i><b style={{ width: `${Math.min(100, Number(row.completion_pct || 0))}%` }} /></i><span>{number(row.completion_pct, "%")}</span></div></td><td>{number(row.in_progress_work)}</td><td>{number(row.todo_work)}</td><td>{number(row.open_bugs)}</td><td>{number(row.oldest_unresolved_days, " days")}</td><td><span className={`attention-badge ${statusClass(row.status)}`}>{row.status}</span></td><td><ChevronRight aria-hidden="true" /></td></tr>)}</tbody></table></div></section>
    </>
  );
}

function IssueTable({ payload, filterOptions, filters, setFilters, onPage }) {
  const items = payload?.items || [];
  const choices = filterOptions?.issue_filters || {};
  const updateFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value, page: 1 }));
  return (
    <section className="dashboard-issue-table" id="feature-issue-table" data-section="issues" aria-labelledby="work-table-title">
      <header><div><p>Operational detail</p><h3 id="work-table-title">Feature &amp; Ticket Table</h3></div><span>{number(payload?.total || 0)} tickets</span></header>
      {payload?.page_limited_filter && <p className="table-scope-note">The selected feature is filtered within the currently loaded table page because the backend does not yet expose a feature-filter parameter.</p>}
      <div className="issue-table-filters">
        {[["issue_type", "Ticket type", "issue_types"], ["status", "Status", "statuses"], ["priority", "Priority", "priorities"]].map(([key, label, optionKey]) => <label key={key}><span>{label}</span><select value={filters[key]} onChange={(event) => updateFilter(key, event.target.value)}><option value="">All {label.toLowerCase()}s</option>{(choices[optionKey] || []).map((item) => <option key={item.value} value={item.value}>{item.value}</option>)}</select></label>)}
        <label><span>Assignee</span><input list="dashboard-assignees" value={filters.assignee} onChange={(event) => updateFilter("assignee", event.target.value)} placeholder="Search assignees" /><datalist id="dashboard-assignees">{(choices.assignees || []).map((item) => <option key={item.value} value={item.value} />)}</datalist></label>
        <label><span>Sort</span><select value={filters.sort_by} onChange={(event) => setFilters((current) => ({ ...current, sort_by: event.target.value }))}><option value="updated">Updated</option><option value="created">Created</option><option value="priority">Priority</option><option value="status">Status</option></select></label>
      </div>
      {items.length === 0 ? <div className="dashboard-empty-state">No Jira tickets match the current squad and table filters.</div> : <div className="portfolio-table-wrap"><table><thead><tr><th>Ticket</th><th>Summary</th><th>Type</th><th>Status</th><th>Priority</th><th>Assignee</th><th>Feature</th><th>Sprint</th></tr></thead><tbody>{items.map((issue) => <tr key={issue.issue_key}><th>{issue.issue_key}</th><td>{issue.summary || "Unavailable"}</td><td>{issue.issue_type || "Unavailable"}</td><td>{issue.status || issue.status_category || "Unavailable"}</td><td>{issue.priority || "Unavailable"}</td><td>{issue.assignee || "Unassigned"}</td><td>{issue.feature_link || "—"}</td><td>{issue.sprints || "—"}</td></tr>)}</tbody></table></div>}
      <footer><button type="button" disabled={(payload?.page || 1) <= 1} onClick={() => onPage((payload?.page || 1) - 1)}>Previous</button><span>Page {payload?.page || 1} of {payload?.total_pages || 1}</span><button type="button" disabled={(payload?.page || 1) >= (payload?.total_pages || 1)} onClick={() => onPage((payload?.page || 1) + 1)}>Next</button></footer>
    </section>
  );
}

export default function RoleDashboard({ projectKey, projects = [], databaseConnected, onProjectChange, onAsk, disabled = false }) {
  const context = useDashboardContext();
  const [squads, setSquads] = useState([]);
  const [options, setOptions] = useState(null);
  const [payload, setPayload] = useState(null);
  const [issues, setIssues] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [drawerMetric, setDrawerMetric] = useState(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [selectedFeature, setSelectedFeature] = useState("");
  const [issueView, setIssueView] = useState("all");
  const [issueFilters, setIssueFilters] = useState({ issue_type: "", status: "", priority: "", assignee: "", page: 1, page_size: 20, sort_by: "updated", sort_order: "desc" });

  useEffect(() => { if (projectKey) context.setSelectedProject(projectKey); }, [projectKey]);

  useEffect(() => {
    const controller = new AbortController();
    loadDashboardSquads(context.selectedProject, { signal: controller.signal }).then((result) => {
      const nextSquads = result.squads || [];
      setSquads(nextSquads);
    }).catch((loadError) => { if (loadError.name !== "AbortError") setError(loadError.message); });
    return () => controller.abort();
  }, [context.selectedProject, refreshToken]);

  useEffect(() => {
    const controller = new AbortController();
    loadDashboardFilters({ project: context.selectedProject, squad: context.selectedSquad || undefined }, { signal: controller.signal }).then(setOptions).catch((loadError) => { if (loadError.name !== "AbortError") setError(loadError.message); });
    return () => controller.abort();
  }, [context.selectedProject, context.selectedSquad, refreshToken]);

  const filterRequest = useMemo(() => ({ project: context.selectedProject, release: context.selectedRelease || undefined, sprint: context.selectedSprint || undefined, date_from: context.dateRange.from || undefined, date_to: context.dateRange.to || undefined }), [context.selectedProject, context.selectedRelease, context.selectedSprint, context.dateRange]);

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading"); setError("");
    const request = !context.selectedSquad || context.activeView === "portfolio" ? loadPortfolioDashboard(filterRequest, { signal: controller.signal }) : loadSquadDashboard(context.selectedSquad, filterRequest, { signal: controller.signal });
    request.then((result) => { setPayload(result); setStatus("ready"); }).catch((loadError) => { if (loadError.name !== "AbortError") { setError(loadError.message); setStatus("error"); } });
    return () => controller.abort();
  }, [context.activeView, context.selectedSquad, filterRequest, refreshToken]);

  useEffect(() => {
    if (!context.selectedSquad || context.activeView === "portfolio") { setIssues(null); return undefined; }
    const controller = new AbortController();
    const timer = window.setTimeout(() => { loadDashboardIssues({ ...filterRequest, squad: context.selectedSquad, ...issueFilters }, { signal: controller.signal }).then(setIssues).catch((loadError) => { if (loadError.name !== "AbortError") setError(loadError.message); }); }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [context.selectedSquad, context.activeView, filterRequest, issueFilters, refreshToken]);

  function ask(question, patch = {}) { if (patch.selected_metric) context.setSelectedMetric(patch.selected_metric); if (patch.current_metric_value !== undefined) context.setCurrentMetricValue(patch.current_metric_value); onAsk(question, context.dashboardContext(patch)); }
  function openMetric(metric) { context.setSelectedMetric(metric.key); context.setCurrentMetricValue(metric.value); setDrawerMetric(metric); }
  function viewSquad(row) { context.setSelectedSquad(row.squad || row.name); context.setSelectedSquadRow(row); context.setActiveView("squad_detail"); setIssueFilters((current) => ({ ...current, page: 1 })); window.requestAnimationFrame(() => document.getElementById("dashboard-top")?.scrollIntoView({ behavior: "smooth", block: "start" })); }
  function changeSquad(value) { if (!value) { context.setActiveView("portfolio"); context.setSelectedSquad(""); context.setSelectedSquadRow(null); } else viewSquad({ squad: value }); }
  function changeProject(value) { context.setSelectedProject(value); context.setSelectedSquad(""); context.setSelectedSquadRow(null); context.setActiveView("portfolio"); context.setSelectedRelease(""); context.setSelectedSprint(""); context.setDateRange({ from: "", to: "" }); onProjectChange?.(value); }
  function changeIssueView(value) { const types = { all: "", features: "Feature", bugs: "Bug", tests: "Test" }; setIssueView(value); setIssueFilters((current) => ({ ...current, issue_type: types[value], page: 1 })); setSelectedFeature(""); }
  function resetFilters() { context.setSelectedSquad(""); context.setSelectedSquadRow(null); context.setActiveView("portfolio"); context.setSelectedRelease(""); context.setSelectedSprint(""); context.setDateRange({ from: "", to: "" }); context.setSelectedMetric(""); context.setCurrentMetricValue(null); setSelectedFeature(""); setIssueView("all"); setIssueFilters({ issue_type: "", status: "", priority: "", assignee: "", page: 1, page_size: 20, sort_by: "updated", sort_order: "desc" }); }
  function focusRisk(risk) { setSelectedFeature(""); setIssueFilters((current) => ({ ...current, issue_type: risk.metric === "high_priority_open_bugs" ? "Bug" : "", priority: risk.metric === "high_priority_open_bugs" ? "High" : "", status: risk.metric === "impeded_work" ? "IMPEDED" : "", sort_by: "updated", page: 1 })); window.requestAnimationFrame(() => document.getElementById("feature-issue-table")?.scrollIntoView({ behavior: "smooth", block: "start" })); }

  const featureOptions = buildFeatureOptions(issues);
  const visibleIssues = filterIssuesForFeature(issues, selectedFeature);
  const isPortfolio = !context.selectedSquad || context.activeView === "portfolio";
  const title = isPortfolio ? "All Squads Overview" : `${context.selectedSquad} Performance`;
  const lastRefresh = payload?.generated_at ? new Date(payload.generated_at).toLocaleString() : "Waiting for data";

  return (
    <section className="role-dashboard" aria-label="Engineering performance dashboard">
      <header className="workspace-dashboard-header" id="dashboard-top" data-section="dashboard"><div><p>{isPortfolio ? "Engineering Performance" : `Engineering Performance › ${context.selectedSquad}`}</p><h1>{title}</h1><div className="dashboard-header-meta"><span><strong>Squad</strong>{context.selectedSquad || "All squads"}</span><span><strong>Sprint</strong>{context.selectedSprint || "All sprints"}</span><span><strong>Date range</strong>{context.dateRange.from || context.dateRange.to ? `${context.dateRange.from || "Start"} — ${context.dateRange.to || "Today"}` : "All available dates"}</span><span><strong>Last refresh</strong>{lastRefresh}</span></div></div><div className="dashboard-header-actions"><span className={`data-connection-pill ${databaseConnected ? "connected" : "offline"}`}><Database aria-hidden="true" />{databaseConnected ? "Live DoraDB" : "Database unavailable"}</span><button id="generate-report-button" className="primary" type="button" onClick={() => setReportOpen(true)} disabled={disabled}><FileText aria-hidden="true" /> Generate Report</button><button type="button" onClick={() => ask(`Summarise the current ${context.selectedSquad || "all-squads"} dashboard and tell me what I should prioritise next.`)}><Sparkles aria-hidden="true" /> Ask Zara</button></div></header>

      <DashboardFilters context={context} options={options} projects={projects} squads={squads} onProjectChange={changeProject} onSquadChange={changeSquad} onRefresh={() => setRefreshToken((value) => value + 1)} loading={status === "loading"} featureOptions={featureOptions} selectedFeature={selectedFeature} onFeatureChange={setSelectedFeature} issueView={issueView} onIssueViewChange={changeIssueView} onReset={resetFilters} />

      {status === "loading" && !payload && <DashboardSkeleton />}
      {status === "error" && <div className="dashboard-error-state" role="alert"><AlertTriangle /><div><strong>Dashboard data could not be loaded</strong><p>{error}</p></div><button type="button" onClick={() => setRefreshToken((value) => value + 1)}>Retry</button></div>}
      {!context.selectedSquad && status !== "loading" && status !== "error" && squads.length === 0 && <div className="dashboard-empty-state"><CircleHelp /><strong>No valid squads are available.</strong><p>Confirm the project and DoraDB squad mappings, then refresh.</p></div>}
      {payload?.empty && status !== "loading" && <div className="dashboard-empty-state"><BarChart3 /><strong>No Jira tickets found in the selected scope.</strong><p>Clear a release, sprint, feature, or created-date filter and try again.</p><button type="button" onClick={resetFilters}>Clear filters</button></div>}

      {payload && !payload.empty && <>
        {isPortfolio ? <><div className="portfolio-kpi-row">{(payload.metric_cards || []).slice(0, 4).map((metric) => <article key={metric.key}><span>{metric.title}</span><strong>{number(metric.value, metric.key.includes("pct") ? "%" : "")}</strong><p>{metric.description}</p></article>)}</div><PortfolioView payload={payload} onSquad={viewSquad} onAsk={ask} /></> : <><PrimaryKpiRow payload={payload} onInfo={openMetric} onAsk={ask} squad={context.selectedSquad} /><DeliveryAnalytics payload={payload} /><RiskAttentionPanel payload={payload} onViewIssue={focusRisk} onAsk={ask} squad={context.selectedSquad} /><ProductivityOverview payload={payload} issues={visibleIssues} onAsk={ask} />{payload.release_information?.length > 0 && <section className="release-information"><header><h3>Release Information</h3><span>Rule-based source dates</span></header>{payload.release_information.map((release) => <article key={`${release.fixversion}-${release.release_date}`}><strong>{release.fixversion}</strong><span>Release date {release.release_date || "Unavailable"}</span><span>Plan {release.release_plan_start || "—"} → {release.release_plan_end || "—"}</span><span>Actual {release.release_actual_start || "—"} → {release.release_actual_end || "—"}</span></article>)}</section>}<IssueTable payload={visibleIssues} filterOptions={options} filters={issueFilters} setFilters={setIssueFilters} onPage={(page) => setIssueFilters((current) => ({ ...current, page }))} /></>}
        {(payload.data_quality_notes || []).length > 0 && <section className="dashboard-quality-note"><CircleHelp aria-hidden="true" /><div><strong>Data quality &amp; interpretation</strong>{payload.data_quality_notes.map((note) => <p key={note}>{note}</p>)}</div></section>}
      </>}

      {!isPortfolio && <button className="back-to-portfolio" type="button" onClick={() => changeSquad("")}><ArrowLeft aria-hidden="true" /> All Squads</button>}
      <MetricInfoDrawer metric={drawerMetric} scope={context.dashboardContext()} updatedAt={payload?.generated_at} onClose={() => setDrawerMetric(null)} onAsk={(question, patch) => { setDrawerMetric(null); ask(question, patch); }} />
      <ReportGenerationDrawer open={reportOpen} scope={context.dashboardContext()} onClose={() => setReportOpen(false)} onGenerate={ask} />
    </section>
  );
}
