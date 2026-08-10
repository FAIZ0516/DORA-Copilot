import type { ChartConfig, ChartDatum, ChartFilter } from "../../visualize/types/visualization";

export interface DashboardContext {
  dataset: string;
  workflowName: string;
  filters: ChartFilter[];
  charts: Array<ChartConfig & { data?: ChartDatum[] }>;
  selectedChart?: ChartConfig;
  selectedCategory?: string;
}
export interface AssistantResponse { answer: string; followUps: string[]; prototype: boolean }
export interface ZaraAssistantService { ask(question: string, context: DashboardContext): Promise<AssistantResponse> }
export interface AssistantMessage { id: string; role: "user" | "assistant"; content: string; prototype?: boolean; followUps?: string[] }
