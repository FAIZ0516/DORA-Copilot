import type { AssistantResponse, DashboardContext, ZaraAssistantService } from "../types/assistant";

function leadingCategory(context: DashboardContext, token: string) {
  const chart = context.charts.find((item) => item.title.toLowerCase().includes(token) || item.group_by?.toLowerCase().includes(token));
  return chart?.data?.slice().sort((a, b) => b.value - a.value)[0];
}

export class MockZaraAssistantService implements ZaraAssistantService {
  async ask(question: string, context: DashboardContext): Promise<AssistantResponse> {
    await new Promise((resolve) => window.setTimeout(resolve, 450));
    const normalized = question.toLowerCase();
    const status = leadingCategory(context, "status");
    const squad = leadingCategory(context, "squad") ?? leadingCategory(context, "team");
    let answer: string;
    if (normalized.includes("why") || normalized.includes("blocked")) {
      answer = `${squad?.label ?? "The leading squad"} has the greatest concentration of work in the current view${squad ? ` (${squad.value} records)` : ""}. The prepared output suggests that unresolved workflow states are concentrated there. Review the underlying issues and their dependencies before treating this as a causal conclusion.`;
    } else if (normalized.includes("which squad") || normalized.includes("attention")) {
      answer = `${squad?.label ?? "The highest-volume squad"} needs attention first because it has the largest record count in the current prepared output. Open its underlying rows to check assignees, status, and aging details.`;
    } else if (normalized.includes("changed") || normalized.includes("previous")) {
      answer = `The current view is led by ${status?.label ?? "one workflow state"}${status ? ` with ${status.value} records` : ""}. A true previous-period comparison needs a comparable sprint or date field; Zara has not invented one where the prepared output does not provide it.`;
    } else if (normalized.includes("issue type") || normalized.includes("delay")) {
      answer = `The current output does not provide enough causal evidence to attribute delays to one issue type. Add Issue Type and a date or aging field in Prepare, then refresh this view for a stronger comparison.`;
    } else {
      answer = `This dashboard contains ${context.charts.length} visualizations for ${context.dataset}. ${status ? `${status.label} is the largest status category in the current view.` : "Open a chart or select a category and I can focus the explanation."}`;
    }
    return { answer, prototype: true, followUps: ["View affected issues", "Which squad contributes most?", "Show blockers only", "Create a chart", "What should we investigate first?"] };
  }
}
