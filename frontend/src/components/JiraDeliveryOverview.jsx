import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  RefreshCw,
} from "lucide-react";
import {
  ageingPrompt,
  issueTypePrompt,
  kpiCards,
} from "../dashboardConfig";
import { loadJiraDashboard } from "../services/dashboard";

function Tooltip({ text }) {
  if (!text) return null;
  return (
    <span className="jira-tooltip-wrapper">
      <CircleHelp size={12} className="jira-tooltip-icon" aria-hidden="true" />
      <span className="jira-tooltip" role="tooltip">{text}</span>
    </span>
  );
}

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function Breakdown({ title, rows, labelKey, note, onSelect, tooltip }) {
  const maximum = Math.max(1, ...rows.map((row) => Number(row.issue_count || 0)));
  return (
    <section className="jira-breakdown" aria-label={title}>
      <h4>
        {title}
        <Tooltip text={tooltip} />
      </h4>
      <div className="jira-breakdown-bars">
        {rows.map((row) => {
          const label = String(row[labelKey]);
          return (
            <button key={label} type="button" onClick={() => onSelect(label)}>
              <span className="jira-bar-label">{label}</span>
              <span className="jira-bar-track" aria-hidden="true">
                <i style={{ width: `${Math.max(2, Number(row.issue_count || 0) / maximum * 100)}%` }} />
              </span>
              <strong>{formatCount(row.issue_count)}</strong>
            </button>
          );
        })}
      </div>
      <p><CircleHelp size={13} aria-hidden="true" />{note}</p>
    </section>
  );
}

export default function JiraDeliveryOverview({ projectKey, onPrompt, disabled = false }) {
  const [dashboard, setDashboard] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);

  async function load({ refresh = false, signal } = {}) {
    if (!projectKey) return;
    setStatus("loading");
    setError("");
    try {
      const payload = await loadJiraDashboard(projectKey, { refresh, signal });
      setDashboard(payload);
      setStatus("ready");
    } catch (loadError) {
      if (loadError.name === "AbortError") return;
      setError(loadError.message);
      setStatus("error");
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    load({ signal: controller.signal });
    return () => controller.abort();
  }, [projectKey]);

  const cards = useMemo(() => kpiCards(dashboard?.kpis), [dashboard]);
  const refreshed = dashboard?.refreshed_at
    ? new Date(dashboard.refreshed_at).toLocaleString()
    : "Not loaded";

  return (
    <section className="jira-delivery-overview" aria-labelledby="jira-overview-title">
      <header className="jira-overview-header">
        <div>
          <h3 id="jira-overview-title">Jira Delivery Overview</h3>
          <p>Current snapshot of Jira work for the selected project scope</p>
        </div>
        <div className="jira-overview-actions">
          <span>Last refreshed: {refreshed}</span>
          <button
            type="button"
            onClick={() => load({ refresh: true })}
            disabled={status === "loading"}
            title="Refresh dashboard data"
            aria-label="Refresh Jira delivery overview"
          >
            <RefreshCw size={15} className={status === "loading" ? "is-spinning" : ""} />
          </button>
          <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
            {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            {expanded ? "Collapse" : "Expand"}
          </button>
        </div>
      </header>

      {status === "loading" && !dashboard && (
        <div className="jira-kpi-grid" aria-label="Loading Jira overview" role="status">
          {[0, 1, 2, 3].map((item) => <span className="jira-kpi-skeleton" key={item} />)}
        </div>
      )}
      {status === "error" && !dashboard && (
        <div className="jira-dashboard-error" role="alert">
          <AlertTriangle size={17} />
          <span>{error}</span>
          <button type="button" onClick={() => load()}>Retry</button>
        </div>
      )}
      {dashboard?.empty && status !== "loading" && (
        <div className="jira-dashboard-empty">No Jira issues matched the selected project scope.</div>
      )}
      {dashboard && !dashboard.empty && (
        <>
          <div className="jira-kpi-grid">
            {cards.map((card) => (
              <button
                key={card.key}
                type="button"
                onClick={() => onPrompt(card.prompt)}
                disabled={disabled}
                aria-label={`${card.label}: ${formatCount(card.value)}. ${card.description}`}
              >
                <span>
                  {card.label}
                  <Tooltip text={card.description} />
                </span>
                <strong>{formatCount(card.value)}</strong>
                {card.percentage != null && <b>{card.percentage.toFixed(2)}% of total</b>}
                <small>{card.note}</small>
                <em>View details</em>
              </button>
            ))}
          </div>

          {expanded && (
            <div className="jira-dashboard-expanded">
              <Breakdown
                title="Issues by Status Category"
                rows={dashboard.status_categories}
                labelKey="status_category"
                onSelect={(label) => onPrompt(`Explain current Jira issues in the '${label}' status category.`)}
                note="Done is an end-state and may include rejected or cancelled work."
                tooltip="Groups all issues by their Jira status category (To Do, In Progress, Done, etc.). This shows your workflow distribution — how much work is waiting, active, or completed. Click any bar to ask the AI for a detailed breakdown."
              />
              <Breakdown
                title="Issues by Issue Type"
                rows={dashboard.issue_types}
                labelKey="issuetype"
                onSelect={(label) => onPrompt(issueTypePrompt(label))}
                note="Issue types are not equal units of effort, productivity, or value."
                tooltip="Breaks down issues by type (Bug, Story, Task, Epic, etc.). Different types serve different purposes — bugs need fixing, stories deliver features, tasks cover maintenance. Click a bar to explore a specific type."
              />
              <Breakdown
                title="Ageing of Open Work"
                rows={dashboard.open_ageing}
                labelKey="ageing_bucket"
                onSelect={(label) => onPrompt(ageingPrompt(label))}
                note="Calendar age from created date; not cycle time or DORA lead time."
                tooltip="How long open issues have been sitting unresolved, grouped into age buckets. Older issues may indicate neglect, blockers, or deprioritisation. This is calendar age — not the same as DORA lead time or cycle time metrics."
              />
              <section className="jira-quality-panel" aria-label="Jira data quality">
                <h4>
                  Data Quality
                  <Tooltip text="Checks the completeness and consistency of Jira issue metadata. These metrics help you assess how reliable your data is. Issues with missing or inconsistent fields may skew team-level reports and DORA metric calculations." />
                </h4>
                <dl>
                  <div><dt>Missing squad</dt><dd>{formatCount(dashboard.data_quality.missing_squad_count)}</dd></div>
                  <div><dt>Missing assignee</dt><dd>{formatCount(dashboard.data_quality.missing_assignee_count)}</dd></div>
                  <div><dt>Done without resolved date</dt><dd>{formatCount(dashboard.data_quality.done_without_resolved_count)}</dd></div>
                  <div><dt>Resolved before created</dt><dd>{formatCount(dashboard.data_quality.invalid_resolution_interval_count)}</dd></div>
                </dl>
                <p>Aggregate completeness checks only. No issue text or identities are displayed.</p>
              </section>
            </div>
          )}
        </>
      )}
    </section>
  );
}
