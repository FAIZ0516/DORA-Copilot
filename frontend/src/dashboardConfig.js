export const DASHBOARD_KPIS = [
  {
    key: "total_issues",
    label: "Total Issues",
    prompt: "Explain the current Jira issue composition by issue type and status category.",
    note: "All Jira rows in scope",
  },
  {
    key: "open_work_count",
    label: "Open Work",
    prompt: "Analyse the current open Jira work by age, issue type, priority and squad coverage.",
    note: "Local definition: unresolved and not Done",
  },
  {
    key: "impeded_issues",
    label: "Impeded Issues",
    prompt: "Analyse currently impeded Jira issues by priority, age and squad coverage without exposing sensitive issue details.",
    note: "Current status only; history unavailable",
  },
  {
    key: "missing_squad_count",
    label: "Missing Squad",
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
  return `Analyse current Jira issues where issuetype is '${issueType}'.`;
}

export function ageingPrompt(bucket) {
  return `Analyse open Jira issues aged '${bucket}' and summarise their status, priority and ownership coverage.`;
}

export function ageBucketForDays(days) {
  if (days == null) return "Unknown created date";
  if (days < 30) return "Less than 30 days";
  if (days <= 60) return "30-60 days";
  if (days <= 90) return "61-90 days";
  return "More than 90 days";
}
