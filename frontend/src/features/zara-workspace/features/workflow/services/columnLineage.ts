import { upstreamNode } from "./schemaPropagation";
import type { DatasetSchema, DatasetSummary, FilterRule, NodeType, WorkflowDefinition, WorkflowNode } from "../types";

export type LineageOperation = Extract<NodeType, "filter" | "group" | "join" | "calculate">;
export interface ColumnTransformation { type: LineageOperation; description: string; }
export interface ColumnLineage { name: string; sourceDataset?: string; transformations: ColumnTransformation[]; }

const clone = (lineage: Map<string, ColumnLineage>) => new Map([...lineage].map(([name, detail]) => [name, { ...detail, transformations: [...detail.transformations] }]));
const humanize = (name: string) => name.replaceAll("_", " ");
const operatorLabel: Record<string, string> = { equals: "=", not_equals: "is not", contains: "contains", not_contains: "does not contain", starts_with: "starts with", greater_than: ">", greater_or_equal: "at least", less_than: "<", less_or_equal: "at most", before: "before", after: "after", between: "between", is_empty: "is empty", is_not_empty: "is not empty" };
function filterDescription(rule: FilterRule) { const operator = operatorLabel[rule.operator] ?? humanize(rule.operator); if (["is_empty", "is_not_empty"].includes(rule.operator)) return `${humanize(rule.column)} ${operator}`; if (rule.operator === "between") return `${humanize(rule.column)} between ${String(rule.value)} and ${String(rule.value_to ?? "")}`; return `${humanize(rule.column)} ${operator} ${String(rule.value ?? "")}`.trim(); }
function filterRules(node: WorkflowNode): FilterRule[] { return (node.config.rules as FilterRule[] | undefined) ?? [{ id: "legacy", column: String(node.config.column ?? ""), operator: String(node.config.operator ?? "equals"), value: node.config.value }]; }
function groupDescription(node: WorkflowNode) { const calculation = String(node.config.calculation ?? "count"); const field = String(node.config.value ?? ""); const labels: Record<string, string> = { count: "Count of records", count_distinct: `Count of distinct ${humanize(field)}`, sum: `Total ${humanize(field)}`, average: `Average ${humanize(field)}`, minimum: `Minimum ${humanize(field)}`, maximum: `Maximum ${humanize(field)}` }; return labels[calculation] ?? humanize(calculation); }

/** Derives preview styling from the workflow definition, never from column-name heuristics. */
export function outputColumnLineage(workflow: WorkflowDefinition, schemas: Record<string, DatasetSchema | undefined>, datasets: DatasetSummary[]) {
  const cache = new Map<string, Map<string, ColumnLineage>>();
  const derive = (node: WorkflowNode): Map<string, ColumnLineage> => {
    const cached = cache.get(node.id); if (cached) return clone(cached);
    const parent = upstreamNode(workflow, node.id); const incoming = parent ? derive(parent) : new Map<string, ColumnLineage>(); let output = clone(incoming);
    if (node.type === "dataset") { const schema = schemas[String(node.config.dataset ?? "")]; output = new Map((schema?.columns ?? []).map((column) => [column.name, { name: column.name, sourceDataset: schema?.dataset.name, transformations: [] }])); }
    if (node.type === "filter") for (const rule of filterRules(node)) { const current = output.get(rule.column); if (current?.name) current.transformations.push({ type: "filter", description: filterDescription(rule) }); }
    if (node.type === "select") { const selected = new Set((node.config.columns as string[] | undefined) ?? []); output = new Map([...output].filter(([name]) => selected.has(name))); }
    if (node.type === "group") { const groupBy = String(node.config.group_by ?? ""); const grouped = output.get(groupBy); const result = String(node.config.result_name || (String(node.config.calculation ?? "count") === "count" ? "issue_count" : `${String(node.config.calculation ?? "value")}_${String(node.config.value ?? "value")}`)); output = new Map(); if (grouped) output.set(groupBy, { ...grouped, transformations: [...grouped.transformations, { type: "group", description: `Grouped by ${humanize(groupBy)}` }] }); output.set(result, { name: result, sourceDataset: grouped?.sourceDataset, transformations: [{ type: "group", description: `Calculated by Group: ${groupDescription(node)}` }] }); }
    if (node.type === "join") { const source = schemas[String(node.config.dataset ?? "")]; const sourceName = datasets.find((dataset) => dataset.id === node.config.dataset)?.name ?? source?.dataset.name ?? "approved dataset"; for (const column of source?.columns ?? []) { const outputName = output.has(column.name) ? `joined_${column.name}` : column.name; output.set(outputName, { name: outputName, sourceDataset: sourceName, transformations: [{ type: "join", description: `Added from ${sourceName} via Join` }] }); } }
    if (node.type === "calculate") { const result = String(node.config.result_name ?? node.config.output_column ?? ""); if (result) output.set(result, { name: result, transformations: [{ type: "calculate", description: String(node.config.description ?? node.config.formula ?? "Calculated field") }] }); }
    cache.set(node.id, clone(output)); return output;
  };
  const outputNode = workflow.nodes.find((node) => node.type === "output"); return outputNode ? derive(outputNode) : new Map<string, ColumnLineage>();
}