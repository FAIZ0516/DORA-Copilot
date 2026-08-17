import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildDashboardContext, defaultDashboardView } from "../src/dashboardState.js";
import { buildPrimaryKpis, buildRiskItems, isSprintAvailable, rankRiskItems } from "../src/dashboardPresentation.js";

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const dashboardSource = readFileSync(new URL("../src/components/RoleDashboard.jsx", import.meta.url), "utf8");
const drawerSource = readFileSync(new URL("../src/components/MetricInfoDrawer.jsx", import.meta.url), "utf8");
const chatSource = readFileSync(new URL("../src/components/Chat.jsx", import.meta.url), "utf8");
const visualsSource = readFileSync(new URL("../src/components/DashboardVisuals.jsx", import.meta.url), "utf8");
const reportDrawerSource = readFileSync(new URL("../src/components/ReportGenerationDrawer.jsx", import.meta.url), "utf8");
const workspaceCss = readFileSync(new URL("../src/workspace.css", import.meta.url), "utf8");
const legacyCss = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
// The dashboard is intentionally role-neutral: every user enters the same
// All Squads view and can drill into a squad from there.
const roleConfigSource = readFileSync(new URL("../src/config/roleDashboardConfig.js", import.meta.url), "utf8");

test("the unified entry opens All Squads without a role or squad selection screen", () => {
  assert.match(roleConfigSource, /UNIFIED_DASHBOARD_CONFIG/);
  assert.match(roleConfigSource, /dashboardTitle: "All DCP Squads Overview"/);
  assert.doesNotMatch(roleConfigSource, /scrum_master|head_of_department/);
  assert.doesNotMatch(appSource, /role-selection/);
  assert.doesNotMatch(appSource, /selectedRole|Switch to Head/);
  assert.match(dashboardSource, /loadDashboardSquads/);
  assert.doesNotMatch(dashboardSource, /setSelectedSquad\(nextSquads\[0\]\.name\)/);
  assert.match(dashboardSource, /<DashboardFilters/);
  assert.equal(defaultDashboardView(), "portfolio");
  assert.match(chatSource, /openConversation\(savedId, \{ restoreDashboardScope: false \}\)/);
});

test("All Squads drills into a selected squad and can return to the portfolio", () => {
  assert.equal(defaultDashboardView("head_of_department"), "portfolio");
  assert.match(dashboardSource, /function viewSquad/);
  assert.match(dashboardSource, /const squad = row\.squad \|\| row\.name/);
  assert.match(dashboardSource, /context\.setSelectedSquad\(squad\)/);
  assert.match(dashboardSource, /All DCP Squads Overview/);
  assert.match(dashboardSource, /DCP-\$\{context\.selectedSquad\} Overview/);
  assert.match(dashboardSource, /> All Squads<\/button>/);
});

test("squad changes keep only valid sprint selections and ignore stale option requests", () => {
  const jaegerOptions = { sprints: [{ value: "JAEGER SPRINT 1" }, { value: "JAEGER SPRINT 2" }] };
  assert.equal(isSprintAvailable("", jaegerOptions), true);
  assert.equal(isSprintAvailable("JAEGER SPRINT 2", jaegerOptions), true);
  assert.equal(isSprintAvailable("MIDAS SPRINT 4", jaegerOptions), false);
  assert.match(dashboardSource, /loadDashboardFilters\(\{ project: context\.selectedProject, squad \}\)/);
  assert.match(dashboardSource, /if \(!isSprintAvailable\(context\.selectedSprint, squadOptions\)\) context\.setSelectedSprint\(""\)/);
  assert.match(dashboardSource, /requestId !== squadChangeRequest\.current/);
});

test("dashboard prioritises compact risks, squad progress, and ticket previews", () => {
  const ranked = rankRiskItems({
    kpis: { status: "Needs Attention" },
    attention_items: [
      { metric: "completion_pct", value: 20 },
      { metric: "impeded_work", value: 2 },
      { metric: "high_priority_open_bugs", value: 6 },
      { metric: "oldest_unresolved_days", value: 80 },
      { metric: "unassigned_open_work", value: 4 },
    ],
  }, 4);
  assert.equal(ranked.length, 4);
  assert.deepEqual(ranked.slice(0, 2).map((risk) => risk.metric), ["high_priority_open_bugs", "impeded_work"]);
  assert.match(dashboardSource, /compact\s+limit=\{4\}/);
  assert.match(dashboardSource, /rows\.slice\(0, 8\)/);
  assert.match(dashboardSource, /items\.slice\(0, 5\)/);
  assert.match(dashboardSource, /View all tickets/);
  assert.match(dashboardSource, /<WorkStatusCard payload=\{payload\}/);
});

