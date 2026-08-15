import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  SERIES_COLORS,
  areaGradient,
  formatAxisTick,
  formatCategory,
  formatCompact,
  formatMeasure,
  isDurationUnit,
  legendOptions,
  resolveChartTheme,
  seriesColor,
  seriesDash,
  seriesPointStyle,
  tooltipOptions,
  truncateLabel,
  categoryScale,
  valueScale,
  verticalGradient,
  withAlpha,
} from "../src/charts/chartTheme.js";

const chartSource = readFileSync(new URL("../src/components/MetricChart.jsx", import.meta.url), "utf8");
const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const rendererSource = readFileSync(
  new URL("../src/features/zara-workspace/features/visualize/charts/ChartRenderer.tsx", import.meta.url),
  "utf8",
);

const theme = resolveChartTheme();

test("number formatting stays exact in tooltips and compact on axes", () => {
  // Axis ticks are compact so a dense axis stays readable...
  assert.equal(formatAxisTick(12345, ""), "12.3K");
  assert.equal(formatAxisTick(2_400_000, ""), "2.4M");
  // ...while the tooltip keeps the number the reader would quote.
  assert.equal(formatMeasure(12345, "issues"), "12,345 issues");
  // Small values are clearer in full than compacted.
  assert.equal(formatCompact(842), "842");
  assert.equal(formatCompact(1200), "1.2K");
});

test("percentages, durations and counts each read correctly", () => {
  assert.equal(formatMeasure(12.5, "%"), "12.5%");
  assert.equal(formatAxisTick(12.5, "%"), "12.5%");
  assert.equal(formatMeasure(1.2, "months"), "1.2 mo");
  assert.equal(formatMeasure(45, "days"), "45 d");
  // A whole count should not gain decimal places.
  assert.equal(formatMeasure(1434, "issues"), "1,434 issues");
  assert.equal(formatMeasure(3.5, "issues"), "3.5 issues");
  assert.ok(isDurationUnit("months"));
  assert.ok(!isDurationUnit("issues"));
});

test("negative, zero and non-finite values render without breaking the axis", () => {
  assert.equal(formatMeasure(0, "issues"), "0 issues");
  assert.equal(formatMeasure(-12.5, "%"), "-12.5%");
  assert.equal(formatAxisTick(-2400, ""), "-2.4K");
  // Missing data must never print "NaN" onto a chart.
  assert.equal(formatMeasure(null, "issues"), "Unavailable");
  assert.equal(formatMeasure(Number.NaN, ""), "Unavailable");
  assert.equal(formatCompact(undefined), "—");
  assert.equal(formatAxisTick("not a number", ""), "");
});

test("unusually large values stay short enough for an axis tick", () => {
  for (const value of [1e6, 1e9, 1e12]) {
    assert.ok(formatAxisTick(value, "").length <= 7, `${value} -> ${formatAxisTick(value, "")}`);
  }
});

test("long category labels are clipped but dates are made readable", () => {
  assert.equal(truncateLabel("short"), "short");
  const clipped = truncateLabel("An extremely long squad or feature name that would overflow");
  assert.ok(clipped.length <= 18);
  assert.ok(clipped.endsWith("…"));
  // ISO dates become human dates; anything else is left alone.
  assert.notEqual(formatCategory("2026-03-04"), "2026-03-04");
  assert.equal(formatCategory("2026-Q1"), "2026-Q1");
  assert.equal(formatCategory("MBK"), "MBK");
  assert.equal(formatCategory(null), "");
});

test("series are distinguishable without relying on colour", () => {
  // Marker shape and dash pattern repeat the distinction colour makes, so the
  // charts stay readable in greyscale and for colour-blind readers.
  const shapes = new Set();
  const dashes = new Set();
  for (let index = 0; index < SERIES_COLORS.length; index += 1) {
    shapes.add(seriesPointStyle(index));
    dashes.add(JSON.stringify(seriesDash(index)));
  }
  assert.equal(shapes.size, SERIES_COLORS.length);
  assert.equal(dashes.size, SERIES_COLORS.length);
});

