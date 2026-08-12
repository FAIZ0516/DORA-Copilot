import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  RadialLinearScale,
  Title,
  Tooltip,
} from "chart.js";
import {
  Bar,
  Doughnut,
  Line,
  Pie,
  PolarArea,
  Radar,
  Scatter,
} from "react-chartjs-2";
import { Component } from "react";
import {
  animationOptions,
  areaGradient,
  applyChartDefaults,
  categoryScale,
  CHART_FONT_STACK,
  formatAxisTick,
  formatCategory,
  formatCompact,
  formatMeasure,
  legendOptions,
  prefersReducedMotion,
  resolveChartTheme,
  seriesColor,
  seriesDash,
  seriesPointStyle,
  tooltipOptions,
  valueScale,
  verticalGradient,
  withAlpha,
} from "../charts/chartTheme";

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  RadialLinearScale,
  Title,
  Tooltip,
);

applyChartDefaults(ChartJS);

function normalizeChart(chart) {
  if (chart?.data?.length && chart?.series?.length) return chart;
  if (!chart?.labels?.length) return null;
  return {
    ...chart,
    x_key: "label",
    series: [{ key: "value", label: chart.title, unit: chart.unit || "" }],
    data: chart.labels.map((label, index) => ({
      label,
      value: Number(chart.values?.[index] ?? 0),
    })),
  };
}

const ALLOWED_CHART_TYPES = new Set(["bar", "horizontal_bar", "stacked_bar", "line", "area", "pie", "donut", "polar_area", "radar", "scatter", "table"]);

export function validateChartSchema(rawChart) {
  const chart = normalizeChart(rawChart);
  if (!chart || typeof chart !== "object") return { valid: false, error: "No chart data was provided." };
  if (!ALLOWED_CHART_TYPES.has(chart.type)) return { valid: false, error: "Unsupported chart type." };
  if (typeof chart.title !== "string" || !chart.title.trim()) return { valid: false, error: "Chart title is missing." };
  if (typeof chart.x_key !== "string" || !chart.x_key) return { valid: false, error: "Chart category key is missing." };
  if (!Array.isArray(chart.series) || chart.series.length === 0 || chart.series.length > 8) return { valid: false, error: "Chart series are invalid." };
  if (!Array.isArray(chart.data) || chart.data.length === 0 || chart.data.length > 200) return { valid: false, error: "Chart data points are invalid." };
  const validSeries = chart.series.every((series) => series && typeof series.key === "string" && typeof series.label === "string");
  if (!validSeries) return { valid: false, error: "Chart series definitions are invalid." };
  const validRows = chart.data.every((row) => row && typeof row === "object" && chart.series.every((series) => Number.isFinite(Number(row[series.key]))));
  if (!validRows) return { valid: false, error: "Chart values must be finite numbers." };
  return { valid: true, chart: { ...chart, data: chart.data.map((row) => ({ ...row })) } };
}

/**
 * A query that legitimately returned nothing is not a rejected chart. It used
 * to fall through the schema check and surface as "Chart data was rejected
 * safely", which reads like a fault. Detect it before validating so genuine
 * schema violations keep their own message.
 */
function isEmptyResult(rawChart) {
  if (!rawChart || typeof rawChart !== "object") return false;
  if (Array.isArray(rawChart.data) && rawChart.data.length === 0) return true;
  return Array.isArray(rawChart.labels) && rawChart.labels.length === 0;
}

function ChartTableFallback({ chart }) {
  return (
    <details className="chart-table-fallback">
      <summary>View data table</summary>
      <div><table><thead><tr><th>{chart.x_label || chart.x_key}</th>{chart.series.map((series) => <th key={series.key}>{series.label}</th>)}</tr></thead><tbody>
        {chart.data.map((row, index) => <tr key={`${row[chart.x_key]}-${index}`}><th>{formatCategory(row[chart.x_key] ?? "")}</th>{chart.series.map((series) => <td key={series.key}>{formatMeasure(row[series.key], series.unit)}</td>)}</tr>)}
      </tbody></table></div>
    </details>
  );
}

class ChartErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { failed: false }; }
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="chart-render-error" role="alert">The chart could not be rendered. Use the data table below.</div>;
    return this.props.children;
  }
}

function scaleId(unit = "", axis = "y") {
  return `${axis}-${unit.replace(/[^a-z0-9]/gi, "").toLowerCase() || "value"}`;
}

/** A plot with many categories needs thinner bars and fewer tick labels. */
function isDense(chart) {
  return chart.data.length > 14;
}

