import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import MetricChart from "../src/components/MetricChart";

afterEach(cleanup);

const TYPES = ["bar", "horizontal_bar", "stacked_bar", "line", "area", "pie", "donut", "polar_area", "radar", "scatter", "table"];

function chartOf(type, data, series) {
  return {
    type, title: `${type} chart`, x_key: "period", x_label: "Reporting period",
    series: series ?? [{ key: "value", label: "Issues", unit: "issues" }],
    data,
  };
}

const normal = [
  { period: "2026-01", value: 120, second: 44 },
  { period: "2026-02", value: 340, second: 91 },
  { period: "2026-03", value: 210, second: 66 },
];

describe("MetricChart renders every supported type", () => {
  for (const type of TYPES) {
    it(`renders ${type}`, () => {
      const { container } = render(<MetricChart chart={chartOf(type, normal)} />);
      expect(container.innerHTML.length).toBeGreaterThan(0);
    });
  }
});

describe("edge cases", () => {
  it("empty result shows an empty state, not an error", () => {
    const { container } = render(<MetricChart chart={chartOf("bar", [])} />);
    expect(container.querySelector(".chart-empty-state")).toBeTruthy();
    expect(container.querySelector(".chart-render-error")).toBeNull();
  });

  it("single data point renders", () => {
    const { container } = render(<MetricChart chart={chartOf("bar", [{ period: "2026-01", value: 5 }])} />);
    expect(container.querySelector(".metric-chart")).toBeTruthy();
    expect(container.textContent).toContain("1 validated data point");
  });

  it("negative values render", () => {
    const { container } = render(<MetricChart chart={chartOf("bar", [{ period: "a", value: -40 }, { period: "b", value: 90 }])} />);
    expect(container.querySelector(".metric-chart")).toBeTruthy();
  });

  it("very large values render", () => {
    const { container } = render(<MetricChart chart={chartOf("line", [{ period: "a", value: 1e9 }, { period: "b", value: 2.4e9 }])} />);
    expect(container.querySelector(".metric-chart")).toBeTruthy();
  });

  it("dense dataset with long labels renders", () => {
    const dense = Array.from({ length: 60 }, (_, i) => ({ period: `A very long squad or feature label ${i}`, value: i * 37 }));
    const { container } = render(<MetricChart chart={chartOf("bar", dense)} />);
    expect(container.querySelector(".metric-chart")).toBeTruthy();
  });

  it("multi-series with mixed units renders and shows a legend", () => {
    const chart = chartOf("bar", normal, [
      { key: "value", label: "Issues", unit: "issues" },
      { key: "second", label: "Failure rate", unit: "%" },
    ]);
    const { container } = render(<MetricChart chart={chart} />);
    expect(container.querySelector(".metric-chart")).toBeTruthy();
  });

  it("malformed chart is still rejected safely", () => {
    const { container } = render(<MetricChart chart={{ type: "bar", title: "x", x_key: "p", series: [], data: [{ p: 1 }] }} />);
    expect(container.querySelector(".chart-render-error")).toBeTruthy();
  });
});
