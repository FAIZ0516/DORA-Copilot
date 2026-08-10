export const ROLE_DASHBOARD_CONFIG = {
  scrum_master: {
    role: "scrum_master",
    workspace: "technical",
    label: "Scrum Master",
    dashboardTitle: "Squad Performance Dashboard",
    dashboardSubtitle: "Sprint health, delivery risks, workload balance, issue evidence, and next actions.",
    access: ["Sprint Operations", "Team Delivery", "Issue-Level Analysis"],
    initialQuestions: [
      "Is the current sprint on track?",
      "Which issues are blocking sprint completion?",
      "Show unresolved work older than seven days.",
      "Where is workload concentrated and who may need support?",
      "What actions should the Scrum Master take today?",
    ],
    followUpQuestions: [
      "Which issue should we address first?",
      "Explain the main ageing risk.",
      "Compare this sprint with the previous sprint.",
    ],
  },
  head_of_department: {
    role: "head_of_department",
    workspace: "business",
    label: "Head of Department",
    dashboardTitle: "Department Performance Dashboard",
    dashboardSubtitle: "Executive portfolio health, squad comparison, release signals, and strategic delivery risk.",
    access: ["Department Overview", "Squad Comparison", "Release & Strategic Risk"],
    initialQuestions: [
      "Which squads are currently at risk?",
      "Compare delivery performance across all squads.",
      "Are we ready for the next release?",
      "What are the top department-level delivery risks?",
      "Summarise department performance for an executive meeting.",
    ],
    followUpQuestions: [
      "What should management prioritise this week?",
      "Which squad needs the earliest intervention?",
      "Explain the strongest cross-squad pattern.",
    ],
  },
};

export function getRoleDashboardConfig(role) {
  return ROLE_DASHBOARD_CONFIG[role] || ROLE_DASHBOARD_CONFIG.scrum_master;
}

export function workspaceForRole(role) {
  return getRoleDashboardConfig(role).workspace;
}