function chartData(chart) {
  const theme = resolveChartTheme();
  const labels = chart.data.map((row) => String(row[chart.x_key] ?? ""));
  const filled = chart.type === "area";
  const isBar = chart.type === "bar" || chart.type === "horizontal_bar" || chart.type === "stacked_bar";
  return {
    labels,
    datasets: chart.series.map((series, index) => {
      const color = seriesColor(index);
      return {
        label: series.label,
        data: chart.data.map((row) => Number(row[series.key] ?? 0)),
        // Bars carry a soft vertical gradient; lines stay flat so the stroke
        // reads as a single continuous value.
        backgroundColor: isBar
          ? (context) => verticalGradient(context, color)
          : filled
            ? (context) => areaGradient(context, color)
            : withAlpha(color, 0.16),
        borderColor: color,
        borderWidth: isBar ? 0 : 2.5,
        borderRadius: isBar ? 6 : undefined,
        borderSkipped: false,
        hoverBackgroundColor: isBar ? (context) => verticalGradient(context, color, { from: 1, to: 0.6 }) : undefined,
        maxBarThickness: isDense(chart) ? 26 : 46,
        // Redundant with colour, so series remain separable without it.
        pointStyle: seriesPointStyle(index),
        borderDash: chart.type === "line" || chart.type === "area" ? seriesDash(index) : [],
        pointBackgroundColor: theme.surface,
        pointBorderColor: color,
        pointBorderWidth: 2,
        // Dense series hide their markers until hover to avoid a bead chain.
        pointRadius: isDense(chart) ? 0 : 3.5,
        pointHoverRadius: 6,
        pointHoverBackgroundColor: color,
        pointHoverBorderColor: theme.surface,
        pointHitRadius: 14,
        // Gentle smoothing only; high tension invents curvature the data
        // does not support, which misrepresents delivery metrics.
        tension: 0.24,
        fill: filled,
        ...(chart.type === "horizontal_bar"
          ? { xAxisID: scaleId(series.unit, "x") }
          : { yAxisID: scaleId(series.unit) }),
      };
    }),
  };
}

function cartesianOptions(chart) {
  const theme = resolveChartTheme();
  const units = [...new Set(chart.series.map((series) => series.unit || ""))];
  const horizontal = chart.type === "horizontal_bar";
  const stacked = chart.type === "stacked_bar";
  const categoryAxis = horizontal ? "y" : "x";
  const valueAxis = horizontal ? "x" : "y";
  const scales = {
    [categoryAxis]: categoryScale(theme, {
      title: chart.x_label || (chart.x_key === "period" ? "Reporting period" : ""),
      stacked,
      horizontal,
      dense: isDense(chart),
    }),
  };
  units.forEach((unit, index) => {
    scales[scaleId(unit, valueAxis)] = valueScale(theme, {
      unit,
      stacked,
      horizontal,
      position: horizontal
        ? (index % 2 === 0 ? "bottom" : "top")
        : (index % 2 === 0 ? "left" : "right"),
      // Grid lines come from the first unit axis only.
      drawGrid: index === 0,
    });
  });
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: horizontal ? "y" : "x",
    layout: { padding: { top: 8, right: 8, bottom: 0, left: 0 } },
    interaction: { intersect: false, mode: "index" },
    ...animationOptions(),
    plugins: {
      legend: legendOptions(theme, { display: chart.series.length > 1 }),
      tooltip: tooltipOptions(theme, (context) => {
        const series = chart.series[context.datasetIndex];
        const value = horizontal ? context.parsed.x : context.parsed.y;
        return `${series.label}: ${formatMeasure(value, series.unit)}`;
      }),
    },
    scales,
  };
}

function radialData(chart) {
  const series = chart.series[0];
  const colors = chart.data.map((_, index) => seriesColor(index));
  const theme = resolveChartTheme();
  return {
    labels: chart.data.map((row) => String(row[chart.x_key] ?? "")),
    datasets: [
      {
        label: series.label,
        data: chart.data.map((row) => Number(row[series.key] ?? 0)),
        backgroundColor: colors.map((color) => withAlpha(color, 0.88)),
        hoverBackgroundColor: colors,
        // A surface-coloured gap between arcs separates adjacent slices
        // without adding a dark outline.
        borderColor: theme.surface,
        borderWidth: 2,
        hoverOffset: 6,
      },
    ],
  };
}

function radialOptions(chart, { cutout } = {}) {
  const theme = resolveChartTheme();
  const unit = chart.series[0]?.unit || "";
  const total = chart.data.reduce((sum, row) => sum + Number(row[chart.series[0].key] ?? 0), 0);
  return {
    responsive: true,
    maintainAspectRatio: false,
    cutout,
    layout: { padding: 6 },
    ...animationOptions(),
    plugins: {
      legend: legendOptions(theme, { position: "right" }),
      tooltip: tooltipOptions(
        theme,
        (context) => {
          const value = Number(context.raw);
          // A share is the point of a part-to-whole chart, so state it
          // rather than making the reader estimate it from the arc.
          const share = total > 0 ? ` (${((value / total) * 100).toFixed(1)}%)` : "";
          return `${formatMeasure(value, unit)}${share}`;
        },
        { titleFor: (items) => formatCategory(items[0]?.label ?? "") },
      ),
    },
  };
}

function scatterData(chart) {
  const theme = resolveChartTheme();
  return {
    datasets: chart.series.map((series, index) => {
      const color = seriesColor(index);
      return {
        label: series.label,
        data: chart.data.map((row) => ({
          x: Number(row[chart.x_key] ?? 0),
          y: Number(row[series.key] ?? 0),
          period: row[chart.point_label_key || "period"],
        })),
        backgroundColor: withAlpha(color, 0.72),
        borderColor: theme.surface,
        borderWidth: 1.5,
        pointStyle: seriesPointStyle(index),
        pointRadius: 7,
        pointHoverRadius: 9,
        pointHoverBackgroundColor: color,
        pointHitRadius: 14,
      };
    }),
  };
}

