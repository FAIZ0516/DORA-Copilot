import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { getRoleDashboardConfig } from "../src/config/roleDashboardConfig.js";
import { DEFAULT_PANEL_LAYOUT, normalizePanelLayout, panelColumns } from "../src/hooks/usePanelLayout.js";

const chatSource = readFileSync(new URL("../src/components/Chat.jsx", import.meta.url), "utf8");
const layoutSource = readFileSync(new URL("../src/components/layout/ThreePanelWorkspace.jsx", import.meta.url), "utf8");
const suggestionSource = readFileSync(new URL("../src/components/chat/SuggestedQuestionChips.jsx", import.meta.url), "utf8");
const chartSource = readFileSync(new URL("../src/components/MetricChart.jsx", import.meta.url), "utf8");
const cssSource = readFileSync(new URL("../src/workspace.css", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const historySource = readFileSync(new URL("../src/components/history/ConversationPanel.jsx", import.meta.url), "utf8");
const grainientSource = readFileSync(new URL("../src/components/Grainient.jsx", import.meta.url), "utf8");
const avatarSource = readFileSync(new URL("../src/components/chat/ZaraAvatar.jsx", import.meta.url), "utf8");
const avatarCssSource = readFileSync(new URL("../src/components/chat/ZaraAvatar.css", import.meta.url), "utf8");
const zaraWorkspaceSource = readFileSync(new URL("../src/features/zara-workspace/features/assistant/components/ZaraPanel.tsx", import.meta.url), "utf8");

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

test("Grainient is an isolated responsive background for the Zara panel", () => {
  assert.match(layoutSource, /panel === "chat" && <ZaraGrainientBackground/);
  assert.match(layoutSource, /className="zara-grainient-background" aria-hidden="true"/);
  assert.match(layoutSource, /<Grainient \{\.\.\.ZARA_GRAINIENT_THEME\} \/>/);
  assert.match(grainientSource, /ZARA_GRAINIENT_SPEED = 0\.32/);
  assert.match(grainientSource, /timeSpeed: ZARA_GRAINIENT_SPEED/);
  assert.match(grainientSource, /saturation: 1\.18/);
  assert.match(grainientSource, /color1: "#18C4FF"/);
  assert.match(grainientSource, /color2: "#064FC8"/);
  assert.match(grainientSource, /color3: "#031A4A"/);
  assert.match(cssSource, /\.zara-grainient-background \{ position: absolute; z-index: 0; inset: 0;/);
  assert.match(cssSource, /pointer-events: none/);
  assert.match(cssSource, /\.workspace-panel-chat > \.workspace-panel-content[\s\S]*z-index: 1/);
  assert.match(grainientSource, /new ResizeObserver\(setSize\)/);
  assert.match(grainientSource, /new IntersectionObserver/);
  assert.match(grainientSource, /prefers-reduced-motion: reduce/);
  assert.match(grainientSource, /typeof window\.WebGL2RenderingContext === "undefined"/);
  assert.match(grainientSource, /context\.renderer\.render\(\{ scene: context\.mesh \}\)/);
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
  assert.match(suggestionSource, /ChevronRight/);
  assert.doesNotMatch(suggestionSource, /sendChat|sendMessage/);
  assert.match(chatSource, /function fillQuestion/);
  assert.match(chatSource, /setInput\(question\)/);
  assert.match(chatSource, /onSuggestionClick=\{fillQuestion\}/);
});

test("assistant identity uses one shared circular Zara portrait", () => {
  assert.ok(existsSync(new URL("../src/assets/zara-avatar.png", import.meta.url)));
  assert.match(avatarSource, /zara-avatar\.png/);
  assert.match(avatarSource, /width=\{size\}/);
  assert.match(avatarSource, /height=\{size\}/);
  assert.match(avatarCssSource, /object-fit: cover/);
  assert.match(avatarCssSource, /object-position: center/);
  assert.match(avatarCssSource, /border-radius: 50%/);
  assert.match(chatSource, /<ZaraAvatar className="copilot-empty-avatar" decorative size=\{36\}/);
  assert.match(chatSource, /<ZaraAvatar className="copilot-message-avatar" decorative size=\{34\}/);
  assert.doesNotMatch(chatSource, /message\.role === "assistant" \? "AI"/);
  assert.match(zaraWorkspaceSource, /components\/chat\/ZaraAvatar/);
  assert.doesNotMatch(zaraWorkspaceSource, /<Bot|<Sparkles/);
});

test("the Zara surface keeps a premium high-contrast visual hierarchy", () => {
  assert.match(cssSource, /\.copilot-empty-state h2 \{[^}]*color: #fff;/s);
  assert.match(cssSource, /\.suggested-question-chips button \{[^}]*color: #09245f;[^}]*background: rgba\(255,255,255,\.94\);/s);
  assert.match(cssSource, /\.copilot-message\.user \.copilot-message-body \{[^}]*rgba\(8,70,200,\.97\)[^}]*border-radius: 19px/s);
  assert.match(cssSource, /\.copilot-message-body \{[^}]*background: rgba\(255,255,255,\.96\);[^}]*border-radius: 6px 18px 18px 18px;/s);
  assert.match(cssSource, /\.copilot-message-content \{[^}]*color: #10182e;/s);
  assert.match(cssSource, /\.copilot-composer \{[^}]*rgba\(9,48,119,\.7\)[^}]*border-radius: 21px;/s);
});

test("the Zara panel remains one continuous glass surface with subtle scrolling", () => {
  assert.match(cssSource, /\.workspace-panel-chat \.workspace-panel-header \{[^}]*rgba\(2,20,61,\.62\)[^}]*backdrop-filter: blur\(16px\);/s);
  assert.match(cssSource, /\.copilot-toolbar \{[^}]*rgba\(2,21,64,\.58\)[^}]*backdrop-filter: blur\(16px\);/s);
  assert.match(cssSource, /\.copilot-composer-wrap \{[^}]*rgba\(1,15,49,0\)[^}]*box-shadow: none;[^}]*backdrop-filter: none;/s);
  assert.match(cssSource, /\.copilot-composer \{[^}]*backdrop-filter: blur\(20px\);/s);
  assert.match(cssSource, /\.copilot-message-list \{[^}]*padding: 16px 11px 52px;[^}]*scrollbar-width: thin;/s);
  assert.match(cssSource, /\.copilot-message-list::\-webkit-scrollbar-thumb:hover/);
  assert.match(cssSource, /\.copilot-empty-avatar \{[^}]*rgba\(35,145,255,\.2\)/s);
});

