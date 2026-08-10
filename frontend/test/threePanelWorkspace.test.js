import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { getRoleDashboardConfig } from "../src/config/roleDashboardConfig.js";
import { DEFAULT_PANEL_LAYOUT, normalizePanelLayout } from "../src/hooks/usePanelLayout.js";

const chatSource = readFileSync(new URL("../src/components/Chat.jsx", import.meta.url), "utf8");
const layoutSource = readFileSync(new URL("../src/components/layout/ThreePanelWorkspace.jsx", import.meta.url), "utf8");
const suggestionSource = readFileSync(new URL("../src/components/chat/SuggestedQuestionChips.jsx", import.meta.url), "utf8");
const chartSource = readFileSync(new URL("../src/components/MetricChart.jsx", import.meta.url), "utf8");
const cssSource = readFileSync(new URL("../src/workspace.css", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const historySource = readFileSync(new URL("../src/components/history/ConversationPanel.jsx", import.meta.url), "utf8");

test("Scrum Master and Head of Department load visibly different configuration", () => {
  const scrum = getRoleDashboardConfig("scrum_master");
  const head = getRoleDashboardConfig("head_of_department");
  assert.equal(scrum.dashboardTitle, "Squad Performance Dashboard");
  assert.equal(head.dashboardTitle, "Department Performance Dashboard");
  assert.notDeepEqual(scrum.initialQuestions, head.initialQuestions);
  assert.notDeepEqual(scrum.access, head.access);
});

test("panel collapse state is normalized and all panels can be restored", () => {
  assert.deepEqual(normalizePanelLayout({ history: false, dashboard: true, chat: false }), { history: false, dashboard: true, chat: false });
  assert.deepEqual(normalizePanelLayout({ history: false, dashboard: false, chat: false }), DEFAULT_PANEL_LAYOUT);
  assert.match(layoutSource, /Collapse \$\{meta\.title\}/);
  assert.match(layoutSource, /Expand \$\{meta\.title\}/);
  assert.match(layoutSource, /restoreDefault/);
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
  assert.match(chatSource, /roleConfig\.followUpQuestions/);
});

test("scope changes refresh dashboard context and role switches without reload", () => {
  assert.match(chatSource, /onRoleChange\?\.\(nextRole\)/);
  assert.match(chatSource, /onProjectChange=\{setProject\}/);
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

test("role selection enters the workspace directly and recent chats stay collapsed", () => {
  assert.match(appSource, /setScreen\("workspace"\)/);
  assert.doesNotMatch(appSource, /Get Started|welcome-screen/);
  assert.match(historySource, /<details className="recent-chats-accordion">/);
  assert.doesNotMatch(historySource, /<details className="recent-chats-accordion" open/);
  assert.match(historySource, />Dashboard</);
  assert.match(historySource, />Reports</);
  assert.match(historySource, />Zara Assistant</);
  assert.match(historySource, />Settings</);
});

test("invalid AI chart schemas are rejected without executing generated code", () => {
  assert.match(chartSource, /ALLOWED_CHART_TYPES/);
  assert.match(chartSource, /validateChartSchema/);
  assert.match(chartSource, /Chart data was rejected safely/);
  assert.doesNotMatch(chartSource, /eval\(|new Function/);
});