function scatterOptions(chart) {
  const theme = resolveChartTheme();
  const series = chart.series[0];
  return {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { top: 8, right: 12 } },
    interaction: { intersect: false, mode: "nearest" },
    ...animationOptions(),
    plugins: {
      legend: legendOptions(theme, { display: chart.series.length > 1 }),
      tooltip: tooltipOptions(
        theme,
        (context) =>
          `${chart.x_label || chart.x_key}: ${formatMeasure(context.parsed.x, "months")} · ${series.label}: ${formatMeasure(context.parsed.y, series.unit)}`,
        { titleFor: (items) => String(items[0]?.raw?.period || series.label) },
      ),
    },
    scales: {
      x: {
        ...valueScale(theme, { unit: chart.x_label || chart.x_key, position: "bottom" }),
        ticks: {
          color: theme.inkMuted,
          font: { family: CHART_FONT_STACK, size: 11 },
          padding: 8,
          maxTicksLimit: 6,
          callback: (value) => formatCompact(value),
        },
      },
      y: valueScale(theme, { unit: series.unit ? `${series.label} (${series.unit})` : series.label }),
    },
  };
}

function radarOptions(chart) {
  const theme = resolveChartTheme();
  const unit = chart.series[0]?.unit || "";
  return {
    responsive: true,
    maintainAspectRatio: false,
    ...animationOptions(),
    plugins: {
      legend: legendOptions(theme, { display: chart.series.length > 1 }),
      tooltip: tooltipOptions(theme, (context) => `${context.dataset.label}: ${formatMeasure(context.parsed.r, chart.series[context.datasetIndex]?.unit || unit)}`),
    },
    scales: {
      r: {
        beginAtZero: true,
        angleLines: { color: theme.grid },
        grid: { color: theme.grid, circular: true },
        pointLabels: {
          color: theme.inkMuted,
          font: { family: CHART_FONT_STACK, size: 11, weight: "600" },
          callback: (label) => formatCategory(label),
        },
        ticks: {
          color: theme.inkMuted,
          backdropColor: "transparent",
          font: { family: CHART_FONT_STACK, size: 10 },
          maxTicksLimit: 5,
          callback: (value) => formatAxisTick(value, unit),
        },
      },
    },
  };
}

function renderChart(chart) {
  if (chart.type === "pie") {
    return <Pie data={radialData(chart)} options={radialOptions(chart)} />;
  }
  if (chart.type === "donut") {
    return <Doughnut data={radialData(chart)} options={radialOptions(chart, { cutout: "62%" })} />;
  }
  if (chart.type === "polar_area") {
    return <PolarArea data={radialData(chart)} options={radialOptions(chart)} />;
  }
  if (chart.type === "radar") {
    return <Radar data={chartData(chart)} options={radarOptions(chart)} />;
  }
  if (chart.type === "scatter") {
    return <Scatter data={scatterData(chart)} options={scatterOptions(chart)} />;
  }
  if (chart.type === "line" || chart.type === "area") {
    return <Line data={chartData(chart)} options={cartesianOptions(chart)} />;
  }
  return <Bar data={chartData(chart)} options={cartesianOptions(chart)} />;
}

const TYPE_LABELS = {
  bar: "Bar chart",
  horizontal_bar: "Horizontal bar",
  stacked_bar: "Stacked bar",
  line: "Line chart",
  area: "Area chart",
  pie: "Pie chart",
  donut: "Doughnut chart",
  polar_area: "Polar area",
  radar: "Radar chart",
  scatter: "Scatter plot",
  table: "Data table",
};

export default function MetricChart({ chart: rawChart }) {
  if (!rawChart) return null;
  if (isEmptyResult(rawChart)) {
    return (
      <div className="chart-empty-state" role="status">
        <strong>No values to plot</strong>
        <span>This scope returned no data points, so there is nothing to chart yet.</span>
      </div>
    );
  }
  const validation = validateChartSchema(rawChart);
  if (!validation.valid) return <div className="chart-render-error" role="alert">Chart data was rejected safely: {validation.error}</div>;
  const chart = validation.chart;
  if (chart.type === "table") return <ChartTableFallback chart={chart} />;
  const points = chart.data.length;
  return (
    <figure className="metric-chart" aria-label={chart.title}>
      <figcaption>
        <span>{chart.title}</span>
        <small>{TYPE_LABELS[chart.type] || chart.type.replaceAll("_", " ")}</small>
      </figcaption>
      <div className={`chart-canvas chart-canvas-${chart.type}`}>
        <ChartErrorBoundary>{renderChart(chart)}</ChartErrorBoundary>
      </div>
      <p className="chart-data-summary">
        {points} validated data point{points === 1 ? "" : "s"}
        {prefersReducedMotion() ? "" : " · hover or focus for exact values"}
      </p>
      <ChartTableFallback chart={chart} />
    </figure>
  );
}
