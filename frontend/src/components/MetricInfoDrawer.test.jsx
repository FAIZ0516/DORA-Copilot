import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MetricInfoDrawer from "./MetricInfoDrawer";

afterEach(cleanup);

const metric = {
  key: "completion_pct",
  title: "Sprint Completion",
  value: 60,
  suffix: "%",
  description: "Percentage of scoped tickets currently in Jira's Done category.",
  formula: "100 × completed tickets ÷ scoped tickets.",
  why_it_matters: "Shows the current workflow position.",
  data_quality_note: "Done can include rejected or cancelled outcomes.",
  required_fields: ["status_category", "key"],
  source_tables: ["public.tbl_gdt_dte_jira_issues"],
  suggested_questions: ["What is still outside Done?"],
};

describe("MetricInfoDrawer", () => {
  it("renders the four explanation levels and keeps existing interactions", () => {
    const onClose = vi.fn();
    const onAsk = vi.fn();
    render(
      <MetricInfoDrawer
        metric={metric}
        scope={{ project: "DCPM", squad: "TITAN" }}
        updatedAt="2026-08-13T10:00:00Z"
        onClose={onClose}
        onAsk={onAsk}
      />,
    );

    expect(screen.getByRole("dialog", { name: "Sprint Completion" })).toBeTruthy();
    expect(screen.getByText("60%")).toBeTruthy();
    for (const heading of ["What it shows", "How Zara calculates", "Why it matters", "Important note"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }

    fireEvent.click(screen.getByRole("button", { name: "What is still outside Done?" }));
    expect(onAsk).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders safely when optional external metric metadata is malformed", () => {
    const onClose = vi.fn();
    expect(() => render(
      <MetricInfoDrawer
        metric={{ key: "external", value: null, suggested_questions: {}, source_tables: "not-an-array" }}
        scope={{ project: "DCPM", selected_squad_row: { name: "TITAN" } }}
        updatedAt="not-a-date"
        onClose={onClose}
        onAsk={vi.fn()}
      />,
    )).not.toThrow();

    expect(screen.getByRole("dialog", { name: "Metric information" })).toBeTruthy();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Close metric information" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
