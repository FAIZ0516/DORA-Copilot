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

test("Generate Report opens Report Studio instead of sending a chat prompt", () => {
  // The whole point of the change: selecting a report type used to build a
  // sentence and post it to /api/chat, which produced an answer the user could
  // not preview, edit, save or export.
  assert.doesNotMatch(drawerSource, /onGenerate|onAsk/);
  assert.doesNotMatch(drawerSource, /using only the currently selected dashboard scope/);
  assert.ok(drawerSource.includes("/reports?"));
  // The dashboard no longer hands the drawer a way to ask the assistant.
  assert.doesNotMatch(dashboardSource, /ReportGenerationDrawer[^/]*onGenerate/);
});

test("the launcher lists the ready-to-run report types directly", () => {
  // One click creates, generates and opens the report -- no chooser page and
  // no form. Only templates with standard questions belong in that list.
  assert.match(drawerSource, /listTemplates\(\)/);
  assert.match(drawerSource, /item\.questions\?\.length/);
  assert.match(drawerSource, /go\(\{ create: template\.id \}\)/);
  assert.match(drawerSource, /Generate now/);
  // The author-it-yourself paths stay available, but secondary.
  assert.match(drawerSource, /go\(\{ start: "chat" \}\)/);
  assert.match(drawerSource, /go\(\{ start: "blank" \}\)/);
  // The options must be real buttons: they were anchors, which no stylesheet
  // targeted, so every option rendered as unstyled inline text.
  assert.doesNotMatch(drawerSource, /<a key=\{id\}/);
});

test("the launcher carries the active dashboard scope across", () => {
  assert.match(drawerSource, /scopeQuery/);
  for (const key of ["project", "squad", "sprint", "release", "date_from", "date_to"]) {
    assert.match(drawerSource, new RegExp(`"${key}"`));
  }
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

test("provenance and trust state are visible on each block", () => {
  assert.match(studioSource, /CLASSIFICATION_LABEL/);
  for (const key of ["observed_fact", "interpretation", "recommendation", "user_authored"]) {
    assert.match(studioSource, new RegExp(key), key);
  }
  assert.match(studioSource, /section\.manually_edited && <span[^>]*>Edited by hand/);
  assert.match(studioSource, /Needs review/);
  assert.match(studioSource, /source_ids\?\.length/);
});

test("data freshness and validation state are surfaced", () => {
  assert.match(studioSource, /freshness\?\.stale/);
  assert.match(studioSource, /Data may be outdated/);
  assert.match(studioSource, /validateReport\(report\.id\)/);
  assert.match(studioSource, /report\.validation\?\.issues/);
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

test("the launcher options land on different states, not all the same page", () => {
  // They previously all opened the same library screen, so the choice did
  // nothing at all.
  assert.match(studioSource, /params\?\.get\("start"\)/);
  assert.match(studioSource, /params\?\.get\("create"\)/);
  assert.match(studioSource, /startMode \|\| autoTemplate \|\| deepLinkId \? "new" : "library"/);
  assert.match(studioSource, /start=\{startMode\}/);
  assert.match(newReportSource, /const START_MODES = \{/);
  for (const mode of ["template", "chat", "blank"]) {
    assert.match(newReportSource, new RegExp(`${mode}: \{`), mode);
  }
  // Blank skips the type picker; the others start on it.
  assert.match(newReportSource, /mode === "blank" \? 2 : 1/);
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
  assert.match(newReportSource, /chosen\.questions\.map/);
  assert.match(newReportSource, /What this report answers/);
  // The generate step is offered at creation and again from the editor.
  assert.match(studioSource, /generateReport\(created\.id\)/);
  assert.match(studioSource, /Refresh from data/);
  // ?create=<template> runs the whole journey with no form in between.
  assert.match(studioSource, /autoTemplate/);
  assert.match(studioSource, /Building your report/);
});

test("creating a report is two steps, not one long form", () => {
  assert.match(newReportSource, /report-steps/);
  assert.match(newReportSource, /Choose a type/);
  assert.match(newReportSource, /Set the details/);
  assert.match(newReportSource, /setStep\(2\)/);
  assert.match(newReportSource, /setStep\(1\)/);
});

test("a handed-over chat answer is acknowledged in the create flow", () => {
  assert.match(newReportSource, /pending &&/);
  assert.match(newReportSource, /will be attached once the report is created/);
  assert.match(studioSource, /setPending\(true\)/);
});

test("the launcher options are actually styled", () => {
  // The previous version used anchors while the stylesheet targeted buttons,
  // so every option rendered as unstyled inline text.
  const workspaceCss = read("../src/workspace.css");
  assert.match(workspaceCss, /\.report-type-list button \{/);
  assert.match(workspaceCss, /\.report-type-icon \{/);
  assert.match(workspaceCss, /\.report-type-text \{/);
  assert.match(workspaceCss, /\.report-drawer-lead \{/);
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

test("a template report generates by default, whichever door you came through", () => {
  // Tying this to ?start=template meant a report begun from the chat or
  // library path was created empty, with every section reading
  // "Not written yet."
  assert.match(newReportSrc, /useState\(true\)/);
  assert.match(newReportSrc, /setGenerate\(\(chosen\.questions\?\.length \|\| 0\) > 0\)/);
  assert.doesNotMatch(newReportSrc, /useState\(mode === "template"\)/);
});

test("the dashboard scope in the URL is applied, not discarded", () => {
  // /reports?project=DCPM&squad=JAEGER must produce a JAEGER report.
  assert.match(newReportSrc, /\.\.\.\(initialScope \|\| \{\}\)/);
  assert.match(studioSource, /initialScope=\{scopeFromQuery\}/);
  assert.match(studioSource, /scopeFromQuery/);
});

test("an empty template report offers to fill itself in one click", () => {
  assert.match(studioSource, /report\.sources\.length === 0 && report\.template !== "blank"/);
  assert.match(studioSource, /This report has no data yet/);
  assert.match(studioSource, /Fill from live data/);
  const studioCss = read("../src/features/report-studio/report-studio.css");
  assert.match(studioCss, /\.report-fill-prompt \{/);
});