test("the palette wraps safely past its own length", () => {
  assert.equal(seriesColor(0), seriesColor(SERIES_COLORS.length));
  assert.equal(seriesPointStyle(1), seriesPointStyle(SERIES_COLORS.length + 1));
  assert.ok(SERIES_COLORS.every((entry) => /^#[0-9a-f]{6}$/i.test(entry.fallback)));
});

test("withAlpha converts hex colours and passes anything else through", () => {
  assert.equal(withAlpha("#4f46e5", 0.5), "rgba(79, 70, 229, 0.5)");
  assert.equal(withAlpha("rgba(1, 2, 3, 0.4)", 0.5), "rgba(1, 2, 3, 0.4)");
});

test("value axis emphasises zero so negative bars read as below the baseline", () => {
  const scale = valueScale(theme, { unit: "%" });
  assert.equal(scale.beginAtZero, true);
  assert.equal(scale.grid.color({ tick: { value: 0 } }), theme.axisZero);
  assert.equal(scale.grid.color({ tick: { value: 10 } }), theme.grid);
  assert.ok(scale.grid.lineWidth({ tick: { value: 0 } }) > scale.grid.lineWidth({ tick: { value: 10 } }));
  assert.equal(scale.ticks.callback(1500), "1.5K%");
});

test("a dense category axis limits ticks instead of overlapping labels", () => {
  assert.equal(categoryScale(theme, { dense: true }).ticks.maxTicksLimit, 12);
  assert.equal(categoryScale(theme, { dense: false }).ticks.maxTicksLimit, undefined);
  // Chart junk stays off: no category grid lines and no axis borders.
  assert.equal(categoryScale(theme, {}).grid.display, false);
  assert.equal(categoryScale(theme, {}).border.display, false);
});

test("tooltips share one configuration and show the untruncated category", () => {
  const options = tooltipOptions(theme, () => "x");
  assert.equal(options.backgroundColor, theme.tooltipSurface);
  assert.equal(options.bodyColor, theme.tooltipInk);
  assert.equal(options.usePointStyle, true);
  assert.equal(options.callbacks.title([{ label: "2026-03-04" }]), formatCategory("2026-03-04"));
});

test("legends use point markers and can be switched off for one series", () => {
  assert.equal(legendOptions(theme).labels.usePointStyle, true);
  assert.equal(legendOptions(theme, { display: false }).display, false);
});

test("both chart systems read the same shared colour tokens", () => {
  // One palette definition, two renderers -- Chart.js in the main app and
  // recharts in the isolated workspace project.
  for (let index = 1; index <= SERIES_COLORS.length; index += 1) {
    assert.match(stylesSource, new RegExp(`--chart-series-${index}:`));
  }
  assert.match(rendererSource, /--chart-series-\$\{index \+ 1\}/);
  assert.match(chartSource, /from "\.\.\/charts\/chartTheme"/);
  // Colours must not be hardcoded back into the renderer.
  assert.doesNotMatch(chartSource, /#[0-9a-f]{6}/i);
});

test("a dark theme is defined for every chart token", () => {
  const light = stylesSource.slice(stylesSource.indexOf("--chart-series-1"));
  const tokens = [...new Set([...light.matchAll(/(--chart-[a-z0-9-]+):/g)].map((match) => match[1]))];
  const darkBlock = stylesSource.slice(stylesSource.indexOf(':root[data-theme="dark"]'));
  for (const name of tokens) {
    assert.match(darkBlock, new RegExp(`${name}:`), `${name} has no dark value`);
  }
  assert.ok(tokens.length >= 16);
});

test("an empty result is an empty state, not a rejected chart", () => {
  assert.match(chartSource, /isEmptyResult/);
  assert.match(chartSource, /chart-empty-state/);
  // Genuinely malformed charts keep the safety message.
  assert.match(chartSource, /Chart data was rejected safely/);
});

test("animation is suppressed rather than shortened under reduced motion", () => {
  assert.match(chartSource, /animationOptions\(\)/);
  const themeSource = readFileSync(new URL("../src/charts/chartTheme.js", import.meta.url), "utf8");
  assert.match(themeSource, /prefers-reduced-motion: reduce/);
  assert.match(themeSource, /animation: false/);
});

test("line smoothing stays low so trends are not invented", () => {
  const tension = chartSource.match(/tension:\s*([\d.]+)/);
  assert.ok(tension, "line tension should be set explicitly");
  assert.ok(Number(tension[1]) <= 0.3, `tension ${tension[1]} distorts the data path`);
});

test("gradients degrade to a flat colour before the canvas is laid out", () => {
  // Chart.js calls scriptable options before `chartArea` exists on the first
  // pass; returning undefined there paints nothing at all.
  const flat = verticalGradient({ chart: {} }, "#4f46e5");
  assert.equal(flat, "rgba(79, 70, 229, 0.9)");
  assert.equal(areaGradient({ chart: {} }, "#4f46e5"), "rgba(79, 70, 229, 0.16)");
});

test("gradients build top-to-bottom stops once the canvas area is known", () => {
  const stops = [];
  const context = {
    chart: {
      chartArea: { top: 0, bottom: 100 },
      ctx: {
        createLinearGradient: (x0, y0, x1, y1) => {
          assert.deepEqual([x0, y0, x1, y1], [0, 0, 0, 100]);
          return { addColorStop: (offset, color) => stops.push([offset, color]) };
        },
      },
    },
  };
  verticalGradient(context, "#4f46e5");
  assert.deepEqual(stops.map(([offset]) => offset), [0, 1]);
  assert.ok(stops[0][1].endsWith("0.9)"));
  assert.ok(stops[1][1].endsWith("0.42)"));
});
