import { Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { workspaceApi } from "../../services/workspaceApi";
import { operatorsFor } from "../workflow/services/schemaPropagation";
import type { DatasetColumn, FilterRule } from "../workflow/types";

interface Props { rule: FilterRule; index: number; sourceDatasetId: string; columns: DatasetColumn[]; sourceColumns: DatasetColumn[]; canRemove: boolean; onChange: (rule: FilterRule) => void; onRemove: () => void; }

export function FilterRuleEditor({ rule, index, sourceDatasetId, columns, sourceColumns, canRemove, onChange, onRemove }: Props) {
  const [values, setValues] = useState<unknown[]>([]);
  const column = useMemo(() => columns.find((item) => item.name === rule.column), [columns, rule.column]);
  const operators = operatorsFor(column);
  const canUseSourceValues = Boolean(column && sourceColumns.some((item) => item.name === column.name));
  const isBoolean = /bool/i.test(column?.data_type ?? "");
  const isTyped = Boolean(column?.numeric || column?.date_like || /date|time|int|numeric|decimal|real|double|float/i.test(column?.data_type ?? ""));
  useEffect(() => { if (!sourceDatasetId || !rule.column || !canUseSourceValues || isTyped || isBoolean) { setValues([]); return; } workspaceApi.values(sourceDatasetId, rule.column).then((result) => setValues(result.values)).catch(() => setValues([])); }, [sourceDatasetId, rule.column, canUseSourceValues, isTyped, isBoolean]);
  const changeColumn = (name: string) => { const next = columns.find((item) => item.name === name); onChange({ ...rule, column: name, operator: operatorsFor(next)[0]?.[0] ?? "equals", value: "", value_to: "" }); };
  const noValue = ["is_empty", "is_not_empty"].includes(rule.operator);
  const between = rule.operator === "between";
  return <article className="filter-rule">
    <header><strong>Condition {index + 1}</strong>{canRemove && <button onClick={onRemove} aria-label={`Remove condition ${index + 1}`}><Trash2 size={13} /></button>}</header>
    <label>Column</label><select value={rule.column} onChange={(event) => changeColumn(event.target.value)}><option value="">Choose a field from the previous step</option>{columns.map((item) => <option key={item.name} value={item.name}>{item.label}</option>)}</select>
    {column && <><label>Condition</label><select value={rule.operator || operators[0]?.[0] || "equals"} onChange={(event) => onChange({ ...rule, operator: event.target.value, value: "", value_to: "" })}>{operators.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></>}
    {!noValue && column && <><label>Value</label>{isBoolean ? <select value={String(rule.value ?? "")} onChange={(event) => onChange({ ...rule, value: event.target.value })}><option value="">Choose a value</option><option value="true">True</option><option value="false">False</option></select> : values.length ? <select value={String(rule.value ?? "")} onChange={(event) => onChange({ ...rule, value: event.target.value })}><option value="">Choose a value</option>{values.map((value) => <option key={String(value)} value={String(value)}>{String(value)}</option>)}</select> : <input type={column.date_like ? "date" : column.numeric ? "number" : "text"} value={String(rule.value ?? "")} onChange={(event) => onChange({ ...rule, value: event.target.value })} placeholder={between ? "Start value" : "Enter a value"} />}{between && <input type={column.date_like ? "date" : column.numeric ? "number" : "text"} value={String(rule.value_to ?? "")} onChange={(event) => onChange({ ...rule, value_to: event.target.value })} placeholder="End value" />}</>}
  </article>;
}