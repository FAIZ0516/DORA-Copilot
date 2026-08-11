import { describe, expect, it } from "vitest";

import cardSource from "../components/ChartCard.tsx?raw";
import rendererSource from "./ChartRenderer.tsx?raw";

describe("modern visualization presentation", () => {
  it("keeps data querying outside the renderer and adds richer visual hierarchy", () => {
    expect(rendererSource).not.toContain("fetch(");
    expect(rendererSource).toContain("linearGradient");
    expect(rendererSource).toContain("InsightStrip");
    expect(rendererSource).toContain("chart-donut-total");
  });

  it("shows chart provenance metadata and accessible actions", () => {
    expect(cardSource).toContain("execution_time_ms");
    expect(cardSource).toContain("chart-type-badge");
    expect(cardSource).toContain("aria-label={`View data for ${chart.title}`}");
  });
});
