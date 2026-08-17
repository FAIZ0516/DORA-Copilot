import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const drawerSource = read("../src/components/ReportGenerationDrawer.jsx");
const studioSource = read("../src/features/report-studio/ReportStudio.jsx");
const menuSource = read("../src/components/chat/AddToReportMenu.jsx");
const chatSource = read("../src/components/Chat.jsx");
const appSource = read("../src/App.jsx");
const clientSource = read("../src/services/reports.js");
const dashboardSource = read("../src/components/RoleDashboard.jsx");
const cssSource = read("../src/features/report-studio/report-studio.css");

test("Generate Report opens Report Studio directly instead of a chooser or chat prompt", () => {
  // The whole point of the change: selecting a report type used to build a
  // sentence and post it to /api/chat, which produced an answer the user could
  // not preview, edit, save or export.
  assert.doesNotMatch(drawerSource, /onGenerate|onAsk|Choose how to start/);
  assert.ok(drawerSource.includes("/reports?"));
  assert.match(drawerSource, /params\.set\("start", "current"\)/);
  assert.match(drawerSource, /params\.set\("auto", "1"\)/);
  assert.match(dashboardSource, /window\.location\.assign\(reportStudioUrl\(reportScope\)\)/);
  assert.doesNotMatch(dashboardSource, /<ReportGenerationDrawer/);
});

test("the removed launcher contains no competing report-product choices", () => {
  assert.doesNotMatch(drawerSource, /Generate from Current View|Use Report Template|role="dialog"/);
  assert.doesNotMatch(drawerSource, /ECHO|realtime voice/i);
});

