import MetricChart from "./MetricChart";
import { buildSupportSignals, buildWorkloadRows } from "../dashboardPresentation";

function ChartCard({ eyebrow, title, note, chart, emptyMessage }) {
  return (
    <section className="analytics-card">
      <header>
        <div><p>{eyebrow}</p><h3>{title}</h3></div>
      </header>
      {chart?.data?.length ? <MetricChart chart={chart} /> : <div className="analytics-empty">{emptyMessage}</div>}
      {note && <p className="analytics-note">{note}</p>}
    </section>
  );
}

export function DeliveryAnalytics({ payload }) {
  const kpis = payload?.kpis || {};
  const deliveryChart = {
    type: "stacked_bar",
    title: "Current Delivery Position",
    x_key: "scope",
    x_label: "Selected scope",
    series: [
      { key: "completed", label: "End-state work", unit: "issues" },
      { key: "in_progress", label: "In progress", unit: "issues" },
      { key: "to_do", label: "To do", unit: "issues" },
    ],
    data: [{
      scope: payload?.squad || "Current scope",
      completed: Number(kpis.completed_work || 0),
      in_progress: Number(kpis.in_progress_work || 0),
      to_do: Number(kpis.todo_work || 0),
    }],
  };
  const statusChart = {
    type: "horizontal_bar",
    title: "Work Status Distribution",
    x_key: "status_category",
    x_label: "Jira status category",
    series: [{ key: "issue_count", label: "Issues", unit: "issues" }],
    data: payload?.work_status || [],
  };
  return (
    <div className="delivery-analytics-grid" data-section="analytics">
      <ChartCard
        eyebrow="Delivery overview"
        title="Sprint Delivery Position"
        chart={deliveryChart}
        note="A current-scope snapshot. The backend does not expose commitment history or a historical sprint trajectory."
        emptyMessage="No delivery-position data is available for this scope."
      />
      <ChartCard
        eyebrow="Workflow distribution"
        title="Work Status"
        chart={statusChart}
        note="Done is a Jira end-state and may include rejected or cancelled work."
        emptyMessage="No status distribution is available for this scope."
      />
    </div>
  );
}

export function ProductivityOverview({ payload, issues, onAsk }) {
  const rows = buildWorkloadRows(issues);
  const signals = buildSupportSignals(payload, issues);
  const chart = {
    type: "horizontal_bar",
    title: "Active Workload by Team Member",
    x_key: "assignee",
    x_label: "Assignee",
    series: [{ key: "issue_count", label: "Active issues", unit: "issues" }],
    data: rows,
  };
  return (
    <section className="productivity-overview" id="productivity-overview" data-section="productivity">
      <header className="section-heading-row">
        <div><p>Decision-support signals</p><h3>Squad Productivity Overview</h3></div>
        <button type="button" onClick={() => onAsk("Explain the current workload distribution and support signals. Consider work complexity, leave, dependencies, and data limitations before recommending action.")}>Ask Zara</button>
      </header>
      <div className="productivity-grid">
        <div className="productivity-chart">
          {rows.length ? <MetricChart chart={chart} /> : <div className="analytics-empty">No assignee workload is visible on the current issue-table page.</div>}
          <p className="analytics-note">This distribution uses the currently loaded issue-table page because a full-scope assignee aggregate is not exposed by the backend.</p>
        </div>
        <div className="support-signals" aria-label="Delivery support signals">
          <h4>Support Signals</h4>
          {signals.length ? signals.map((signal) => (
            <article key={signal.label}><span>{signal.label}</span><strong>{signal.value}</strong><p>{signal.detail}</p></article>
          )) : <div className="analytics-empty">No support signals were detected from the currently available data.</div>}
        </div>
      </div>
      <p className="productivity-disclaimer">Productivity indicators are decision-support signals and should be interpreted together with work complexity, leave, dependencies and team context.</p>
    </section>
  );
}
