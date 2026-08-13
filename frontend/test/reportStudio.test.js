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
  assert.match(drawerSource, /\/reports\?start=/);
  // The dashboard no longer hands the drawer a way to ask the assistant.
  assert.doesNotMatch(dashboardSource, /ReportGenerationDrawer[^/]*onGenerate/);
});

test("the launcher offers the three documented starting points", () => {
  for (const start of ["template", "chat", "blank"]) {
    assert.match(drawerSource, new RegExp(`/reports\\?start=${start}`));
  }
  assert.match(drawerSource, /Use a template/);
  assert.match(drawerSource, /Build from chat/);
  assert.match(drawerSource, /Start blank/);
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

test("a selection can go to an existing report or start a new one", () => {
  assert.match(menuSource, /listReports\(\)/);
  assert.match(menuSource, /addSource\(reportId/);
  assert.match(menuSource, /stashPendingSource/);
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
