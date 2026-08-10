import type { DatasetColumn, DatasetSchema, WorkflowDefinition, WorkflowNode } from "../types";

export type SchemaMap = Record<string, DatasetColumn[]>;
const numericType = (column?: DatasetColumn) => Boolean(column?.numeric || /int|numeric|decimal|real|double|float/i.test(column?.data_type ?? ""));

export function upstreamNode(workflow: WorkflowDefinition, nodeId: string): WorkflowNode | undefined {
  const edge = workflow.edges.find((item) => item.target === nodeId);
  return edge ? workflow.nodes.find((node) => node.id === edge.source) : undefined;
}

export function workflowSchemas(workflow: WorkflowDefinition, schemas: Record<string, DatasetSchema | undefined>): SchemaMap {
  const output: SchemaMap = {}; const remaining = new Map(workflow.nodes.map((node) => [node.id, node]));
  while (remaining.size) { let progressed = false; for (const [id, node] of remaining) {
    const parent = upstreamNode(workflow, id); if (parent && !output[parent.id]) continue; const incoming = parent ? output[parent.id] : [];
    if (node.type === "dataset") output[id] = schemas[String(node.config.dataset ?? "")]?.columns ?? [];
    else if (node.type === "select") output[id] = incoming.filter((column) => ((node.config.columns as string[] | undefined) ?? []).includes(column.name));
    else if (node.type === "group") { const group = incoming.find((column) => column.name === node.config.group_by); const calculation = String(node.config.calculation ?? "count"); const resultName = String(node.config.result_name || (calculation === "count" ? "issue_count" : `${calculation}_${String(node.config.value ?? "value")}`)); output[id] = [...(group ? [group] : []), { name: resultName, label: resultName.replaceAll("_", " "), data_type: "numeric", nullable: false, numeric: true, date_like: false }]; }
    else if (node.type === "join") { const joinSchema = schemas[String(node.config.dataset ?? "")]?.columns ?? []; const names = new Set(incoming.map((column) => column.name)); output[id] = [...incoming, ...joinSchema.map((column) => names.has(column.name) ? { ...column, name: `joined_${column.name}`, label: `Joined ${column.label}` } : column)]; }
    else output[id] = incoming; remaining.delete(id); progressed = true;
  } if (!progressed) break; }
  return output;
}

export function inputSchema(workflow: WorkflowDefinition, nodeId: string, outputs: SchemaMap) { const parent = upstreamNode(workflow, nodeId); return parent ? outputs[parent.id] ?? [] : []; }
export function operatorsFor(column?: DatasetColumn) {
  if (!column) return [];
  if (column.date_like || /date|time/i.test(column.data_type)) return [["before", "Before"], ["after", "After"], ["equals", "On"], ["between", "Between"]] as const;
  if (/bool/i.test(column.data_type)) return [["equals", "Is true"], ["not_equals", "Is false"]] as const;
  if (numericType(column)) return [["equals", "Equals"], ["greater_than", "Greater than"], ["greater_or_equal", "Greater than or equal"], ["less_than", "Less than"], ["less_or_equal", "Less than or equal"], ["between", "Between"]] as const;
  return [["equals", "Equals"], ["not_equals", "Does not equal"], ["contains", "Contains"], ["not_contains", "Does not contain"], ["is_empty", "Is empty"], ["is_not_empty", "Is not empty"]] as const;
}
export function configurationIssue(node: WorkflowNode, input: DatasetColumn[]) {
  if (node.type === "dataset" && !node.config.dataset) return "Choose an approved dataset.";
  if (node.type === "filter") {
    if (!input.length) return "Connect this filter to a previous step first.";
    const rules = (node.config.rules as { column?: string; operator?: string; value?: unknown }[] | undefined) ?? [node.config];
    const invalid = rules.find((rule) => rule.column && !input.some((column) => column.name === rule.column)); if (invalid) return `${String(invalid.column)} is no longer available from the previous step.`;
    const incomplete = rules.find((rule) => !rule.column || !rule.operator || (!["is_empty", "is_not_empty"].includes(String(rule.operator)) && [undefined, null, ""].includes(rule.value as string | null | undefined))); if (incomplete) return "Complete each filter condition.";
  }
  if (node.type === "select") {
    if (!input.length) return "Connect Select Columns to a previous step first.";
    const columns = (node.config.columns as string[] | undefined) ?? []; const invalid = columns.find((name) => !input.some((column) => column.name === name)); if (invalid) return `${invalid} is no longer available from the previous step.`;
    if (!columns.length) return "Select at least one column to keep.";
  }
  if (node.type === "group") {
    if (!input.length) return "Connect Group to a previous step first.";
    if (!node.config.group_by) return "Choose a field to group by.";
    if (!input.some((column) => column.name === node.config.group_by)) return `${String(node.config.group_by)} is no longer available from the previous step.`;
    if (!node.config.calculation || (!['count'].includes(String(node.config.calculation)) && !node.config.value)) return "Choose what to summarize.";
  }
  if (node.type === "join") {
    if (!input.length) return "Connect Join to a previous step first.";
    if (!node.config.dataset) return "Choose approved data to add.";
    if (!node.config.left_column || !node.config.right_column) return "Choose matching fields for this join.";
  }
  return undefined;
}
export function compatibleJoinFields(left: DatasetColumn[], right: DatasetColumn[], leftName?: string) { const selected = left.find((column) => column.name === leftName); if (!selected) return right; const normalize = (name: string) => name.toLowerCase().replaceAll("_", "").replace(/id$/, ""); return right.filter((column) => column.data_type === selected.data_type || (numericType(column) && numericType(selected)) || (column.date_like && selected.date_like)).sort((a, b) => Number(normalize(b.name) === normalize(selected.name)) - Number(normalize(a.name) === normalize(selected.name)) || a.label.localeCompare(b.label)); }