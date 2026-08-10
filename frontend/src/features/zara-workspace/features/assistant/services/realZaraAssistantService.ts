import type { AssistantResponse, DashboardContext, ZaraAssistantService } from "../types/assistant";

export class RealZaraAssistantService implements ZaraAssistantService {
  async ask(question: string, context: DashboardContext): Promise<AssistantResponse> {
    const response = await fetch("/api/assistant/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, context }) });
    if (!response.ok) throw new Error("Zara AI is unavailable.");
    return response.json() as Promise<AssistantResponse>;
  }
}
