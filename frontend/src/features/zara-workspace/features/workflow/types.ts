export type NodeType = "dataset" | "filter" | "select" | "calculate" | "group" | "join" | "output";

export interface Point { x: number; y: number }
export interface WorkflowNode {
  id: string;
  type: NodeType;
  config: Record<string, unknown>;
  position: Point;
}
export interface WorkflowEdge { id: string; source: string; target: string }
export interface WorkflowDefinition {
  id?: string;
  name: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}
export interface DatasetSummary {
  id: string;
  name: string;
  description: string;
  schema_name: string;
  table_name: string;
  relation_type: string;
  column_count: number;
  approximate_rows: number | null;
}
export interface DatasetColumn {
  name: string;
  label: string;
  data_type: string;
  nullable: boolean;
  numeric: boolean;
  date_like: boolean;
}
export interface DatasetSchema { dataset: DatasetSummary; columns: DatasetColumn[] }
export interface PreviewResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  preview_limit: number;
  truncated: boolean;
  execution_time_ms: number;
}
export interface FilterRule { id: string; column: string; operator: string; value: unknown; value_to?: unknown }

export const NODE_LABELS: Record<NodeType, string> = {
  dataset: "Input Dataset", filter: "Filter", select: "Select Columns",
  calculate: "Calculate", group: "Group", join: "Join", output: "Output Dataset",
};

export function nodeSummary(node: WorkflowNode, dataset?: DatasetSummary): string {
  if (node.type === "dataset") return dataset?.name ?? "Choose a dataset";
  if (node.type === "filter") {
    const rules = node.config.rules as FilterRule[] | undefined;
    if (rules?.length) return `${rules.length} condition${rules.length === 1 ? "" : "s"} · match ${String(node.config.match ?? "all")}`;
    const operator = String(node.config.operator ?? "").replaceAll("_", " ");
    return node.config.column ? `${String(node.config.column)} ${operator} ${String(node.config.value ?? "")}`.trim() : "Set a rule";
  }
  if (node.type === "select") return `${(node.config.columns as string[] | undefined)?.length ?? 0} columns`;
  if (node.type === "group") return node.config.group_by ? `${String(node.config.group_by)} · ${String(node.config.result_name ?? "Issue count")}` : "Set up summary";
  if (node.type === "join") return node.config.dataset ? node.config.left_column && node.config.right_column ? `Match ${String(node.config.left_column)} to ${String(node.config.right_column)}` : "Choose matching fields" : "Choose data to combine";
  if (node.type === "output") return "Ready for preview";
  return "Configure this step";
}

export function isConfigured(node: WorkflowNode): boolean {
  if (node.type === "dataset") return Boolean(node.config.dataset);
  if (node.type === "filter") {
    const rules = (node.config.rules as FilterRule[] | undefined) ?? [{ id: "legacy", column: String(node.config.column ?? ""), operator: String(node.config.operator ?? ""), value: node.config.value }];
    return rules.length > 0 && rules.every((rule) => Boolean(rule.column && rule.operator && (["is_empty", "is_not_empty"].includes(rule.operator) || ![undefined, null, ""].includes(rule.value as never))));
  }
  if (node.type === "select") return Boolean((node.config.columns as string[] | undefined)?.length);
  if (node.type === "group") return Boolean(node.config.group_by && node.config.calculation && (["count"].includes(String(node.config.calculation)) || node.config.value));
  if (node.type === "join") return Boolean(node.config.dataset && node.config.left_column && node.config.right_column);
  if (node.type === "output") return true;
  return false;
}
