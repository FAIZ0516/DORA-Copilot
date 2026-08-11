export const DASHBOARD_KPIS = [
  {
    key: "total_issues",
    label: "Total Tickets",
    description: "The total number of Jira tickets within the selected project scope, across all statuses and types. This is your baseline — it shows the full size of the tracked backlog including done, in-progress, and open work.",
    prompt: "Explain the current Jira ticket composition by ticket type and status category.",
    note: "All Jira rows in scope",
  },
  {
    key: "open_work_count",
    label: "Open Work",
    description: "Tickets that are unresolved and not in a Done status category. This represents your active workload — work that still needs attention. A high open work count may signal delivery bottlenecks or resource constraints.",
    prompt: "Analyse the current open Jira work by age, ticket type, priority and squad coverage.",
    note: "Local definition: unresolved and not Done",
  },
  {
    key: "impeded_issues",
    label: "Impeded Tickets",
    description: "Tickets currently marked with an impeded/blocked status. These are stuck and cannot progress until the blocker is resolved. Tracking impeded items helps identify systemic obstacles in your delivery pipeline.",
    prompt: "Analyse currently impeded Jira tickets by priority, age and squad coverage without exposing sensitive ticket details.",
    note: "Current status only; history unavailable",
  },
  {
    key: "missing_squad_count",
    label: "Missing Squad",
    description: "Tickets with a blank or null squad (team) assignment. Unassigned work creates blind spots in team-level reporting and capacity planning. A high percentage here means you can't accurately attribute work to specific teams.",
    prompt: "Explain the impact of missing squad mappings on team-level reporting.",
    note: "Blank or null squad mapping",
  },
];

export function kpiCards(kpis = {}) {
  return DASHBOARD_KPIS.map((definition) => ({
    ...definition,
    value: Number(kpis[definition.key] || 0),
    percentage:
      definition.key === "missing_squad_count"
        ? Number(kpis.missing_squad_pct || 0)
        : null,
  }));
}

export function issueTypePrompt(issueType) {
  return `Analyse current Jira tickets where issuetype is '${issueType}'.`;
}

export function ageingPrompt(bucket) {
  return `Analyse open Jira tickets aged '${bucket}' and summarise their status, priority and ownership coverage.`;
}

export function ageBucketForDays(days) {
  if (days == null) return "Unknown created date";
  if (days < 30) return "Less than 30 days";
  if (days <= 60) return "30-60 days";
  if (days <= 90) return "61-90 days";
  return "More than 90 days";
}
