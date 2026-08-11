import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PreviewResult } from "../../workflow/types";
import type { ChartConfig, ChartDatum, ChartResult } from "../types/visualization";

const palette = ["#4f46e5", "#0ea5e9", "#14b8a6", "#f59e0b", "#f43f5e", "#8b5cf6", "#22c55e"];
const compactNumber = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const fullNumber = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const tooltipStyle = {
  border: "1px solid #dbe5f2",
  borderRadius: 12,
  boxShadow: "0 14px 32px rgba(30, 52, 86, .14)",
  color: "#233a57",
  fontSize: 10,
  padding: "8px 10px",
};

function InsightStrip({ data }: { data: ChartDatum[] }) {
  const total = data.reduce((sum, item) => sum + Number(item.value || 0), 0);
  const leader = data.reduce<ChartDatum | null>((current, item) => !current || item.value > current.value ? item : current, null);
  return (
    <div className="chart-insight-strip" aria-label={`${data.length} plotted categories`}>
      <span><small>Total</small><strong>{compactNumber.format(total)}</strong></span>
      {leader && <span><small>Leading</small><strong title={leader.label}>{leader.label}</strong></span>}
      <span><small>Categories</small><strong>{data.length}</strong></span>
    </div>
  );
}

export function ChartRenderer({ chart, result, preview, onSelect }: { chart: ChartConfig; result?: ChartResult; preview: PreviewResult; onSelect: (label: string) => void }) {
  const data = result?.data ?? [];
  const gradientKey = chart.id.replace(/[^a-zA-Z0-9]/g, "");

  if (chart.type === "kpi") {
    const value = data[0]?.value ?? 0;
    const formatted = chart.calculation === "percentage" ? `${value.toFixed(1)}%` : compactNumber.format(value);
    return (
      <div className="dashboard-kpi">
        <div className="dashboard-kpi__halo" aria-hidden="true"><i /><i /><i /></div>
        <small>{chart.calculation.replaceAll("_", " ")}</small>
        <strong title={fullNumber.format(value)}>{formatted}</strong>
        <span>{chart.calculation === "percentage" ? "of prepared records" : "records in current view"}</span>
      </div>
    );
  }

  if (chart.type === "table") return (
    <div className="chart-table">
      <div><strong>Category</strong><strong>Value</strong></div>
      {data.slice(0, 12).map((item, index) => <button key={item.label} onClick={() => onSelect(item.label)}><span><i>{index + 1}</i>{item.label}</span><strong>{fullNumber.format(item.value)}</strong></button>)}
      {!data.length && preview.rows.slice(0, 8).map((row, index) => <div key={index}><span>{String(row[preview.columns[0]] ?? "Not set")}</span><strong>{String(row[preview.columns[1]] ?? "")}</strong></div>)}
    </div>
  );

  if (!data.length) return <div className="chart-no-data"><span aria-hidden="true">◇</span><strong>No chart data yet</strong><small>No grouped values were returned for this view.</small></div>;

  if (chart.type === "donut") {
    const total = data.reduce((sum, item) => sum + Number(item.value || 0), 0);
    return (
      <div className="chart-visual chart-visual--donut">
        <InsightStrip data={data} />
        <div className="chart-plot chart-donut-plot">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="label" innerRadius="57%" outerRadius="78%" cornerRadius={7} paddingAngle={3} stroke="rgba(255,255,255,.9)" strokeWidth={2} onClick={(entry) => onSelect(String((entry as unknown as ChartDatum).label))}>
                {data.map((_, index) => <Cell key={index} fill={palette[index % palette.length]} />)}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} cursor={false} />
              <Legend iconType="circle" iconSize={7} wrapperStyle={{ fontSize: 9, paddingTop: 4 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="chart-donut-total"><small>Total</small><strong>{compactNumber.format(total)}</strong></div>
        </div>
      </div>
    );
  }

  if (chart.type === "line") return (
    <div className="chart-visual">
      <InsightStrip data={data} />
      <div className="chart-plot">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={[...data].reverse()} margin={{ top: 12, right: 16, left: -18, bottom: 0 }}>
            <defs><linearGradient id={`line-${gradientKey}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4f46e5" stopOpacity={0.34} /><stop offset="95%" stopColor="#0ea5e9" stopOpacity={0.02} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="4 5" vertical={false} stroke="#e8eef7" />
            <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#718198" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 9, fill: "#718198" }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: "#94a3b8", strokeDasharray: "4 4" }} />
            <Area type="monotone" dataKey="value" stroke="none" fill={`url(#line-${gradientKey})`} />
            <Line type="monotone" dataKey="value" stroke="#4f46e5" strokeWidth={3} dot={{ r: 3, fill: "#fff", strokeWidth: 2 }} activeDot={{ r: 6, fill: "#0ea5e9", stroke: "#fff", strokeWidth: 3, onClick: (_event, payload) => onSelect(String((payload as unknown as { payload?: ChartDatum }).payload?.label ?? "")) }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );

  return (
    <div className="chart-visual">
      <InsightStrip data={data} />
      <div className="chart-plot">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 12, right: 16, left: -18, bottom: 0 }}>
            <defs><linearGradient id={`bar-${gradientKey}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4f46e5" /><stop offset="100%" stopColor="#0ea5e9" /></linearGradient></defs>
            <CartesianGrid strokeDasharray="4 5" vertical={false} stroke="#e8eef7" />
            <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#718198" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 9, fill: "#718198" }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(79,70,229,.055)" }} />
            <Bar dataKey="value" fill={`url(#bar-${gradientKey})`} radius={[8, 8, 3, 3]} maxBarSize={48} background={{ fill: "#f4f7fb", radius: 8 }} onClick={(entry) => onSelect(String((entry as unknown as ChartDatum).label))} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
