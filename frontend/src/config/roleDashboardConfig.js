export const UNIFIED_DASHBOARD_CONFIG = {
  workspace: "technical",
  label: "Engineering Performance",
  dashboardTitle: "All DCP Squads Overview",
  dashboardSubtitle: "Portfolio signals, squad drill-down, delivery risk, and supporting Jira ticket evidence.",
  initialQuestions: [
    "Which squads currently need attention?",
    "Which squad has the most open bugs?",
    "Summarise the current dashboard scope.",
    "What should engineering prioritise next?",
  ],
  followUpQuestions: [],
};

export function getRoleDashboardConfig() {
  return UNIFIED_DASHBOARD_CONFIG;
}

export function workspaceForRole() {
  return UNIFIED_DASHBOARD_CONFIG.workspace;
}
