import { BarChart3, Check, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { PreviewResult } from "../../workflow/types";
import type { Calculation, ChartConfig, ChartType } from "../types/visualization";

export function AddChartModal({ preview, editing, onClose, onCreate }: { preview: PreviewResult; editing?: ChartConfig | null; onClose: () => void; onCreate: (chart: ChartConfig) => void }) {
  const [title, setTitle] = useState("");
  const [groupBy, setGroupBy] = useState("");
  const [value, setValue] = useState("");
  const [calculation, setCalculation] = useState<Calculation>("count");
  const [type, setType] = useState<ChartType>("bar");
  useEffect(() => { if (editing) { setTitle(editing.title); setGroupBy(editing.group_by ?? ""); setValue(editing.value ?? ""); setCalculation(editing.calculation); setType(editing.type); } }, [editing]);
  const create = () => onCreate({ id: editing?.id ?? crypto.randomUUID(), title: title.trim() || (groupBy ? `Records by ${groupBy.replaceAll("_", " ")}` : "Prepared records"), type, group_by: type === "kpi" ? null : groupBy || null, value: value || null, calculation: type === "kpi" && calculation !== "percentage" ? "count" : calculation, filters: editing?.filters ?? [] });
  return <div className="modal-backdrop" onMouseDown={onClose}><section className="add-chart-modal" onMouseDown={(event) => event.stopPropagation()}>
    <header><div><span><BarChart3 size={18} /></span><div><small>ADD VISUALIZATION</small><h2>What do you want to visualize?</h2></div></div><button onClick={onClose}><X size={18} /></button></header>
    <div className="chart-setup"><p>Choose a field and value. Zara will translate this setup into a database aggregation.</p><label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Blocked Issues by Squad" /></label><label>Group by<select value={groupBy} onChange={(event) => setGroupBy(event.target.value)}><option value="">No grouping</option>{preview.columns.map((column) => <option key={column} value={column}>{column.replaceAll("_", " ")}</option>)}</select></label><label>Value<select value={value} onChange={(event) => setValue(event.target.value)}><option value="">Count rows</option>{preview.columns.map((column) => <option key={column} value={column}>{column.replaceAll("_", " ")}</option>)}</select></label><label>Calculation<select value={calculation} onChange={(event) => setCalculation(event.target.value as Calculation)}><option value="count">Count</option><option value="sum">Sum</option><option value="average">Average</option><option value="minimum">Minimum</option><option value="maximum">Maximum</option></select></label><label>Chart<select value={type} onChange={(event) => setType(event.target.value as ChartType)}><option value="bar">Bar Chart</option><option value="line">Line Chart</option><option value="donut">Donut / Pie Chart</option><option value="kpi">KPI Number</option><option value="table">Table</option></select></label></div>
    <footer><button onClick={onClose}>Cancel</button><button className="create-chart" onClick={create}><Check size={14} /> {editing ? "Update Chart" : "Create Chart"}</button></footer>
  </section></div>;
}
