import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { getRoleDashboardConfig } from "../src/config/roleDashboardConfig.js";
import { DEFAULT_PANEL_LAYOUT, normalizePanelLayout, panelColumns } from "../src/hooks/usePanelLayout.js";

const chatSource = readFileSync(new URL("../src/components/Chat.jsx", import.meta.url), "utf8");
const layoutSource = readFileSync(new URL("../src/components/layout/ThreePanelWorkspace.jsx", import.meta.url), "utf8");
const suggestionSource = readFileSync(new URL("../src/components/chat/SuggestedQuestionChips.jsx", import.meta.url), "utf8");
const chartSource = readFileSync(new URL("../src/components/MetricChart.jsx", import.meta.url), "utf8");
const cssSource = readFileSync(new URL("../src/workspace.css", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const historySource = readFileSync(new URL("../src/components/history/ConversationPanel.jsx", import.meta.url), "utf8");

test("the dashboard has one role-neutral configuration", () => {
  const scrum = getRoleDashboardConfig("scrum_master");
  const head = getRoleDashboardConfig("head_of_department");
  assert.equal(scrum, head);
  assert.equal(scrum.dashboardTitle, "All DCP Squads Overview");
});

test("panel collapse state is normalized without a restore-default toolbar", () => {
  assert.deepEqual(normalizePanelLayout({ history: false, dashboard: true, chat: false }), { history: false, dashboard: true, chat: false });
  assert.deepEqual(normalizePanelLayout({ history: false, dashboard: false, chat: false }), DEFAULT_PANEL_LAYOUT);
  assert.match(layoutSource, /Collapse \$\{meta\.actionName\}/);
  assert.match(layoutSource, /Expand \$\{meta\.actionName\}/);
  assert.doesNotMatch(layoutSource, /restoreDefault|Restore Default/);
});

test("every supported panel combination redistributes available width", () => {
  const all = panelColumns({ history: true, dashboard: true, chat: true });
  assert.match(all, /minmax\(420px, 1fr\)/);
  assert.match(all, /minmax\(320px, 360px\)/);

  const onlyDashboard = panelColumns({ history: false, dashboard: true, chat: false });
  const onlyZara = panelColumns({ history: false, dashboard: false, chat: true });
  const onlyMenu = panelColumns({ history: true, dashboard: false, chat: false });
  for (const columns of [onlyDashboard, onlyZara, onlyMenu]) {
    assert.match(columns, /minmax\(0, 1fr\)/);
  }
  assert.equal(onlyDashboard, "48px minmax(0, 1fr) 48px");
  assert.equal(onlyZara, "48px 48px minmax(0, 1fr)");
  assert.equal(onlyMenu, "minmax(0, 1fr) 48px 48px");

  assert.equal(
    panelColumns({ history: true, dashboard: false, chat: true }),
    "minmax(210px, 1fr) 48px minmax(320px, 1fr)",
  );
});

test("panel icons and labels describe the action for each orientation", () => {
  for (const label of ["menu", "dashboard", "Zara"]) {
    assert.match(layoutSource, new RegExp(`actionName: "${label}"`));
  }
  for (const icon of ["PanelLeftClose", "PanelLeftOpen", "Minimize2", "Maximize2", "PanelRightClose", "PanelRightOpen"]) {
    assert.match(layoutSource, new RegExp(icon));
  }
});

test("ZARA branding uses the shared image asset with accessible text", () => {
  assert.match(layoutSource, /zara-wordmark\.png/);
  assert.match(layoutSource, /alt="ZARA"/);
  assert.match(layoutSource, /aria-label="ZARA AI Chat"/);
  assert.match(appSource, /zara-wordmark\.png/);
  assert.match(appSource, /alt="ZARA"/);
  assert.doesNotMatch(appSource, /zara-text-brand/);
  assert.doesNotMatch(appSource, /ECHO/);
});

test("suggested questions fill the composer and never send directly", () => {
  assert.match(suggestionSource, /onSuggestionClick\(question\)/);
  assert.doesNotMatch(suggestionSource, /sendChat|sendMessage/);
  assert.match(chatSource, /function fillQuestion/);
  assert.match(chatSource, /setInput\(question\)/);
  assert.match(chatSource, /onSuggestionClick=\{fillQuestion\}/);
});

test("follow-up suggestions appear after an assistant response", () => {
  assert.match(chatSource, /latestAssistantId/);
  assert.match(chatSource, /Continue exploring/);
  assert.match(chatSource, /requestFollowUpQuestions/);
  assert.match(chatSource, /message\.followUps \|\| \[\]/);
});

test("scope changes refresh dashboard context without role switching or reload", () => {
  assert.match(chatSource, /continueInScope/);
  assert.match(chatSource, /scope_mismatch/);
  assert.match(chatSource, /onProjectChange=\{setProject\}/);
  assert.doesNotMatch(chatSource, /onRoleChange|changeRole/);
  assert.doesNotMatch(chatSource, /window\.location\.reload/);
});

test("mobile navigation exposes Menu, Dashboard, and Zara", () => {
  assert.match(layoutSource, /workspace-mobile-tabs/);
  assert.match(layoutSource, /history:/);
  assert.match(layoutSource, /dashboard:/);
  assert.match(layoutSource, /chat:/);
  assert.match(cssSource, /@media \(max-width: 1050px\)/);
  assert.match(cssSource, /data-mobile-panel="dashboard"/);
});

test("the app enters the workspace directly and recent chats stay collapsed", () => {
  // The role-selection screen was removed entirely: there is no screen
  // state and no chooser, so the workspace renders immediately.
  assert.doesNotMatch(appSource, /role-selection/);
  assert.doesNotMatch(appSource, /setScreen/);
  assert.doesNotMatch(appSource, /Get Started|welcome-screen/);
  assert.match(historySource, /<details className="recent-chats-accordion">/);
  assert.doesNotMatch(historySource, /<details className="recent-chats-accordion" open/);
  assert.match(historySource, />Dashboard</);
  assert.match(historySource, />Reports</);
  assert.match(historySource, />Zara Assistant</);
  assert.doesNotMatch(historySource, />Settings</);
});

test("invalid AI chart schemas are rejected without executing generated code", () => {
  assert.match(chartSource, /ALLOWED_CHART_TYPES/);
  assert.match(chartSource, /validateChartSchema/);
  assert.match(chartSource, /Chart data was rejected safely/);
  assert.doesNotMatch(chartSource, /eval\(|new Function/);
});
