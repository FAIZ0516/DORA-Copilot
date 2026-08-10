import type { WorkflowDefinition } from "../../workflow/types";
import type { ChartConfig, ChartResult } from "../types/visualization";

async function post<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "The chart data could not be loaded.");
  }
  return response.json() as Promise<T>;
}

export const chartDataService = {
  query(workflow: WorkflowDefinition, chart: ChartConfig) {
    return post<ChartResult>("/api/visualizations/query", {
      workflow, group_by: chart.group_by ?? null, value: chart.value ?? null,
      calculation: chart.calculation, filters: chart.filters ?? [], limit: 50,
    });
  },
};
