import type { DatasetColumn, DatasetSchema, DatasetSummary, FilterRule, PreviewResult, WorkflowDefinition, WorkflowNode } from "../features/workflow/types";
import type { WorkspaceService } from "./workspaceService";

type DataRow = Record<string, unknown>;

const jiraRows: DataRow[] = [
  { key: "DCPM-142", summary: "Payment retry telemetry", status: "In Progress", dcpsquad: "Atlas", assignee: "Aisha", priority: "High", issue_type: "Story", story_points: 8, sprint: "Sprint 24", release: "2026.08", created: "2026-07-29" },
  { key: "DCPM-143", summary: "Resolve deployment permission", status: "Blocked", dcpsquad: "Atlas", assignee: "Daniel", priority: "Highest", issue_type: "Bug", story_points: 5, sprint: "Sprint 24", release: "2026.08", created: "2026-07-30" },
  { key: "DCPM-147", summary: "Customer profile cache", status: "To Do", dcpsquad: "Beacon", assignee: "Mei", priority: "Medium", issue_type: "Story", story_points: 5, sprint: "Sprint 24", release: "2026.08", created: "2026-08-01" },
  { key: "DCPM-150", summary: "Release readiness checks", status: "In Progress", dcpsquad: "Beacon", assignee: "Kumar", priority: "High", issue_type: "Task", story_points: 3, sprint: "Sprint 24", release: "2026.08", created: "2026-08-02" },
  { key: "DCPM-151", summary: "Audit access history", status: "Blocked", dcpsquad: "Cobalt", assignee: "Nadia", priority: "High", issue_type: "Story", story_points: 8, sprint: "Sprint 24", release: "2026.09", created: "2026-08-03" },
  { key: "DCPM-153", summary: "Improve error recovery", status: "In Review", dcpsquad: "Cobalt", assignee: "Farid", priority: "Medium", issue_type: "Bug", story_points: 3, sprint: "Sprint 24", release: "2026.09", created: "2026-08-04" },
  { key: "DCPM-155", summary: "Portfolio metric definitions", status: "To Do", dcpsquad: "Atlas", assignee: "Aisha", priority: "Medium", issue_type: "Task", story_points: 2, sprint: "Sprint 25", release: "2026.09", created: "2026-08-05" },
  { key: "DCPM-158", summary: "Dependency risk panel", status: "Done", dcpsquad: "Beacon", assignee: "Mei", priority: "Low", issue_type: "Story", story_points: 5, sprint: "Sprint 23", release: "2026.08", created: "2026-07-25" },
];

const squadRows: DataRow[] = [
  { dcpsquad: "Atlas", squad_lead: "Aisha", department: "Platform", capacity: 32 },
  { dcpsquad: "Beacon", squad_lead: "Mei", department: "Customer", capacity: 28 },
  { dcpsquad: "Cobalt", squad_lead: "Nadia", department: "Governance", capacity: 24 },
];

function column(name: string, dataType = "text", label = name.replaceAll("_", " ")): DatasetColumn {
  return { name, label: label.replace(/\b\w/g, (letter) => letter.toUpperCase()), data_type: dataType, nullable: true, numeric: /int|numeric|decimal|real|double|float/i.test(dataType), date_like: /date|time/i.test(dataType) };
}

const entries: Array<{ summary: DatasetSummary; columns: DatasetColumn[]; rows: DataRow[] }> = [
  {
    summary: { id: "mock-jira-issues", name: "Jira Issues", description: "Issue-level delivery data for the Zara workspace prototype.", schema_name: "mock", table_name: "jira_issues", relation_type: "approved mock dataset", column_count: 11, approximate_rows: jiraRows.length },
    columns: [column("key"), column("summary"), column("status"), column("dcpsquad", "text", "Squad"), column("assignee"), column("priority"), column("issue_type"), column("story_points", "integer"), column("sprint"), column("release"), column("created", "date")],
    rows: jiraRows,
  },
  {
    summary: { id: "mock-squad-information", name: "Squad Information", description: "Approved squad ownership and capacity reference data.", schema_name: "mock", table_name: "squad_information", relation_type: "approved mock dataset", column_count: 4, approximate_rows: squadRows.length },
    columns: [column("dcpsquad", "text", "Squad"), column("squad_lead"), column("department"), column("capacity", "integer")],
    rows: squadRows,
  },
];

const entry = (id: string) => {
  const found = entries.find((item) => item.summary.id === id);
  if (!found) throw new Error("The selected prototype dataset is unavailable.");
  return found;
};

function compare(value: unknown, rule: FilterRule): boolean {
  const actualText = String(value ?? "").toLowerCase();
  const expectedText = String(rule.value ?? "").toLowerCase();
  const actualNumber = Number(value);
  const expectedNumber = Number(rule.value);
  switch (rule.operator) {
    case "not_equals": return actualText !== expectedText;
    case "contains": return actualText.includes(expectedText);
    case "not_contains": return !actualText.includes(expectedText);
    case "starts_with": return actualText.startsWith(expectedText);
    case "ends_with": return actualText.endsWith(expectedText);
    case "greater_than": return actualNumber > expectedNumber;
    case "greater_than_or_equal": return actualNumber >= expectedNumber;
    case "less_than": return actualNumber < expectedNumber;
    case "less_than_or_equal": return actualNumber <= expectedNumber;
    case "between": return actualNumber >= expectedNumber && actualNumber <= Number(rule.value_to);
    case "is_empty": return value == null || value === "";
    case "is_not_empty": return value != null && value !== "";
    default: return actualText === expectedText;
  }
}

