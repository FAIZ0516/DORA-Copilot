/**
 * Shared Chart.js theme: palette, tokens, formatting, and option fragments.
 *
 * Every Chart.js surface in the app (chat answers and the role dashboard, both
 * via `components/MetricChart.jsx`) reads its colours, fonts, grids, tooltips
 * and number formatting from here. Chart styling used to be inlined in the
 * renderer, so the same hex codes and tick callbacks were repeated per chart
 * type and drifted apart.
 *
 * Colour tokens live in CSS custom properties (see the `--chart-*` block in
 * `styles.css`) and are read at runtime, so a theme switch restyles canvases
 * without a rebuild. The Zara workspace renders with recharts inside its own
 * isolated TypeScript project, which cannot import this module; it reads the
 * same CSS variables instead, which keeps one source of truth for colour.
 */

const FONT_STACK =
  '"Inter Variable", Inter, "Segoe UI", system-ui, -apple-system, sans-serif';

/**
 * Series colours, ordered so neighbouring series stay distinguishable.
 *
 * Each entry is a CSS variable name with a literal fallback. The fallbacks are
 * what tests and any non-browser context see. Hues are spaced around the wheel
 * and alternate light/dark value, so adjacent series differ in brightness as
 * well as hue -- that is what keeps them apart for red-green colour blindness
 * and in greyscale print.
 */
export const SERIES_COLORS = [
  { token: "--chart-series-1", fallback: "#4f46e5" }, // indigo
  { token: "--chart-series-2", fallback: "#0ea5e9" }, // sky
  { token: "--chart-series-3", fallback: "#14b8a6" }, // teal
  { token: "--chart-series-4", fallback: "#f59e0b" }, // amber
  { token: "--chart-series-5", fallback: "#f43f5e" }, // rose
  { token: "--chart-series-6", fallback: "#8b5cf6" }, // violet
  { token: "--chart-series-7", fallback: "#22c55e" }, // green
  { token: "--chart-series-8", fallback: "#64748b" }, // slate
];

/**
 * Redundant encodings. A reader who cannot separate two hues can still tell
 * series apart by marker shape and, on line charts, by dash pattern.
 */
const POINT_STYLES = ["circle", "rect", "triangle", "rectRot", "star", "cross", "rectRounded", "dash"];
const DASH_PATTERNS = [[], [6, 4], [2, 3], [10, 4], [6, 3, 2, 3], [1, 3], [12, 5], [4, 2]];

const THEME_TOKENS = {
  ink: { token: "--chart-ink", fallback: "#1f2d3d" },
  inkMuted: { token: "--chart-ink-muted", fallback: "#64748b" },
  grid: { token: "--chart-grid", fallback: "#e8eef6" },
  axisZero: { token: "--chart-axis-zero", fallback: "#cbd5e1" },
  surface: { token: "--chart-surface", fallback: "#ffffff" },
  track: { token: "--chart-track", fallback: "rgba(100, 116, 139, 0.07)" },
  tooltipSurface: { token: "--chart-tooltip-surface", fallback: "#0f172a" },
  tooltipInk: { token: "--chart-tooltip-ink", fallback: "#f8fafc" },
  tooltipMuted: { token: "--chart-tooltip-muted", fallback: "#cbd5e1" },
};

function readCssValue(token, fallback) {
  if (typeof window === "undefined" || typeof getComputedStyle !== "function") return fallback;
  try {
    const value = getComputedStyle(document.documentElement).getPropertyValue(token);
    return value?.trim() || fallback;
  } catch {
    // A detached or sandboxed document should degrade to the literal palette
    // rather than throw while a chart is painting.
    return fallback;
  }
}

/** Resolve the active colour tokens. Call per render so theme changes apply. */
export function resolveChartTheme() {
  const theme = {};
  for (const [name, entry] of Object.entries(THEME_TOKENS)) {
    theme[name] = readCssValue(entry.token, entry.fallback);
  }
  return theme;
}

export function seriesColor(index) {
  const entry = SERIES_COLORS[index % SERIES_COLORS.length];
  return readCssValue(entry.token, entry.fallback);
}

export function seriesPointStyle(index) {
  return POINT_STYLES[index % POINT_STYLES.length];
}

export function seriesDash(index) {
  return DASH_PATTERNS[index % DASH_PATTERNS.length];
}

/** True when the reader asked the OS to minimise animation. */
export function prefersReducedMotion() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------------ */
/* Formatting                                                          */
/* ------------------------------------------------------------------ */

const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: "compact",
  maximumFractionDigits: 1,
});
const preciseFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const wholeFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

/**
 * Short unit suffixes for axis ticks. The axis already carries a title, so the
 * tick itself only needs enough to disambiguate scale.
 */