test("initial suggestions use a centred two-column grid only when the Zara panel is wide enough", () => {
  assert.match(cssSource, /\.workspace-panel-chat \{[^}]*container: zara-chat \/ inline-size;/s);
  assert.match(cssSource, /\.copilot-empty-state \.suggested-question-section \{[^}]*width: min\(100%,1100px\);[^}]*margin-top: 11px;/s);
  assert.match(cssSource, /\.suggested-question-chips \{[^}]*grid-template-columns: minmax\(0,1fr\);/s);
  assert.match(cssSource, /@container zara-chat \(min-width: 640px\)[\s\S]*\.copilot-empty-state \.suggested-question-chips \{ grid-template-columns: repeat\(2,minmax\(0,1fr\)\); \}/);
  assert.match(cssSource, /\.copilot-composer \{[^}]*border: 1px solid rgba\(211,234,255,\.34\);[^}]*0 0 14px rgba\(8,124,255,\.14\)/s);
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

test("expanded dashboard filters stay in flow above KPI cards", () => {
  const filterPanelRule = cssSource.match(/\.more-filters\s*>\s*div\s*\{([^}]*)\}/)?.[1] || "";
  assert.match(cssSource, /\.dashboard-filter-bar\s*>\s*\.more-filters\[open\]\s*\{\s*grid-column:\s*1\s*\/\s*-1/);
  assert.doesNotMatch(filterPanelRule, /position:\s*(?:absolute|fixed)/);
  assert.match(filterPanelRule, /grid-template-columns:\s*repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(cssSource, /\.more-filters\[open\]\s*>\s*div\s*\{\s*grid-template-columns:\s*repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(cssSource, /\.more-filters\[open\]\s*>\s*div\s*\{\s*grid-template-columns:\s*1fr/);
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
