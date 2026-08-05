import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  DASHBOARD_KPIS,
  ageBucketForDays,
  ageingPrompt,
  issueTypePrompt,
  kpiCards,
} from "../src/dashboardConfig.js";

test("dashboard is placed above suggested questions", () => {
  const source = readFileSync(new URL("../src/components/Chat.jsx", import.meta.url), "utf8");
  assert.ok(source.indexOf("<JiraDeliveryOverview") < source.indexOf("empty-chat-suggestions"));
});

test("all four KPI cards use live aggregate values and correct percentage", () => {
  const cards = kpiCards({
    total_issues: 200,
    open_work_count: 80,
    impeded_issues: 6,
    missing_squad_count: 50,
    missing_squad_pct: 25,
  });
  assert.deepEqual(cards.map((card) => card.value), [200, 80, 6, 50]);
  assert.equal(cards[3].percentage, 25);
});

test("KPI and chart drill-down prompts are exact and contain no SQL", () => {
  assert.equal(
    DASHBOARD_KPIS[0].prompt,
    "Explain the current Jira issue composition by issue type and status category.",
  );
  assert.equal(issueTypePrompt("Bug"), "Analyse current Jira issues where issuetype is 'Bug'.");
  assert.match(ageingPrompt("30-60 days"), /priority and ownership coverage/);
  assert.equal(DASHBOARD_KPIS.some((item) => /select\s/i.test(item.prompt)), false);
});

test("calendar age buckets have exclusive boundary assignments", () => {
  assert.deepEqual(
    [null, 0, 29, 30, 60, 61, 90, 91].map(ageBucketForDays),
    [
      "Unknown created date",
      "Less than 30 days",
      "Less than 30 days",
      "30-60 days",
      "30-60 days",
      "61-90 days",
      "61-90 days",
      "More than 90 days",
    ],
  );
});

test("project changes request fresh scope and manual refresh bypasses cache", async () => {
  const storage = new Map();
  globalThis.window = {
    localStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
    },
    crypto: { randomUUID: () => "dashboard-development-session" },
  };
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    return { ok: true, json: async () => ({}) };
  };
  const { loadJiraDashboard } = await import("../src/services/dashboard.js");
  await loadJiraDashboard("DCPM");
  await loadJiraDashboard("OTHER");
  await loadJiraDashboard("DCPM", { refresh: true });
  assert.match(calls[0], /project_key=DCPM/);
  assert.match(calls[1], /project_key=OTHER/);
  assert.match(calls[2], /project_key=DCPM/);
  assert.match(calls[2], /refresh=true/);
});

test("dashboard wording does not equate Done with success or age with DORA metrics", () => {
  const source = readFileSync(new URL("../src/components/JiraDeliveryOverview.jsx", import.meta.url), "utf8");
  assert.match(source, /Done is an end-state/);
  assert.doesNotMatch(source, /Done (?:is|means) successful delivery/i);
  assert.match(source, /not cycle time or DORA lead time/i);
});

test("dashboard has mobile one-column rules without an internal scrollbar", () => {
  const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /@media \(max-width: 560px\)[\s\S]*?\.jira-kpi-grid\s*\{[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/);
  assert.doesNotMatch(css, /\.jira-dashboard-expanded\s*\{[^}]*overflow-y:\s*(?:auto|scroll)/);
});
