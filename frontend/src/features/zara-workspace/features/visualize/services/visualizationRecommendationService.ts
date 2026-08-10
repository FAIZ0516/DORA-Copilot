import type { WorkflowDefinition } from "../../workflow/types";
import type { ChartConfig } from "../types/visualization";

export const visualizationRecommendationService = {
  async recommend(workflow: WorkflowDefinition): Promise<ChartConfig[]> {
    const response = await fetch("/api/visualizations/recommend", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workflow }) });
    if (!response.ok) throw new Error("Zara could not recommend charts for this output.");
    const payload = await response.json() as { charts: Omit<ChartConfig, "id">[] };
    return payload.charts.map((chart) => ({ ...chart, id: crypto.randomUUID() }));
  },
};
