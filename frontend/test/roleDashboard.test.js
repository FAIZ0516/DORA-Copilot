import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildDashboardContext, defaultDashboardView } from "../src/dashboardState.js";

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const dashboardSource = readFileSync(new URL("../src/components/RoleDashboard.jsx", import.meta.url), "utf8");
const drawerSource = readFileSync(new URL("../src/components/MetricInfoDrawer.jsx", import.meta.url), "utf8");
const chatSource = readFileSync(new URL("../src/components/Chat.jsx", import.meta.url), "utf8");

test("Scrum Master entry resolves a real squad without an intermediate selection screen", () => {
  assert.match(appSource, /role: "scrum_master"/);
  assert.match(dashboardSource, /loadDashboardSquads/);
  assert.match(dashboardSource, /context\.setSelectedSquad\(nextSquads\[0\]\.name\)/);
  assert.match(dashboardSource, /<DashboardFilters/);
  assert.doesNotMatch(dashboardSource, /Select your squad|pendingSquad/);
});

test("Head of Department opens the portfolio dashboard", () => {
  assert.equal(defaultDashboardView("head_of_department"), "portfolio");
  assert.match(appSource, /role: "head_of_department"/);
  assert.match(dashboardSource, /Department Performance Dashboard/);
});

test("squad drill-down preserves portfolio filters in structured context", () => {
  const state = {
    selectedRole: "head_of_department",
    activeView: "portfolio",
    selectedProject: "DCPM",
    selectedSquad: "",
    selectedRelease: "4.3.0",
    selectedSprint: "TITAN R19 SPRINT 4",
    dateRange: { from: "2026-01-01", to: "2026-08-05" },
    selectedMetric: "open_bugs",
    selectedSquadRow: null,
    currentMetricValue: 8,
  };
  assert.deepEqual(buildDashboardContext(state, {
    squad: "TITAN",
    active_view: "squad_detail",
  }), {
    role: "head_of_department",
    active_view: "squad_detail",
    project: "DCPM",
    squad: "TITAN",
    release: "4.3.0",
    sprint: "TITAN R19 SPRINT 4",
    date_from: "2026-01-01",
    date_to: "2026-08-05",
    selected_metric: "open_bugs",
    selected_squad_row: undefined,
    current_metric_value: 8,
  });
  assert.match(dashboardSource, /Back to all squads/);
  assert.match(dashboardSource, /context\.setActiveView\("portfolio"\)/);
});

test("information icon opens an accessible right-side metric drawer", () => {
  assert.match(dashboardSource, /setDrawerMetric\(metric\)/);
  assert.match(drawerSource, /role="dialog"/);
  assert.match(drawerSource, /aria-modal="false"/);
  assert.match(drawerSource, /event\.key === "Escape"/);
  assert.match(drawerSource, /Current scope/);
  assert.match(drawerSource, /Calculation/);
  assert.match(drawerSource, /Data source/);
});

test("dashboard prompts retain independent structured dashboard context", () => {
  assert.match(chatSource, /pendingDashboardContextRef/);
  assert.match(chatSource, /dashboard_context: requestContext/);
  assert.match(drawerSource, /selected_metric: metric\.key/);
  assert.match(drawerSource, /current_metric_value: metric\.value/);
});

test("unsupported metrics are hidden and API limitations use honest wording", () => {
  assert.doesNotMatch(dashboardSource, /Test Pass Rate/);
  assert.doesNotMatch(dashboardSource, /Worst Employee/);
  assert.match(dashboardSource, /Dependency links are not exposed/);
  assert.match(dashboardSource, /backend does not yet expose a feature-filter parameter/);
});

test("workspace exposes the requested analytics controls and actions", () => {
  for (const label of ["Squad", "Sprint", "Project", "Feature", "Issue View", "More Filters"]) {
    assert.match(dashboardSource, new RegExp(`>${label}<|${label} `));
  }
  assert.match(dashboardSource, /Generate Report/);
  assert.match(dashboardSource, /Ask Zara/);
  assert.match(dashboardSource, /Risks Requiring Attention/);
  assert.match(dashboardSource, /Feature &amp; Issue Table/);
});

test("loading, empty, and error dashboard states are distinct", () => {
  assert.match(dashboardSource, /DashboardSkeleton/);
  assert.match(dashboardSource, /No Jira issues found in the selected scope/);
  assert.match(dashboardSource, /Dashboard data could not be loaded/);
  assert.match(dashboardSource, /value === null \|\| value === undefined/);
});
