import type { WorkflowDefinition } from "../../workflow/types";

export type ChartType = "bar" | "line" | "donut" | "kpi" | "table";
export type Calculation = "count" | "sum" | "average" | "minimum" | "maximum" | "percentage";
export interface ChartFilter { column: string; operator: "equals" | "not_equals" | "contains" | "in"; value: unknown }
export interface ChartConfig {
  id: string;
  title: string;
  subtitle?: string;
  type: ChartType;
  group_by?: string | null;
  value?: string | null;
  calculation: Calculation;
  filters?: ChartFilter[];
}
export interface ChartDatum { label: string; value: number }
export interface ChartResult { data: ChartDatum[]; row_count: number; execution_time_ms: number }
export interface VisualizationDashboard {
  id: string;
  name: string;
  sourceWorkflowId?: string;
  workflow: WorkflowDefinition;
  charts: ChartConfig[];
  filters: ChartFilter[];
  savedAt: string;
}
