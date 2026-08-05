export const WORKSPACE_SUGGESTIONS = {
  business: [
    {
      icon: "briefcase",
      title: "Work Overview",
      description: "Summarise current work by status and issue type.",
      prompt: "Summarise the current Jira workload by status category and issue type. Clearly state the reporting scope and limitations.",
    },
    {
      icon: "alert",
      title: "Delivery Risks",
      description: "Highlight ageing, impeded, and unresolved work.",
      prompt: "Highlight potential delivery risks using old unresolved issues, impeded work, missing ownership, and relevant data-quality limitations.",
    },
    {
      icon: "database",
      title: "Data Quality",
      description: "Find gaps that may affect reporting.",
      prompt: "What data-quality gaps in the Jira issues table could make management reporting misleading?",
    },
    {
      icon: "focus",
      title: "Management Focus",
      description: "Suggest areas that deserve management review.",
      prompt: "Based only on the available Jira evidence, what areas should management review next? Separate observed facts from suggestions.",
    },
  ],
  technical: [
    {
      icon: "table",
      title: "Explore Jira Data",
      description: "Understand what one Jira row represents.",
      prompt: "What does the Jira issues table represent, and what does one row mean?",
    },
    {
      icon: "workflow",
      title: "Understand Workflow",
      description: "Compare status, category, and resolution.",
      prompt: "Explain the difference between status, status category, resolution, and resolved date.",
    },
    {
      icon: "users",
      title: "Explore Squads",
      description: "List non-empty squad values.",
      prompt: "List the available squad values in the Jira issues data.",
    },
    {
      icon: "gauge",
      title: "Check DORA Metrics",
      description: "Understand available lead-time evidence.",
      prompt: "Can the current database calculate DORA Lead Time for Changes? Explain which data is available and which additional sources are required.",
    },
  ],
};

export const WORKSPACE_PLACEHOLDERS = {
  business: "Ask about workload, delivery risks, trends, or management insights...",
  technical: "Ask about tables, columns, data quality, SQL, or DORA definitions...",
};

export function getSuggestionPrompt(workspace, index) {
  return WORKSPACE_SUGGESTIONS[workspace]?.[index]?.prompt || "";
}