test("squad drill-down preserves portfolio filters in structured context", () => {
  const state = {
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
  assert.match(dashboardSource, /<ArrowLeft aria-hidden="true" \/> All Squads/);
  assert.match(dashboardSource, /context\.setActiveView\("portfolio"\)/);
});

test("information icon opens an accessible right-side metric drawer", () => {
  assert.match(dashboardSource, /setDrawerMetric\(metric\)/);
  assert.match(dashboardSource, /function PortfolioKpiRow/);
  assert.match(dashboardSource, /<PortfolioKpiRow payload=\{payload\} onInfo=\{openMetric\}/);
  assert.match(drawerSource, /role="dialog"/);
  assert.match(drawerSource, /aria-modal="false"/);
  assert.match(drawerSource, /event\.key === "Escape"/);
  assert.match(drawerSource, /What it shows/);
  assert.match(drawerSource, /How Zara calculates/);
  assert.match(drawerSource, /Why it matters/);
  assert.match(drawerSource, /Important note/);
  assert.match(drawerSource, /Current scope/);
  assert.match(drawerSource, /Data source/);
});

test("squad KPI cards remove the duplicated ratio and use backend active work", () => {
  const cards = buildPrimaryKpis({
    kpis: {
      total_work: 20,
      completed_work: 12,
      completion_pct: 60,
      active_work: 7,
      impeded_work: 2,
      status: "Needs Attention",
      reasons: [{ metric: "impeded_work" }],
    },
    metric_registry: {
      completion_pct: { formula: "completion formula" },
      active_work: { formula: "active work formula" },
    },
  });

  assert.deepEqual(cards.map(({ key, title }) => ({ key, title })), [
    { key: "completion_pct", title: "Sprint Completion" },
    { key: "active_work", title: "Open Work" },
    { key: "impeded_work", title: "Active Blockers" },
    { key: "delivery_risk", title: "Delivery Risk" },
  ]);
  assert.equal(cards[0].comparison, "12 of 20 scoped tickets completed");
  assert.equal(cards[1].value, 7);
  assert.doesNotMatch(dashboardSource, /Completed vs Scoped/);
  assert.match(cards[2].definition.data_quality_note, /exactly Impeded/);
  assert.match(cards[2].definition.data_quality_note, /not inferred as blockers/);
});

test("scope changes clear old KPI payload and ignore late responses", () => {
  assert.match(dashboardSource, /setPayload\(null\)/);
  assert.match(dashboardSource, /let active = true/);
  assert.match(dashboardSource, /if \(active\) \{ setPayload\(result\); setStatus\("ready"\); \}/);
  assert.match(dashboardSource, /active = false; controller\.abort\(\)/);
});

test("dashboard prompts retain independent structured dashboard context", () => {
  assert.match(chatSource, /pendingDashboardContextRef/);
  assert.match(chatSource, /dashboard_context: requestContext/);
  assert.match(drawerSource, /selected_metric: metric\.key/);
  assert.match(drawerSource, /current_metric_value: metric\.value/);
});

test("KPI suggestions fill the composer without auto-sending and retain scope", () => {
  assert.match(chatSource, /onSuggest=\{fillQuestion\}/);
  assert.match(dashboardSource, /<PrimaryKpiRow[^>]*onAsk=\{suggest\}/);
  assert.match(chatSource, /pendingDashboardContextRef\.current = dashboardOverride/);
  assert.match(chatSource, /dashboardOverride \|\| pendingDashboardContextRef\.current \|\| dashboard\.dashboardContext\(\)/);
  assert.doesNotMatch(dashboardSource, /<PrimaryKpiRow[^>]*onAsk=\{ask\}/);
});

test("unsupported metrics are hidden and API limitations use honest wording", () => {
  assert.doesNotMatch(dashboardSource, /Test Pass Rate/);
  assert.doesNotMatch(dashboardSource, /Worst Employee/);
  assert.match(dashboardSource, /backend does not yet expose a feature-filter parameter/);
});

test("feature and ticket table removes Age and row View actions", () => {
  const issueTable = dashboardSource.slice(
    dashboardSource.indexOf("function IssueTable"),
    dashboardSource.indexOf("export default function RoleDashboard"),
  );
  assert.doesNotMatch(issueTable, /<th>Age<\/th>|age_days|>View<|selectedIssue|table-view-issue/);
  assert.match(issueTable, /<th>Ticket<\/th>/);
  assert.match(issueTable, /issue_filters/);
  assert.match(issueTable, /"Ticket type"/);
  assert.match(issueTable, /"Status"/);
  assert.match(issueTable, /"Priority"/);
  assert.match(issueTable, />Assignee</);
  assert.match(issueTable, />Sort</);
});

test("workspace exposes the compact primary dashboard controls and actions", () => {
  const controls = dashboardSource.slice(
    dashboardSource.indexOf("export function DashboardFilters"),
    dashboardSource.indexOf("function RiskAttentionPanel"),
  );
  for (const label of ["Squad", "Sprint", "Feature", "Advanced filters"]) {
    assert.match(controls, new RegExp(`>${label}<|${label} `));
  }
  assert.doesNotMatch(controls, />Project</);
  assert.doesNotMatch(controls, />Ticket View</);
  assert.match(dashboardSource, /Generate Report/);
  assert.match(dashboardSource, /Ask Zara/);
  assert.match(dashboardSource, /Risks Requiring Attention/);
  assert.match(dashboardSource, /Feature &amp; Ticket Table/);
});

test("loading, empty, and error dashboard states are distinct", () => {
  assert.match(dashboardSource, /DashboardSkeleton/);
  assert.match(dashboardSource, /No Jira tickets found in the selected scope/);
  assert.match(dashboardSource, /Dashboard data could not be loaded/);
  assert.match(dashboardSource, /value === null \|\| value === undefined/);
});

// Collect whole `<button ...>` opening tags. A plain regex cannot do this:
// `disabled={(payload?.page || 1) >= total}` contains a `>` that would end the
// match early, so track JSX brace depth and stop at the first `>` outside it.
function buttonTags(source) {
  const tags = [];
  for (let index = source.indexOf("<button"); index !== -1; index = source.indexOf("<button", index + 1)) {
    let depth = 0;
    for (let cursor = index; cursor < source.length; cursor += 1) {
      const character = source[cursor];
      if (character === "{") depth += 1;
      else if (character === "}") depth -= 1;
      else if (character === ">" && depth === 0) {
        tags.push(source.slice(index, cursor + 1));
        break;
      }
    }
  }
  return tags;
}

test("every dashboard button has a handler and none is wired to a no-op", () => {
  // Regression: the portfolio risk panel was mounted with onViewIssue={() => {}},
  // so its "View Issue" button was rendered, looked clickable, and did nothing.
  for (const source of [dashboardSource, visualsSource, reportDrawerSource, drawerSource]) {
    for (const button of buttonTags(source)) {
      assert.ok(
        /onClick=|type="submit"/.test(button),
        `button without a handler: ${button.slice(0, 90)}`,
      );
    }
    assert.doesNotMatch(source, /on[A-Z]\w*=\{\(\) => \{\}\}/, "handler wired to an empty function");
  }
});

test("portfolio risks name their squad and drill into that squad", () => {
  // Portfolio attention_items are squad rows; flattening their reasons used to
  // discard the squad, leaving a Head of Department unable to tell which squad
  // a risk belonged to and leaving the drill-in button with no target.
  assert.match(dashboardSource, /reason, squad: item\.squad/);
  assert.match(dashboardSource, /viewLabel="View Squad"/);
  assert.match(dashboardSource, /squad_comparison \|\| \[\]\)\.find/);

  const risks = buildRiskItems({
    kpis: { status: "Needs Attention" },
    attention_items: [
      { metric: "high_priority_open_bugs", value: 12, reason: "High-priority open bugs meet the escalation threshold", squad: "MBK", status: "Needs Attention" },
    ],
  });
  assert.equal(risks.length, 1);
  assert.equal(risks[0].squad, "MBK");
  assert.match(risks[0].title, /^MBK — /);
  assert.match(risks[0].evidence, /^MBK: /);
});

