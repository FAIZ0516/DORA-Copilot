import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DashboardFilters, MetricAskMenu } from "./RoleDashboard";

afterEach(cleanup);

const filterContext = (setDateRange = vi.fn()) => ({
  selectedProject: "DCPM",
  selectedSquad: "KAIJU",
  selectedSprint: "Sprint 12",
  selectedRelease: "R5",
  dateRange: { from: "2026-08-01", to: "2026-08-14" },
  setSelectedSprint: vi.fn(),
  setSelectedRelease: vi.fn(),
  setDateRange,
});

function renderFilters(context = filterContext()) {
  render(
    <DashboardFilters
      context={context}
      options={{
        sprints: [{ value: "Sprint 12" }],
        releases: [{ value: "R5" }],
        date_range: { minimum: "2026-01-01", maximum: "2026-08-14" },
      }}
      projects={[{ key: "DCPM", label: "DCPM" }]}
      squads={[{ name: "KAIJU" }]}
      onProjectChange={vi.fn()}
      onSquadChange={vi.fn()}
      onRefresh={vi.fn()}
      loading={false}
      featureOptions={[]}
      selectedFeature=""
      onFeatureChange={vi.fn()}
      issueView="all"
      onIssueViewChange={vi.fn()}
      onReset={vi.fn()}
    />,
  );
}

describe("dashboard overlays", () => {
  it("opens More Filters and keeps both date controls interactable", () => {
    const setDateRange = vi.fn();
    renderFilters(filterContext(setDateRange));

    fireEvent.click(screen.getByText("Advanced filters"));
    expect(screen.getByText("Created from")).toBeTruthy();
    expect(screen.getByText("Created to")).toBeTruthy();

    fireEvent.change(screen.getByDisplayValue("2026-08-01"), { target: { value: "2026-08-02" } });
    expect(setDateRange).toHaveBeenCalledTimes(1);
    const updater = setDateRange.mock.calls[0][0];
    expect(updater({ from: "2026-08-01", to: "2026-08-14" })).toEqual({ from: "2026-08-02", to: "2026-08-14" });
  });

  it("reveals KPI questions on hover, focus and click without selecting one", () => {
    const onAsk = vi.fn();
    const { container } = render(
      <MetricAskMenu
        card={{ key: "active_work", title: "Open Work", value: 17 }}
        scope={{ project: "DCPM", squad: "KAIJU", sprint: "Sprint 12" }}
        onAsk={onAsk}
      />,
    );
    const wrapper = container.querySelector(".metric-ask-menu");
    const trigger = screen.getByRole("button", { name: /Ask Zara/i });

    fireEvent.mouseEnter(wrapper);
    expect(screen.getByRole("menu", { name: "Questions about Open Work" })).toBeTruthy();
    expect(onAsk).not.toHaveBeenCalled();

    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.focus(trigger);
    expect(screen.getByRole("menu", { name: "Questions about Open Work" })).toBeTruthy();
    expect(onAsk).not.toHaveBeenCalled();

    fireEvent.click(trigger);
    expect(screen.queryByRole("menu", { name: "Questions about Open Work" })).toBeNull();
    fireEvent.click(trigger);
    expect(screen.getByRole("menu", { name: "Questions about Open Work" })).toBeTruthy();
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("selects a grounded KPI question only after the user chooses an option", () => {
    const onAsk = vi.fn();
    render(
      <MetricAskMenu
        card={{ key: "impeded_work", title: "Active Blockers", value: 3 }}
        scope={{ project: "DCPM", squad: "KAIJU", sprint: "Sprint 12" }}
        onAsk={onAsk}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Ask Zara/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Which should be unblocked first?" }));

    expect(onAsk).toHaveBeenCalledTimes(1);
    const [question, context] = onAsk.mock.calls[0];
    expect(question).toMatch(/KAIJU/);
    expect(question).toMatch(/Sprint 12/);
    expect(context).toMatchObject({ selected_metric: "impeded_work", current_metric_value: 3 });
  });
});
