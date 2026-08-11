const RISK_COPY = {
  high_priority_open_bugs: {
    title: "High-priority defects need review",
    impact: "Unresolved high-priority defects may disrupt planned delivery or release readiness.",
    action: "Review ownership, age, and release impact with the squad.",
  },
  oldest_unresolved_days: {
    title: "Long-running work needs attention",
    impact: "Older unresolved work can hide dependency, scope, or ownership constraints.",
    action: "Inspect the oldest items and confirm the next unblock action.",
  },
  completion_pct: {
    title: "Delivery position is below the attention threshold",
    impact: "A lower end-state percentage may indicate scope pressure or work progressing late in the selected period.",
    action: "Review remaining work and validate what can be completed safely.",
  },
  impeded_work: {
    title: "Impeded work requires intervention",
    impact: "Impeded items can delay dependent work and reduce delivery predictability.",
    action: "Confirm the blocker owner and agree a dated resolution step.",
  },
  unassigned_open_work: {
    title: "Open work has no visible owner",
    impact: "Ownership gaps can delay triage and make follow-through unclear.",
    action: "Confirm whether queue ownership is intentional or assign a responsible owner.",
  },
};

function words(value = "") {
  return String(value).replaceAll("_", " ");
}

function severityFor(status, metric) {
  if (String(status).toLowerCase() === "healthy") return "Low";
  if (String(status).toLowerCase() === "needs attention") {
    return metric === "impeded_work" || metric === "high_priority_open_bugs" ? "High" : "Medium";
  }
  return "Medium";
}

export function buildRiskItems(payload) {
  const status = payload?.kpis?.status || "Monitor";
  return (payload?.attention_items || []).map((reason, index) => {
    const copy = RISK_COPY[reason.metric] || {
      title: `${words(reason.metric)} needs review`,
      impact: "The current delivery condition crossed a transparent dashboard attention rule.",
      action: "Review the supporting tickets with the squad before deciding on an intervention.",
    };
    return {
      id: `${reason.metric || "risk"}-${index}`,
      metric: reason.metric,
      value: reason.value,
      severity: severityFor(status, reason.metric),
      evidence: reason.reason || `${words(reason.metric)}: ${reason.value ?? "Unavailable"}`,
      ...copy,
    };
  });
}

export function buildPrimaryKpis(payload) {
  const kpis = payload?.kpis || {};
  const registry = payload?.metric_registry || {};
  return [
    {
      key: "completion_pct",
      title: "Sprint Progress",
      value: kpis.completion_pct,
      suffix: "%",
      tone: "blue",
      comparison: "Previous sprint comparison unavailable",
      definition: registry.completion_pct,
    },
    {
      key: "completed_work",
      title: "Completed vs Scoped",
      value: `${Number(kpis.completed_work || 0).toLocaleString()} / ${Number(kpis.total_work || 0).toLocaleString()}`,
      tone: "green",
      comparison: "Scoped tickets are not a commitment baseline",
      definition: registry.completed_work,
    },
    {
      key: "impeded_work",
      title: "Active Blockers",
      value: kpis.impeded_work ?? 0,
      tone: Number(kpis.impeded_work || 0) > 0 ? "orange" : "green",
      comparison: "Based on current Impeded status",
      definition: {
        title: "Active Blockers",
        description: "Tickets whose current Jira status is Impeded.",
        why_it_matters: "Impeded work may need an explicit owner and next action.",
        formula: "Count where status equals Impeded.",
        source_tables: ["public.tbl_gdt_dte_jira_issues"],
        suggested_questions: ["Which impeded tickets need attention first?"],
      },
    },
    {
      key: "delivery_risk",
      title: "Delivery Risk",
      value: kpis.status || "Monitor",
      tone: String(kpis.status).toLowerCase() === "needs attention" ? "red" : "amber",
      comparison: `${(kpis.reasons || []).length} transparent attention signal${(kpis.reasons || []).length === 1 ? "" : "s"}`,
      definition: {
        title: "Delivery Risk",
        description: "A deterministic status derived from visible defect, ageing, progress, impediment, and ownership signals.",
        why_it_matters: "It focuses review without replacing team judgment.",
        formula: "Configured attention thresholds; no model-generated risk score.",
        source_tables: ["public.tbl_gdt_dte_jira_issues"],
        suggested_questions: ["Why is this squad at risk?"],
      },
    },
  ];
}

export function buildFeatureOptions(issuePayload) {
  return [...new Set((issuePayload?.items || []).map((item) => item.feature_link).filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b)));
}

export function filterIssuesForFeature(issuePayload, selectedFeature) {
  if (!issuePayload || !selectedFeature) return issuePayload;
  const items = (issuePayload.items || []).filter((item) => item.feature_link === selectedFeature);
  return { ...issuePayload, items, visible_total: items.length, page_limited_filter: true };
}

export function buildWorkloadRows(issuePayload) {
  const counts = new Map();
  (issuePayload?.items || []).forEach((issue) => {
    if (issue.status_category === "Done") return;
    const assignee = issue.assignee || "Unassigned";
    counts.set(assignee, (counts.get(assignee) || 0) + 1);
  });
  return [...counts.entries()]
    .map(([assignee, issue_count]) => ({ assignee, issue_count }))
    .sort((a, b) => b.issue_count - a.issue_count || a.assignee.localeCompare(b.assignee))
    .slice(0, 8);
}

export function buildSupportSignals(payload, issuePayload) {
  const items = issuePayload?.items || [];
  const signals = [];
  const unassigned = items.filter((item) => !item.assignee && item.status_category !== "Done").length;
  const longRunning = items.filter((item) => Number(item.age_days || 0) > 60).length;
  const impeded = Number(payload?.kpis?.impeded_work || 0);
  if (unassigned) signals.push({ label: "Workload Balance", value: unassigned, detail: "active items on this table page are unassigned" });
  if (longRunning) signals.push({ label: "Delivery Support Needed", value: longRunning, detail: "items on this table page are older than 60 days" });
  if (impeded) signals.push({ label: "Needs Attention", value: impeded, detail: "items in the selected scope are currently impeded" });
  return signals;
}