test("squad-level risks stay unprefixed when there is no squad on the reason", () => {
  const risks = buildRiskItems({
    kpis: { status: "Needs Attention" },
    attention_items: [{ metric: "impeded_work", value: 3, reason: "current impeded work is present" }],
  });
  assert.equal(risks[0].squad, "");
  assert.equal(risks[0].title, "Impeded work requires intervention");
  assert.doesNotMatch(risks[0].evidence, /—|: current impeded/);
});

test("dashboard actions send while KPI suggestion choices remain editable", () => {
  assert.match(chatSource, /function askZara/);
  assert.match(chatSource, /sendMessage\(question, dashboardOverride\)/);
  assert.match(chatSource, /onAsk=\{askZara\}/);
  assert.match(chatSource, /onSuggest=\{fillQuestion\}/);
  assert.match(chatSource, /onSuggestionClick=\{fillQuestion\}/);
});

test("dashboard popovers establish local unclipped stacking contexts", () => {
  assert.match(workspaceCss, /\.dashboard-filter-area:has\(\.more-filters\[open\]\) \{ z-index: 4; \}/);
  assert.match(workspaceCss, /\.dashboard-filter-area \{[^}]*position: relative;[^}]*overflow: visible;/s);
  assert.match(workspaceCss, /\.dashboard-filter-bar \{[^}]*overflow: visible;/s);
  assert.match(workspaceCss, /\.role-metric-card \{[^}]*overflow: visible;/s);
  assert.match(workspaceCss, /\.role-metric-card:focus-within/);
  assert.match(workspaceCss, /\.metric-ask-menu\.is-open/);
  assert.doesNotMatch(legacyCss, /\.role-metric-card \{[^}]*overflow: hidden;/s);
});

test("Ask Zara stays visibly labelled and compact risk explanations use readable contrast", () => {
  assert.match(dashboardSource, /<Sparkles aria-hidden="true" \/> Ask Zara/);
  assert.match(workspaceCss, /\.role-metric-card > \.metric-ask-menu > \.metric-ask-action \{[^}]*width: max-content;[^}]*overflow: visible;[^}]*opacity: 1;/s);
  assert.match(workspaceCss, /\.metric-ask-action svg:first-child \{[^}]*width: 14px;[^}]*color: #4167d2;/s);
  assert.match(workspaceCss, /\.dashboard-attention-panel \.attention-list article \.risk-content > p \{[^}]*color: #43536b;[^}]*font-size: \.62rem;/s);
});