test("the launcher carries the active dashboard scope across", () => {
  assert.match(drawerSource, /reportStudioUrl/);
  for (const key of ["project", "squad", "sprint", "release", "date_from", "date_to", "feature", "issue_type", "status", "priority"]) {
    assert.match(drawerSource, new RegExp(`"${key}"`));
  }
  assert.match(dashboardSource, /const reportScope = \{/);
  assert.match(dashboardSource, /feature: selectedFeature \|\| undefined/);
  assert.doesNotMatch(drawerSource, /current_metric_value|selected_squad_row/);
});

test("Report Studio has its own route and is loaded lazily", () => {
  assert.match(appSource, /lazy\(\(\) => import\("\.\/features\/report-studio\/ReportStudio"\)\)/);
  assert.match(appSource, /path === "\/reports"/);
  assert.match(appSource, /path\.startsWith\("\/reports\/"\)/);
});

test("every report operation goes through the API, never local storage alone", () => {
  // A report must survive a browser refresh, so nothing may be persisted only
  // in React state or localStorage.
  for (const call of [
    "listTemplates", "listReports", "getReport", "createReport", "updateReport",
    "archiveReport", "duplicateReport", "addSection", "updateSection",
    "deleteSection", "reorderSections", "addSource", "removeSource",
    "composeReport", "validateReport", "exportReport",
  ]) {
    assert.match(clientSource, new RegExp(`export (const|async function) ${call}\\b`), call);
  }
  assert.match(clientSource, /"\/api\/reports"/);
  // localStorage is only the hand-off for an unsaved selection, never the store.
  assert.doesNotMatch(clientSource, /localStorage\.setItem\("zara-report/);
});

test("the client reuses the shared session identity rather than inventing one", () => {
  // Reports must resolve to the same user as the conversations they cite.
  assert.match(clientSource, /import \{ getDevelopmentSession \} from "\.\/conversations"/);
  assert.match(clientSource, /"X-Development-Session": getDevelopmentSession\(\)/);
});

test("exports are streamed as a blob, not fetched from a public URL", () => {
  assert.match(clientSource, /await response\.blob\(\)/);
  assert.match(clientSource, /URL\.revokeObjectURL/);
  assert.match(clientSource, /content-disposition/i);
  // No guessable link to a file left on the server.
  assert.doesNotMatch(clientSource, /window\.open\(/);
});

test("Add to report appears on assistant answers and selects what to include", () => {
  assert.match(chatSource, /<AddToReportMenu/);
  assert.match(chatSource, /message\.metadata\?\.message_id/);
  assert.match(chatSource, /message\.role === "assistant" && !message\.error && <AddToReportMenu/);
  for (const selection of ["full", "narrative", "chart", "table", "warnings"]) {
    assert.match(menuSource, new RegExp(`"${selection}"`), selection);
  }
});

test("the three transformation modes exist and rewrite is the default", () => {
  for (const mode of ["rewrite", "summarize", "original"]) {
    assert.match(menuSource, new RegExp(`"${mode}"`), mode);
  }
  assert.match(menuSource, /useState\("rewrite"\)/);
});

test("chart and table selections are hidden when the answer has neither", () => {
  assert.match(menuSource, /value !== "chart" \|\| hasChart/);
  assert.match(menuSource, /value !== "table" \|\| hasTable/);
});

test("adding an answer lands on the report, not back in the create flow", () => {
  // Adding evidence is a different journey from building from scratch: the
  // user already knows what they want, so one click should finish it.
  assert.match(menuSource, /window\.location\.assign\(`\/reports\/\$\{reportId\}`\)/);
  assert.match(menuSource, /window\.location\.assign\(`\/reports\/\$\{report\.id\}`\)/);
  assert.match(studioSource, /deepLinkId/);
  // /reports/<uuid> opens that report directly rather than the library.
  assert.ok(studioSource.includes("window.location.pathname.match"));
  assert.ok(studioSource.includes("[0-9a-f-]{36}"));
});

test("the report list is prefetched so the menu does not pause on open", () => {
  assert.match(menuSource, /onMouseEnter=\{preload\}/);
  assert.match(menuSource, /onFocus=\{preload\}/);
});

test("a selection can go to an existing report or start a new one", () => {
  assert.match(menuSource, /listReports\(\)/);
  assert.match(menuSource, /addSource\(reportId/);
  assert.match(menuSource, /createReport\(\{/);
  assert.match(menuSource, /Create a new report from this answer/);
});

test("only identifiers are sent, never a browser copy of the evidence", () => {
  // The server re-reads the message under the caller's own identity, so the
  // snapshot cannot be forged from the client.
  assert.match(menuSource, /conversation_id: conversationId/);
  assert.match(menuSource, /message_id: messageId/);
  assert.doesNotMatch(menuSource, /answer:|chart:\s*message|table:\s*message/);
});

test("the studio shows scope conflicts rather than merging silently", () => {
  assert.match(studioSource, /report\.conflicts\?\.length > 0/);
  assert.match(studioSource, /Scope differences between sources/);
  assert.match(studioSource, /role="alert"/);
});

test("sections can be edited, reordered, hidden and deleted", () => {
  assert.match(studioSource, /reorderSections\(report\.id, order\)/);
  assert.match(studioSource, /onMove\(index, -1\)/);
  assert.match(studioSource, /onMove\(index, 1\)/);
  assert.match(studioSource, /visible: !target\.visible/);
  assert.match(studioSource, /deleteSection\(report\.id, section\.id\)/);
  assert.match(studioSource, /addSection\(report\.id/);
  // A destructive edit is confirmed first.
  assert.match(studioSource, /window\.confirm\(/);
});

test("one section can be saved without regenerating the whole report", () => {
  assert.match(studioSource, /updateSection\(report\.id, section\.id, \{ content \}\)/);
  assert.match(studioSource, /Save section/);
});

test("internal provenance and validation state stay out of report blocks", () => {
  assert.doesNotMatch(studioSource, /CLASSIFICATION_LABEL/);
  assert.doesNotMatch(studioSource, /Edited by hand/);
  assert.doesNotMatch(studioSource, /Needs review — not re-verified/);
  assert.doesNotMatch(studioSource, /source_ids\?\.length/);
});

test("data freshness is surfaced without rendering internal validation metadata", () => {
  assert.match(studioSource, /freshness\?\.stale/);
  assert.match(studioSource, /Data may be outdated/);
  assert.doesNotMatch(studioSource, /> Validate</);
  assert.doesNotMatch(studioSource, /report\.validation\?\.issues/);
});

test("export offers PDF, DOCX and per-table CSV", () => {
  assert.match(studioSource, /onExport\("pdf"\)/);
  assert.match(studioSource, /onExport\("docx"\)/);
  assert.match(studioSource, /exportReport\(report\.id, "csv", section\.id\)/);
});

test("loading, empty, error and retry states all exist", () => {
  assert.match(studioSource, /status === "loading"/);
  assert.match(studioSource, /status === "error"/);
  assert.match(studioSource, /No reports yet/);
  assert.match(studioSource, /onRetry/);
  assert.match(studioSource, /Try again/);
  assert.match(studioSource, /role="status"/);
});

test("controls are keyboard accessible and labelled", () => {
  // Icon-only buttons must still announce what they do.
  assert.match(studioSource, /aria-label=\{`Move \$\{section\.title \|\| section\.type\} up`\}/);
  assert.match(studioSource, /aria-label=\{section\.visible \?/);
  assert.match(studioSource, /aria-label=\{`Delete \$\{section\.title \|\| section\.type\}`\}/);
  assert.match(studioSource, /aria-label="Report title"/);
  assert.match(studioSource, /aria-label="Report sections"/);
  // The menu closes on Escape and traps nothing.
  assert.match(menuSource, /event\.key === "Escape"/);
  assert.match(menuSource, /aria-expanded=\{open\}/);
  assert.match(cssSource, /:focus-visible/);
});

test("the studio respects reduced motion and is responsive", () => {
  assert.match(cssSource, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(cssSource, /@media \(max-width: 900px\)/);
  assert.match(cssSource, /grid-template-columns: minmax\(0, 1fr\)/);
});

test("the studio reuses the shared chart tokens rather than a new palette", () => {
  for (const token of ["--chart-ink", "--chart-surface", "--chart-card-border", "--chart-series-1"]) {
    assert.match(cssSource, new RegExp(token), token);
  }
});

const newReportSource = read("../src/features/report-studio/NewReport.jsx");

test("dashboard entry auto-prepares while Reports New Report stays lightweight", () => {
  assert.match(studioSource, /params\?\.get\("start"\)/);
  assert.match(studioSource, /const autoCurrent = startMode === "current"/);
  assert.match(studioSource, /scopeFromQuery\.squad && scopeFromQuery\.sprint \? "weekly_scrum" : "executive_summary"/);
  assert.doesNotMatch(newReportSource, /Choose how to start|mode ===/);
  for (const field of ["Project", "Squad", "Sprint", "Template"]) assert.match(newReportSource, new RegExp(`>${field}<`));
  assert.match(newReportSource, /Weekly Scrum Report/);
});

test("Add to report styles ship with the chat page, not the lazy studio route", () => {
  // report-studio.css is imported by the lazily loaded studio, so the button
  // rendered completely unstyled on the chat page.
  const mainCss = read("../src/styles.css");
  assert.match(mainCss, /\.add-to-report-menu/);
  assert.match(mainCss, /\.add-to-report-list/);
  assert.doesNotMatch(cssSource, /\.add-to-report-menu \{/);
});

test("a template carries standard questions and can generate from live data", () => {
  assert.match(clientSource, /export const generateReport/);
  assert.match(clientSource, /\/generate`/);
  assert.match(newReportSource, /useState\("weekly_scrum"\)/);
  assert.match(newReportSource, /Feature Delivery Status/);
  // The generate step is offered at creation and again from the editor.
  assert.match(studioSource, /generateReport\(created\.id\)/);
  assert.match(studioSource, /Refresh Data/);
  // ?create=<template> runs the whole journey with no form in between.
  assert.match(studioSource, /autoTemplate/);
  assert.match(studioSource, /Building your report/);
});

test("Weekly Scrum uses verified squad and sprint option sources", () => {
  assert.match(newReportSource, /loadDashboardSquads/);
  assert.match(newReportSource, /loadDashboardFilters/);
  assert.match(newReportSource, /<select required value=\{scope\.squad\}/);
  assert.match(newReportSource, /<select required value=\{scope\.sprint\}/);
});

test("a handed-over chat answer is acknowledged in the create flow", () => {
  assert.match(newReportSource, /pending &&/);
  assert.match(newReportSource, /selected verified Zara source will remain attached/);
  assert.match(studioSource, /setPending\(true\)/);
});

test("the launcher options are actually styled", () => {
  assert.match(cssSource, /\.report-config-grid/);
  assert.match(cssSource, /\.report-new-actions/);
});

test("the add-to-report menu renders in a portal, not inside the chat message", () => {
  // Inline, the scrim inherited `.copilot-message-meta button:hover`, which
  // repainted the full-viewport overlay pale blue and blanked the page. The
  // message list's overflow-y also clipped the panel.
  assert.match(menuSource, /createPortal\(/);
  assert.match(menuSource, /document\.body,/);
  assert.match(menuSource, /add-to-report-layer/);
  const mainCss = read("../src/styles.css");
  assert.match(mainCss, /\.add-to-report-layer \.add-to-report-scrim:hover/);
  // The blanket overflow override is gone; the portal removes the need.
  assert.doesNotMatch(mainCss, /\.copilot-message-meta \{ overflow: visible/);
});

test("the menu is positioned from the trigger and follows scroll", () => {
  assert.match(menuSource, /getBoundingClientRect\(\)/);
  assert.match(menuSource, /window\.addEventListener\("resize", place\)/);
  assert.match(menuSource, /window\.addEventListener\("scroll", place, true\)/);
});

test("reports in the list are distinguishable from one another", () => {
  // Several reports share a template name, so the row shows scope and age.
  assert.match(menuSource, /report\.scope\?\.squad \|\| "All squads"/);
  assert.match(menuSource, /toLocaleDateString\(\)/);
});

const newReportSrc = read("../src/features/report-studio/NewReport.jsx");
const assistantSource = read("../src/features/report-studio/ReportAssistantPanel.jsx");

test("choosing Weekly Scrum always generates it", () => {
  assert.match(newReportSrc, /\}, \{ generate: true \}\)/);
  assert.doesNotMatch(newReportSrc, /setGenerate/);
  assert.match(newReportSrc, /Create report/);
});

test("PDF preview reuses the report export endpoint and can return to editing", () => {
  assert.match(clientSource, /fetchReportExport\(id, "pdf", null, true\)/);
  assert.match(clientSource, /previewReportPdf/);
  assert.match(studioSource, /Preview PDF/);
  assert.match(studioSource, /Back to Edit Report/);
  assert.match(studioSource, /<iframe src=\{preview\.url\}/);
});

test("template selection lives inside the existing report editor", () => {
  assert.match(clientSource, /applyReportTemplate/);
  assert.match(studioSource, /aria-label="Report template"/);
  assert.match(studioSource, /applyReportTemplate\(report\.id, template\)/);
  assert.match(studioSource, /item\.id === "weekly_scrum" \|\| item\.id === report\.template/);
});

test("the primary toolbar is concise and secondary actions live under More", () => {
  for (const action of ["Refresh Data", "Save Draft", "Preview PDF", "Export"]) {
    assert.match(studioSource, new RegExp(action));
  }
  assert.match(studioSource, /<details className="report-action-menu"><summary aria-label="More report actions"/);
  assert.match(studioSource, /Copy report content/);
  assert.match(studioSource, /Duplicate report/);
  assert.doesNotMatch(studioSource, /> Validate</);
});

test("the visible workspace branding is ZARA Report Studio", () => {
  assert.match(studioSource, /<h1>ZARA Report Studio<\/h1>/);
  assert.match(studioSource, /report-page-brand">RHB <span>REPORT/);
  assert.match(studioSource, /ZARA WEEKLY DELIVERY REPORT/);
  assert.doesNotMatch(studioSource, /DORA COPILOT · ZARA/);
});

test("report creation feedback remains visible on the new-report screen", () => {
  // A create failure must not look like an inert Generate report button.
  assert.match(studioSource, /view !== "editor" && notice/);
  assert.doesNotMatch(studioSource, /view === "library" && notice/);
});

test("returning from an auto-created report shows the library instead of the loading screen", () => {
  assert.match(studioSource, /view === "new" && !report && \(autoTemplate \|\| autoCurrent \|\| deepLinkId\)/);
  assert.match(studioSource, /onBack=\{\(\) => \{ setView\("library"\); setReport\(null\)/);
});

test("an auto-created dashboard report replaces its launch URL with the saved draft URL", () => {
  assert.match(studioSource, /window\.history\.replaceState\(\{\}, "", `\/reports\/\$\{created\.id\}`\)/);
});

test("the dashboard scope in the URL is applied, not discarded", () => {
  // /reports?project=DCPM&squad=JAEGER must produce a JAEGER report.
  assert.match(newReportSrc, /\.\.\.\(initialScope \|\| \{\}\)/);
  assert.match(studioSource, /initialScope=\{scopeFromQuery\}/);
  assert.match(studioSource, /scopeFromQuery/);
});

test("Current View normalizes display-wide labels and uses a contextual title", () => {
  assert.match(newReportSrc, /ALL_SCOPE_LABELS/);
  for (const label of ["all sprints", "all releases", "all available dates", "all tickets"]) {
    assert.match(newReportSrc, new RegExp(label));
  }
  assert.match(studioSource, /`\$\{scopeFromQuery\.squad\} Delivery Report`/);
});

test("an empty template report fills itself with no button to press", () => {
  // However it was created or reopened, a template report with no evidence
  // answers its own questions rather than showing a wall of empty sections.
  assert.match(studioSource, /report\.template === "blank" \|\| report\.sources\.length > 0/);
  assert.match(studioSource, /filledRef\.current\.has\(report\.id\)/);
  assert.match(studioSource, /generateReport\(report\.id\)/);
  assert.match(studioSource, /Answering this report's questions from live data/);
  // Guarded so it runs once per report, never in a loop.
  assert.match(studioSource, /filledRef\.current\.add\(report\.id\)/);
});

test("the existing dev proxy continues to route report APIs to the documented backend", () => {
  const viteConfig = read("../vite.config.js");
  assert.match(viteConfig, /"\/api": \{/);
  assert.match(viteConfig, /target: "http:\/\/127\.0\.0\.1:8000"/);
  assert.doesNotMatch(viteConfig, /ws: true/);
});

test("the workspace renders deterministic states and structured report content", () => {
  assert.match(studioSource, /Needs Input/);
  assert.doesNotMatch(studioSource, /Not written yet/);
  assert.match(studioSource, /function StructuredTable/);
  assert.match(studioSource, /function SimpleChart/);
  assert.match(studioSource, /section\.state/);
});

test("Zara refines only the selected narrative section", () => {
  assert.match(studioSource, /refineReportSection\(report\.id, section\.id, instruction\)/);
  assert.match(studioSource, /updated_sections\?\.includes\(section\.id\)/);
  assert.match(studioSource, /item\.id === section\.id \? updated : item/);
  assert.match(studioSource, /<ReportAssistantPanel/);
  assert.match(assistantSource, /selectedSection/);
  assert.match(assistantSource, /async function submit/);
  assert.match(assistantSource, /await onRefine\(selectedSection, instruction\.trim\(\)\)/);
  assert.match(assistantSource, /if \(updated\) setInstruction\(""\)/);
  assert.match(assistantSource, /Verified facts are protected/);
});

test("the report refinement panel reuses Zara's calmer animated visual system", () => {
  assert.match(assistantSource, /Grainient, \{ ZARA_GRAINIENT_THEME \}/);
  assert.match(assistantSource, /<Grainient \{\.\.\.ZARA_GRAINIENT_THEME\} \/>/);
  assert.doesNotMatch(assistantSource, /timeSpeed=/);
  assert.match(cssSource, /\.report-assistant-grainient \{ position: absolute;/);
  assert.match(cssSource, /\.report-assistant-panel \{[^}]*background: #031a4a;/s);
  assert.match(cssSource, /\.report-assistant-panel header h3 \{ color: #fff;/);
  assert.match(cssSource, /\.report-assistant-suggestions button \{[^}]*background: rgba\(255,255,255,\.93\);/s);
  assert.match(cssSource, /\.report-assistant-panel select, \.report-assistant-panel textarea \{[^}]*background: rgba\(255,255,255,\.96\);/s);
  assert.match(assistantSource, /components\/chat\/ZaraAvatar/);
  assert.match(assistantSource, /<ZaraAvatar decorative size=\{34\}/);
  assert.doesNotMatch(assistantSource, /<Sparkles/);
});

test("methodology and evidence navigation stay out of the authored report surface", () => {
  assert.match(studioSource, /\["cover", "methodology"\]\.includes\(section\.type\)/);
  assert.doesNotMatch(studioSource, /<h3>Evidence<\/h3>/);
  assert.match(newReportSource, /Data Quality and Limitations/);
  assert.doesNotMatch(newReportSource, /Evidence \(appendix\)/);
});

test("Save Draft and clipboard Copy are distinct from Duplicate", () => {
  assert.match(studioSource, /Save Draft/);
  assert.match(studioSource, /copyReportContent/);
  assert.match(studioSource, /navigator\.clipboard\.writeText/);
  assert.match(studioSource, /Duplicate report/);
});