function filterRows(rows: DataRow[], node: WorkflowNode): DataRow[] {
  const rules = (node.config.rules as FilterRule[] | undefined) ?? [];
  if (!rules.length) return rows;
  return rows.filter((row) => node.config.match === "any" ? rules.some((rule) => compare(row[rule.column], rule)) : rules.every((rule) => compare(row[rule.column], rule)));
}

function groupRows(rows: DataRow[], node: WorkflowNode): DataRow[] {
  const groupBy = String(node.config.group_by ?? "");
  const calculation = String(node.config.calculation ?? "count");
  const valueName = String(node.config.value ?? "");
  const resultName = String(node.config.result_name || (calculation === "count" ? "issue_count" : `${calculation}_${valueName || "value"}`));
  const groups = new Map<string, DataRow[]>();
  for (const row of rows) { const key = String(row[groupBy] ?? "Unspecified"); groups.set(key, [...(groups.get(key) ?? []), row]); }
  return [...groups].map(([key, grouped]) => {
    const values = grouped.map((row) => row[valueName]).filter((value) => value != null);
    const numbers = values.map(Number).filter(Number.isFinite);
    let result: unknown = grouped.length;
    if (calculation === "count_distinct") result = new Set(values.map(String)).size;
    if (calculation === "sum") result = numbers.reduce((sum, current) => sum + current, 0);
    if (calculation === "average") result = numbers.length ? numbers.reduce((sum, current) => sum + current, 0) / numbers.length : 0;
    if (calculation === "minimum") result = numbers.length ? Math.min(...numbers) : null;
    if (calculation === "maximum") result = numbers.length ? Math.max(...numbers) : null;
    return { [groupBy]: key, [resultName]: result };
  });
}

function joinRows(rows: DataRow[], node: WorkflowNode): DataRow[] {
  const right = entry(String(node.config.dataset ?? "")).rows;
  const leftColumn = String(node.config.left_column ?? "");
  const rightColumn = String(node.config.right_column ?? "");
  const inner = node.config.join_type === "inner";
  const joined: DataRow[] = [];
  for (const row of rows) {
    const matches = right.filter((candidate) => String(candidate[rightColumn] ?? "") === String(row[leftColumn] ?? ""));
    if (!matches.length && !inner) joined.push({ ...row });
    for (const match of matches) {
      const additions = Object.fromEntries(Object.entries(match).map(([name, value]) => [name in row ? `joined_${name}` : name, value]));
      joined.push({ ...row, ...additions });
    }
  }
  return joined;
}

function executeNode(workflow: WorkflowDefinition, node: WorkflowNode, cache: Map<string, DataRow[]>): DataRow[] {
  const cached = cache.get(node.id); if (cached) return cached;
  const edge = workflow.edges.find((item) => item.target === node.id);
  const parent = edge ? workflow.nodes.find((item) => item.id === edge.source) : undefined;
  let rows = node.type === "dataset" ? entry(String(node.config.dataset ?? "")).rows.map((row) => ({ ...row })) : parent ? executeNode(workflow, parent, cache) : [];
  if (node.type === "filter") rows = filterRows(rows, node);
  if (node.type === "select") { const selected = (node.config.columns as string[] | undefined) ?? []; rows = rows.map((row) => Object.fromEntries(selected.map((name) => [name, row[name]]))); }
  if (node.type === "group") rows = groupRows(rows, node);
  if (node.type === "join") rows = joinRows(rows, node);
  cache.set(node.id, rows); return rows;
}

export class MockWorkspaceService implements WorkspaceService {
  async datasets() { return entries.map((item) => item.summary); }
  async schema(dataset: string): Promise<DatasetSchema> { const item = entry(dataset); return { dataset: item.summary, columns: item.columns }; }
  async values(dataset: string, name: string) { return { values: [...new Set(entry(dataset).rows.map((row) => row[name]).filter((value) => value != null))].slice(0, 50) }; }
  async run(workflow: WorkflowDefinition): Promise<PreviewResult> {
    const started = performance.now();
    const output = workflow.nodes.find((node) => node.type === "output") ?? workflow.nodes.at(-1);
    const rows = output ? executeNode(workflow, output, new Map()).slice(0, 100) : [];
    const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    return { columns, rows, row_count: rows.length, preview_limit: 100, truncated: false, execution_time_ms: Math.max(1, Math.round(performance.now() - started)) };
  }
  async save(workflow: WorkflowDefinition) {
    const saved = { ...workflow, id: workflow.id ?? crypto.randomUUID() };
    if (typeof window !== "undefined") window.localStorage.setItem("zara-workspace-latest", JSON.stringify(saved));
    return saved;
  }
}
