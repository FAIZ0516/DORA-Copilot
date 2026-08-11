import { Calculator, CheckCircle2, ChevronDown, Download, Filter, GitMerge, Group, RefreshCw, Table2, X } from "lucide-react";

import { outputColumnLineage, type ColumnLineage, type LineageOperation } from "../../features/workflow/services/columnLineage";
import type { DatasetSchema, DatasetSummary, PreviewResult, WorkflowDefinition } from "../../features/workflow/types";
import { downloadCsv, safeFilename } from "../../services/exportCsv";

const labels: Record<LineageOperation, string> = { filter: "Filtered", group: "Grouped", join: "Joined", calculate: "Calculated" };
const icons = { filter: Filter, group: Group, join: GitMerge, calculate: Calculator } as const;
const detail = (column: ColumnLineage) => column.transformations.map((item) => `${labels[item.type]}\n${item.description}`).join("\n\n");
const primary = (column?: ColumnLineage) => column?.transformations.at(-1)?.type;

export function PreviewDrawer({ result, workflow, datasets, schemas, open, onClose, onRun }: { result: PreviewResult | null; workflow: WorkflowDefinition; datasets: DatasetSummary[]; schemas: Record<string, DatasetSchema | undefined>; open: boolean; onClose: () => void; onRun: () => void }) {
  const lineage = outputColumnLineage(workflow, schemas, datasets); const selectedCount = workflow.nodes.find((node) => node.type === "select")?.config.columns as string[] | undefined; const used = result ? [...new Set(result.columns.flatMap((column) => lineage.get(column)?.transformations.map((item) => item.type) ?? []))] as LineageOperation[] : [];
  if (!open) return <button className="preview-peek" onClick={onRun}><Table2 size={15} /> Output preview <ChevronDown size={14} /></button>;
  return <section className="preview-drawer">
    <header><div><span className="preview-icon"><Table2 size={17} /></span><div><strong>Output preview</strong><small>{result ? <><CheckCircle2 size={12} /> Refreshed · {result.row_count} rows shown · {result.execution_time_ms} ms {selectedCount?.length ? <span className="preview-selected-count">· {selectedCount.length} columns selected</span> : null}</> : "Run the workflow to see processed data"}</small></div></div><div className="preview-actions">{Boolean(used.length) && <div className="preview-legend" aria-label="Column lineage legend">{used.map((operation) => { const Icon = icons[operation]; return <span key={operation} className={`preview-legend__${operation}`}><Icon size={11} /> {labels[operation]}</span>; })}</div>}<button onClick={onRun}><RefreshCw size={14} /> Refresh</button><button disabled={!result} onClick={() => result && downloadCsv(`${safeFilename(workflow.name, "workflow-output")}-preview`, result.columns, result.rows)}><Download size={14} /> Export</button><button className="icon-only" onClick={onClose}><X size={16} /></button></div></header>
    <div className="preview-table-wrap">{result ? <table><thead><tr><th>#</th>{result.columns.map((column) => { const columnLineage = lineage.get(column); const operation = primary(columnLineage); const Icon = operation ? icons[operation] : null; return <th key={column} className={operation ? `preview-column--${operation}` : undefined} title={columnLineage ? detail(columnLineage) : undefined} aria-label={columnLineage ? `${column.replaceAll("_", " ")}. ${detail(columnLineage)}` : column.replaceAll("_", " ")}><span>{column.replaceAll("_", " ")}</span>{Icon && <i aria-hidden="true"><Icon size={12} /></i>}</th>; })}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={index}><td>{index + 1}</td>{result.columns.map((column) => <td key={column} title={String(row[column] ?? "")}>{formatValue(row[column])}</td>)}</tr>)}</tbody></table> : <div className="preview-empty"><Table2 size={24} /><strong>No preview yet</strong><span>Run the connected workflow to inspect its output.</span></div>}</div>
  </section>;
}

function formatValue(value: unknown) {
  if (value == null) return <span className="null-value">—</span>;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}