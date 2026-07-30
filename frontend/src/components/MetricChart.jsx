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

const palette = [
  "#0873be",
  "#56bee2",
  "#e94655",
  "#143b76",
  "#79cfec",
  "#f2a93b",
  "#6f58b5",
  "#2b9b74",
];
const translucentPalette = [
  "rgba(8, 115, 190, 0.72)",
  "rgba(86, 190, 226, 0.72)",
  "rgba(233, 70, 85, 0.72)",
  "rgba(20, 59, 118, 0.72)",
  "rgba(121, 207, 236, 0.72)",
  "rgba(242, 169, 59, 0.72)",
  "rgba(111, 88, 181, 0.72)",
  "rgba(43, 155, 116, 0.72)",
];

function normalizeChart(chart) {
  if (chart?.data?.length && chart?.series?.length) return chart;
  if (!chart?.labels?.length) return null;
  return {
    ...chart,
    x_key: "label",
    series: [{ key: "value", label: chart.title, unit: chart.unit || "" }],
    data: chart.labels.map((label, index) => ({
      label,
      value: Number(chart.values[index] ?? 0),
    })),
  };
}

function formatValue(value, unit = "") {
  const formatted = Number(value).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  });
  if (!unit) return formatted;
  return unit === "%" ? `${formatted}%` : `${formatted} ${unit}`;
}

function scaleId(unit = "", axis = "y") {
  return `${axis}-${unit.replace(/[^a-z0-9]/gi, "").toLowerCase() || "value"}`;
}

function chartData(chart) {
  const labels = chart.data.map((row) => String(row[chart.x_key] ?? ""));
  return {
    labels,
    datasets: chart.series.map((series, index) => ({
      label: series.label,
      data: chart.data.map((row) => Number(row[series.key] ?? 0)),
      backgroundColor: translucentPalette[index % translucentPalette.length],
      borderColor: palette[index % palette.length],
      borderWidth: 2,
      borderRadius: 4,
      pointBackgroundColor: "#ffffff",
      pointBorderColor: palette[index % palette.length],
      pointBorderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.28,
      fill: chart.type === "area",
      ...(chart.type === "horizontal_bar"
        ? { xAxisID: scaleId(series.unit, "x") }
        : { yAxisID: scaleId(series.unit) }),
    })),
  };
}

function cartesianOptions(chart) {
  const units = [...new Set(chart.series.map((series) => series.unit || ""))];
  const horizontal = chart.type === "horizontal_bar";
  const categoryAxis = horizontal ? "y" : "x";
  const valueAxis = horizontal ? "x" : "y";
  const scales = {
    [categoryAxis]: {
      stacked: chart.type === "stacked_bar",
      title: {
        display: true,
        text: chart.x_label || (chart.x_key === "period" ? "Reporting period" : ""),
        color: "#526a7b",
        font: { weight: "600" },
      },
      grid: { display: false },
      ticks: { color: "#526a7b" },
    },
  };
  units.forEach((unit, index) => {
    scales[scaleId(unit, valueAxis)] = {
      beginAtZero: true,
      stacked: chart.type === "stacked_bar",
      position: horizontal
        ? (index % 2 === 0 ? "bottom" : "top")
        : (index % 2 === 0 ? "left" : "right"),
      title: {
        display: true,
        text: unit || "Value",
        color: "#526a7b",
        font: { weight: "600" },
      },
      grid: { color: index === 0 ? "#e3edf2" : "transparent" },
      ticks: {
        color: "#526a7b",
        callback: (value) => formatValue(value, unit),
      },
    };
  });
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: horizontal ? "y" : "x",
    interaction: { intersect: false, mode: "nearest" },
    plugins: {
      legend: {
        display: chart.series.length > 1,
        position: "bottom",
        labels: { color: "#31566d", usePointStyle: true, boxWidth: 9 },
      },
      tooltip: {
        callbacks: {
          label: (context) => {
            const series = chart.series[context.datasetIndex];
            const value = horizontal ? context.parsed.x : context.parsed.y;
            return `${series.label}: ${formatValue(value, series.unit)}`;
          },
        },
      },
    },
    scales,
  };
}

function radialData(chart) {
  const series = chart.series[0];
  return {
    labels: chart.data.map((row) => String(row[chart.x_key] ?? "")),
    datasets: [
      {
        label: series.label,
        data: chart.data.map((row) => Number(row[series.key] ?? 0)),
        backgroundColor: translucentPalette,
        borderColor: palette,
        borderWidth: 2,
      },
    ],
  };
}

function radialOptions(chart) {
  const unit = chart.series[0]?.unit || "";
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "right",
        labels: { color: "#31566d", usePointStyle: true, boxWidth: 9 },
      },
      tooltip: {
        callbacks: {
          label: (context) =>
            `${context.label}: ${formatValue(context.raw, unit)}`,
        },
      },
    },
  };
}

function scatterData(chart) {
  return {
    datasets: chart.series.map((series, index) => ({
      label: series.label,
      data: chart.data.map((row) => ({
        x: Number(row[chart.x_key] ?? 0),
        y: Number(row[series.key] ?? 0),
        period: row[chart.point_label_key || "period"],
      })),
      backgroundColor: palette[index % palette.length],
      borderColor: palette[index % palette.length],
      pointRadius: 6,
      pointHoverRadius: 8,
    })),
  };
}

function scatterOptions(chart) {
  const series = chart.series[0];
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => String(items[0]?.raw?.period || ""),
          label: (context) =>
            `${chart.x_label || chart.x_key}: ${formatValue(context.parsed.x, "months")}; ${series.label}: ${formatValue(context.parsed.y, series.unit)}`,
        },
      },
    },
    scales: {
      x: {
        beginAtZero: true,
        title: { display: true, text: chart.x_label || chart.x_key },
        grid: { color: "#e3edf2" },
      },
      y: {
        beginAtZero: true,
        title: { display: true, text: `${series.label} (${series.unit})` },
        grid: { color: "#e3edf2" },
      },
    },
  };
}

function renderChart(chart) {
  if (chart.type === "pie") {
    return <Pie data={radialData(chart)} options={radialOptions(chart)} />;
  }
  if (chart.type === "donut") {
    return <Doughnut data={radialData(chart)} options={radialOptions(chart)} />;
  }
  if (chart.type === "polar_area") {
    return <PolarArea data={radialData(chart)} options={radialOptions(chart)} />;
  }
  if (chart.type === "radar") {
    return (
      <Radar
        data={chartData(chart)}
        options={{
          ...radialOptions(chart),
          scales: { r: { beginAtZero: true, grid: { color: "#dceaf0" } } },
        }}
      />
    );
  }
  if (chart.type === "scatter") {
    return <Scatter data={scatterData(chart)} options={scatterOptions(chart)} />;
  }
  if (chart.type === "line" || chart.type === "area") {
    return <Line data={chartData(chart)} options={cartesianOptions(chart)} />;
  }
  return <Bar data={chartData(chart)} options={cartesianOptions(chart)} />;
}

export default function MetricChart({ chart: rawChart }) {
  const chart = normalizeChart(rawChart);
  if (!chart || chart.type === "table") return null;
  return (
    <figure className="metric-chart" aria-label={chart.title}>
      <figcaption>
        <span>{chart.title}</span>
        <small>{chart.type.replaceAll("_", " ")}</small>
      </figcaption>
      <div className={`chart-canvas chart-canvas-${chart.type}`}>
        {renderChart(chart)}
      </div>
      <p className="chart-data-summary">
        {chart.data.length} validated data points. Hover or focus the chart for values.
      </p>
    </figure>
  );
}
