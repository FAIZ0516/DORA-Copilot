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

/**
 * Chart colours come from the shared `--chart-*` CSS variables in
 * `styles.css`, the same tokens the Chart.js theme reads, so the workspace and
 * the main dashboard stay visually identical. This project is compiled as an
 * isolated TypeScript program without `allowJs`, so it cannot import
 * `charts/chartTheme.js` directly -- CSS variables are the shared layer both
 * sides can reach.
 */
function token(name: string, fallback: string): string {
  if (typeof window === "undefined" || typeof getComputedStyle !== "function") return fallback;
  try {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  } catch {
    return fallback;
  }
}

const paletteFallback = ["#4f46e5", "#0ea5e9", "#14b8a6", "#f59e0b", "#f43f5e", "#8b5cf6", "#22c55e"];
const palette = paletteFallback.map((fallback, index) => token(`--chart-series-${index + 1}`, fallback));
const inkMuted = token("--chart-ink-muted", "#5b6b80");
const gridColor = token("--chart-grid", "#e8eef6");
const surface = token("--chart-surface", "#ffffff");

const compactNumber = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const fullNumber = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const tooltipStyle = {
  background: token("--chart-tooltip-surface", "#0f172a"),
  border: "none",
  borderRadius: 10,
  boxShadow: "0 12px 28px rgba(15, 23, 42, .28)",
  color: token("--chart-tooltip-ink", "#f8fafc"),
  fontSize: 11,
  padding: "9px 12px",
};
const tooltipLabelStyle = { color: token("--chart-tooltip-ink", "#f8fafc") };
const tooltipItemStyle = { color: token("--chart-tooltip-ink", "#f8fafc") };
const axisTick = { fontSize: 10, fill: inkMuted } as const;

/** Keep one long category from eating the plot area; tooltips show it whole. */
function shortLabel(value: unknown): string {
  const text = String(value ?? "");
  return text.length > 16 ? `${text.slice(0, 15)}…` : text;
}

/** Axis ticks stay compact; the tooltip carries the exact figure. */
function compactTick(value: unknown): string {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? compactNumber.format(numeric) : "";
}

/**
 * Tooltip values are shown in full. recharts types the incoming value as a
 * loose `ValueType`, so narrow it here rather than at every call site.
 */
function exactValue(value: unknown): string {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? fullNumber.format(numeric) : "—";
}

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
              <Pie data={data} dataKey="value" nameKey="label" innerRadius="60%" outerRadius="80%" cornerRadius={6} paddingAngle={2} stroke={surface} strokeWidth={2} onClick={(entry) => onSelect(String((entry as unknown as ChartDatum).label))}>
                {data.map((_, index) => <Cell key={index} fill={palette[index % palette.length]} />)}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle} cursor={false} formatter={exactValue} />
              <Legend iconType="circle" iconSize={7} wrapperStyle={{ fontSize: 10, paddingTop: 6, color: inkMuted }} />
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
            <defs><linearGradient id={`line-${gradientKey}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={palette[0]} stopOpacity={0.28} /><stop offset="95%" stopColor={palette[1]} stopOpacity={0.01} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={gridColor} />
            <XAxis dataKey="label" tick={axisTick} tickFormatter={shortLabel} axisLine={false} tickLine={false} minTickGap={12} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={44} tickFormatter={compactTick} />
            <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle} cursor={{ stroke: inkMuted, strokeDasharray: "4 4" }} formatter={exactValue} />
            <Area type="monotone" dataKey="value" stroke="none" fill={`url(#line-${gradientKey})`} />
            <Line type="monotone" dataKey="value" stroke={palette[0]} strokeWidth={2.5} dot={{ r: 3, fill: surface, stroke: palette[0], strokeWidth: 2 }} activeDot={{ r: 6, fill: palette[0], stroke: surface, strokeWidth: 3, onClick: (_event, payload) => onSelect(String((payload as unknown as { payload?: ChartDatum }).payload?.label ?? "")) }} />
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
            <defs><linearGradient id={`bar-${gradientKey}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={palette[0]} stopOpacity={0.95} /><stop offset="100%" stopColor={palette[0]} stopOpacity={0.55} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={gridColor} />
            <XAxis dataKey="label" tick={axisTick} tickFormatter={shortLabel} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={8} />
            <YAxis tick={axisTick} axisLine={false} tickLine={false} width={44} tickFormatter={compactTick} />
            <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle} cursor={{ fill: token("--chart-track", "rgba(100,116,139,.07)") }} formatter={exactValue} />
            <Bar dataKey="value" fill={`url(#bar-${gradientKey})`} radius={[6, 6, 2, 2]} maxBarSize={44} onClick={(entry) => onSelect(String((entry as unknown as ChartDatum).label))} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
