import type { WorkflowDefinition } from "../../workflow/types";
import type { ChartConfig, ChartDatum, ChartFilter } from "../../visualize/types/visualization";
import type { DashboardContext } from "../types/assistant";

export function buildDashboardContext(args: { workflow: WorkflowDefinition; dataset: string; charts: ChartConfig[]; chartData: Record<string, ChartDatum[]>; filters: ChartFilter[]; selectedChart?: ChartConfig; selectedCategory?: string }): DashboardContext {
  return {
    dataset: args.dataset,
    workflowName: args.workflow.name,
    filters: args.filters,
    charts: args.charts.map((chart) => ({ ...chart, data: args.chartData[chart.id] })),
    selectedChart: args.selectedChart,
    selectedCategory: args.selectedCategory,
  };
}