const UNIT_SUFFIX = {
  "%": "%",
  percent: "%",
  months: " mo",
  month: " mo",
  days: " d",
  day: " d",
  hours: " h",
  hour: " h",
  minutes: " min",
};

/** Units that describe an elapsed span rather than a count. */
const DURATION_UNITS = new Set(["months", "month", "days", "day", "hours", "hour", "minutes"]);

export function isDurationUnit(unit = "") {
  return DURATION_UNITS.has(String(unit).toLowerCase());
}

/**
 * Coerce to a number, treating absent values as absent.
 *
 * `Number(null)` and `Number("")` are both 0, so a missing metric would print
 * and plot as a real zero -- "0 issues" reads as a measured result when in
 * fact nothing was measured. Absent stays absent.
 */
function toNumber(value) {
  if (value === null || value === undefined || value === "") return Number.NaN;
  return Number(value);
}

/** Compact form for dense axes and summary chips: 12345 -> "12.3K". */
export function formatCompact(value) {
  const numeric = toNumber(value);
  if (!Number.isFinite(numeric)) return "—";
  // Below the compact threshold the plain form is shorter and more precise.
  return Math.abs(numeric) < 1000 ? preciseFormatter.format(numeric) : compactFormatter.format(numeric);
}

/**
 * Full-precision measurement with its unit, used in tooltips and the data
 * table where the exact number matters.
 */
export function formatMeasure(value, unit = "") {
  const numeric = toNumber(value);
  if (!Number.isFinite(numeric)) return "Unavailable";
  const key = String(unit).toLowerCase();
  const suffix = UNIT_SUFFIX[key];
  if (suffix) return `${preciseFormatter.format(numeric)}${suffix}`;
  if (!unit) return preciseFormatter.format(numeric);
  // Counts read better whole; "1,434 issues" not "1,434.00 issues".
  const formatted = Number.isInteger(numeric) ? wholeFormatter.format(numeric) : preciseFormatter.format(numeric);
  return `${formatted} ${unit}`;
}

/**
 * Axis tick label. Compact so dense axes stay legible; the tooltip still shows
 * the exact value from `formatMeasure`.
 */
export function formatAxisTick(value, unit = "") {
  const numeric = toNumber(value);
  if (!Number.isFinite(numeric)) return "";
  const suffix = UNIT_SUFFIX[String(unit).toLowerCase()] ?? "";
  return `${formatCompact(numeric)}${suffix}`;
}

const MAX_TICK_LABEL = 18;

