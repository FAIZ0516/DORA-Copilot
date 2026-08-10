import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { PreviewResult } from "../../workflow/types";
import type { ChartConfig, ChartDatum, ChartResult } from "../types/visualization";

const colors = ["#2563eb", "#7c3aed", "#14b8a6", "#f59e0b", "#ef476f", "#60a5fa", "#8b5cf6"];

export function ChartRenderer({ chart, result, preview, onSelect }: { chart: ChartConfig; result?: ChartResult; preview: PreviewResult; onSelect: (label: string) => void }) {
  const data = result?.data ?? [];
  if (chart.type === "kpi") {
    const value = data[0]?.value ?? 0;
    return <div className="dashboard-kpi"><strong>{chart.calculation === "percentage" ? `${value.toFixed(1)}%` : value.toLocaleString()}</strong><span>{chart.calculation === "percentage" ? "of prepared records" : "records in current view"}</span></div>;
  }
  if (chart.type === "table") return <div className="chart-table"><div><strong>Field</strong><strong>Value</strong></div>{data.slice(0, 12).map((item) => <button key={item.label} onClick={() => onSelect(item.label)}><span>{item.label}</span><strong>{item.value.toLocaleString()}</strong></button>)}{!data.length && preview.rows.slice(0, 8).map((row, index) => <div key={index}><span>{String(row[preview.columns[0]] ?? "Not set")}</span><strong>{String(row[preview.columns[1]] ?? "")}</strong></div>)}</div>;
  if (!data.length) return <div className="chart-no-data">No grouped values were returned for this chart.</div>;
  if (chart.type === "donut") return <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} dataKey="value" nameKey="label" innerRadius="48%" outerRadius="72%" paddingAngle={2} onClick={(entry) => onSelect(String((entry as unknown as ChartDatum).label))}>{data.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}</Pie><Tooltip /><Legend iconType="circle" iconSize={7} wrapperStyle={{ fontSize: 9 }} /></PieChart></ResponsiveContainer>;
  if (chart.type === "line") return <ResponsiveContainer width="100%" height="100%"><LineChart data={[...data].reverse()} margin={{ top: 8, right: 12, left: -20, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e7edf5" /><XAxis dataKey="label" tick={{ fontSize: 9 }} /><YAxis tick={{ fontSize: 9 }} /><Tooltip /><Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 5, onClick: (_event, payload) => onSelect(String((payload as unknown as { payload?: ChartDatum }).payload?.label ?? "")) }} /></LineChart></ResponsiveContainer>;
  return <ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 8, right: 12, left: -20, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e7edf5" /><XAxis dataKey="label" tick={{ fontSize: 9 }} /><YAxis tick={{ fontSize: 9 }} /><Tooltip cursor={{ fill: "#f0f5fc" }} /><Bar dataKey="value" fill="#2563eb" radius={[5, 5, 0, 0]} onClick={(entry) => onSelect(String((entry as unknown as ChartDatum).label))} /></BarChart></ResponsiveContainer>;
}
