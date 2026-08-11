import type { AssistantResponse, DashboardContext, ZaraAssistantService } from "../types/assistant";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

/**
 * Live workspace assistant.
 *
 * This used to POST to `/api/assistant/ask`, an endpoint that was never built,
 * so every question in live mode failed with "Zara AI is unavailable." It now
 * uses `/api/chat` -- the same governed, DoraDB-grounded agent the main
 * dashboard talks to -- so answers come from real data instead of a 404.
 */
export class RealZaraAssistantService implements ZaraAssistantService {
  private conversationId: string | null = null;

  async ask(question: string, context: DashboardContext): Promise<AssistantResponse> {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: describeContext(question, context),
        conversation_id: this.conversationId,
        workspace: "technical",
      }),
    });
    if (!response.ok) throw new Error("Zara could not reach the analysis service.");
    const payload = await response.json();
    const conversationId = payload?.metadata?.conversation_id;
    if (typeof conversationId === "string") this.conversationId = conversationId;
    return {
      answer: payload.answer,
      // The chat API does not emit follow-up chips; the panel renders none.
      followUps: [],
      prototype: false,
    };
  }
}

/**
 * The workspace context describes a user-built workflow, not a dashboard
 * scope, so it cannot map onto the typed `dashboard_context` field. State it
 * in the message instead, where the agent can weigh it as ordinary context.
 */
function describeContext(question: string, context: DashboardContext): string {
  const parts: string[] = [];
  if (context.dataset) parts.push(`prepared dataset "${context.dataset}"`);
  if (context.workflowName) parts.push(`workflow "${context.workflowName}"`);
  if (context.selectedCategory) parts.push(`selected category "${context.selectedCategory}"`);
  if (context.filters?.length) {
    parts.push(
      `active filters ${context.filters
        .map((filter) => `${filter.column} ${filter.operator} ${String(filter.value)}`)
        .join(", ")}`,
    );
  }
  if (!parts.length) return question;
  const preamble = `I am looking at the Zara data workspace (${parts.join("; ")}).`;
  // Keep inside the API's 2000-character message limit without truncating the
  // user's actual question when workspace labels or filters are unusually long.
  const roomForContext = Math.max(0, 1999 - question.length);
  return roomForContext ? `${preamble.slice(0, roomForContext)} ${question}` : question.slice(0, 2000);
}