/** Keep one long category from stealing the plotting area. */
export function truncateLabel(label, limit = MAX_TICK_LABEL) {
  const text = String(label ?? "");
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

/**
 * Render an ISO date or timestamp as a short readable date, leaving anything
 * that is not a date untouched (periods like "2026-Q1" or sprint names).
 */
export function formatCategory(value) {
  const text = String(value ?? "");
  if (!/^\d{4}-\d{2}-\d{2}([T ]|$)/.test(text)) return text;
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/* ------------------------------------------------------------------ */
/* Shared option fragments                                             */
/* ------------------------------------------------------------------ */

/**
 * A soft vertical gradient for bars and area fills. Chart.js hands us the
 * canvas context only once the layout is known, so this is used from a
 * scriptable option and returns a flat colour until `chartArea` exists.
 */
export function verticalGradient(context, color, { from = 0.9, to = 0.42 } = {}) {
  const { ctx, chartArea } = context.chart || {};
  if (!ctx || !chartArea) return withAlpha(color, from);
  const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
  gradient.addColorStop(0, withAlpha(color, from));
  gradient.addColorStop(1, withAlpha(color, to));
  return gradient;
}

export function areaGradient(context, color) {
  const { ctx, chartArea } = context.chart || {};
  if (!ctx || !chartArea) return withAlpha(color, 0.16);
  const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
  gradient.addColorStop(0, withAlpha(color, 0.28));
  gradient.addColorStop(1, withAlpha(color, 0.01));
  return gradient;
}

/** Apply an alpha to a #rrggbb colour, passing other formats through. */
export function withAlpha(color, alpha) {
  const hex = String(color).trim();
  if (!/^#[0-9a-f]{6}$/i.test(hex)) return hex;
  const red = parseInt(hex.slice(1, 3), 16);
  const green = parseInt(hex.slice(3, 5), 16);
  const blue = parseInt(hex.slice(5, 7), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

export function animationOptions() {
  // Reduced motion means no growth/sweep animation at all, not a faster one.
  return prefersReducedMotion()
    ? { animation: false, animations: {}, transitions: { active: { animation: { duration: 0 } } } }
    : { animation: { duration: 420, easing: "easeOutQuart" } };
}

export function legendOptions(theme, { display = true, position = "bottom" } = {}) {
  return {
    display,
    position,
    align: "start",
    labels: {
      color: theme.inkMuted,
      usePointStyle: true,
      pointStyle: "circle",
      boxWidth: 7,
      boxHeight: 7,
      padding: 14,
      font: { family: FONT_STACK, size: 11, weight: "600" },
    },
  };
}

/**
 * One tooltip style for every chart type: dark card, muted title, exact
 * values. `formatEntry` maps a Chart.js tooltip item to its label text.
 */
export function tooltipOptions(theme, formatEntry, { titleFor } = {}) {
  return {
    backgroundColor: theme.tooltipSurface,
    titleColor: theme.tooltipMuted,
    bodyColor: theme.tooltipInk,
    borderColor: withAlpha(theme.tooltipInk, 0.12),
    borderWidth: 1,
    cornerRadius: 10,
    padding: { top: 9, right: 12, bottom: 9, left: 12 },
    displayColors: true,
    usePointStyle: true,
    boxPadding: 5,
    titleFont: { family: FONT_STACK, size: 10, weight: "600" },
    bodyFont: { family: FONT_STACK, size: 12, weight: "500" },
    callbacks: {
      // Titles show the untruncated category, so a clipped axis tick is
      // always recoverable on hover.
      title: titleFor || ((items) => formatCategory(items[0]?.label ?? "")),
      label: formatEntry,
    },
  };
}

/** Category (non-numeric) axis: no grid, no border, clipped labels. */
export function categoryScale(theme, { title = "", stacked = false, horizontal = false, dense = false } = {}) {
  return {
    stacked,
    grid: { display: false, drawBorder: false },
    border: { display: false },
    title: title
      ? { display: true, text: title, color: theme.inkMuted, font: { family: FONT_STACK, size: 10, weight: "600" }, padding: { top: 8 } }
      : { display: false },
    ticks: {
      color: theme.inkMuted,
      font: { family: FONT_STACK, size: 11 },
      padding: 6,
      autoSkip: !horizontal,
      // A dense category axis drops labels rather than overlapping them.
      maxTicksLimit: dense ? 12 : undefined,
      maxRotation: horizontal ? 0 : 0,
      minRotation: 0,
      callback(value) {
        const raw = this.getLabelForValue ? this.getLabelForValue(value) : value;
        return truncateLabel(formatCategory(raw), horizontal ? 22 : MAX_TICK_LABEL);
      },
    },
  };
}

/** Value (numeric) axis: hairline horizontal grid, emphasised zero line. */
export function valueScale(theme, { unit = "", position = "left", stacked = false, horizontal = false, drawGrid = true } = {}) {
  return {
    beginAtZero: true,
    stacked,
    position,
    grid: {
      // Only the primary axis paints grid lines; a second unit axis would
      // double them up on the same plot.
      display: drawGrid,
      drawBorder: false,
      drawTicks: false,
      // Emphasise the zero baseline so negative values read as below it.
      color: (context) => (context.tick?.value === 0 ? theme.axisZero : theme.grid),
      lineWidth: (context) => (context.tick?.value === 0 ? 1.5 : 1),
    },
    border: { display: false, dash: horizontal ? undefined : undefined },
    title: unit
      ? { display: true, text: unit, color: theme.inkMuted, font: { family: FONT_STACK, size: 10, weight: "600" } }
      : { display: false },
    ticks: {
      color: theme.inkMuted,
      font: { family: FONT_STACK, size: 11 },
      padding: 8,
      maxTicksLimit: 6,
      callback: (value) => formatAxisTick(value, unit),
    },
  };
}

/**
 * Install app-wide Chart.js defaults once. Anything set here does not need
 * repeating per chart type.
 */
export function applyChartDefaults(ChartJS) {
  const theme = resolveChartTheme();
  ChartJS.defaults.font.family = FONT_STACK;
  ChartJS.defaults.font.size = 11;
  ChartJS.defaults.color = theme.inkMuted;
  ChartJS.defaults.borderColor = theme.grid;
  ChartJS.defaults.maintainAspectRatio = false;
  ChartJS.defaults.responsive = true;
  ChartJS.defaults.datasets.bar.maxBarThickness = 46;
  ChartJS.defaults.datasets.bar.borderRadius = 6;
  ChartJS.defaults.datasets.bar.borderSkipped = false;
  ChartJS.defaults.elements.point.hoverBorderWidth = 3;
  ChartJS.defaults.elements.line.borderCapStyle = "round";
  ChartJS.defaults.elements.line.borderJoinStyle = "round";
  ChartJS.defaults.plugins.tooltip.animation = prefersReducedMotion() ? false : { duration: 140 };
}

export const CHART_FONT_STACK = FONT_STACK;
