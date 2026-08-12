import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  METRICS_WITH_CURATED_QUESTIONS,
  buildMetricQuestions,
  describeValue,
  groundQuestion,
  scopePhrase,
} from "../src/dashboardQuestions.js";

const dashboardSource = readFileSync(new URL("../src/components/RoleDashboard.jsx", import.meta.url), "utf8");
const drawerSource = readFileSync(new URL("../src/components/MetricInfoDrawer.jsx", import.meta.url), "utf8");

const SCOPE = { squad: "MBK", project: "DCPM" };
const card = (key, value, extra = {}) => ({ key, title: "Metric", value, ...extra });

/** Words that only resolve against something on screen. */
const DEICTIC = /\b(this|these|those|them|it)\b/i;

test("every generated question states its own scope", () => {
  // The whole cause of the old failures: "Why is this percentage low?" means
  // nothing without the screen, so the assistant asked which percentage.
  // A question must therefore name the project, and either the selected squad
  // or -- for deliberate cross-squad comparisons -- say "all squads".
  for (const key of METRICS_WITH_CURATED_QUESTIONS) {
    for (const value of [0, 43.2, 91.4, "Needs Attention", "Healthy"]) {
      for (const option of buildMetricQuestions(card(key, value), SCOPE)) {
        const context = `${key}=${value}: ${option.label}`;
        assert.match(option.question, /DCPM/, `${context}: no project`);
        assert.ok(
          /MBK/.test(option.question) || /all squads|squads in DCPM/i.test(option.question),
          `${context}: neither a squad nor an explicit all-squads scope`,
        );
        assert.ok(option.label && option.id, `${context}: missing label/id`);
      }
    }
  }
});

test("a question never opens with a bare pronoun", () => {
  for (const key of METRICS_WITH_CURATED_QUESTIONS) {
    for (const option of buildMetricQuestions(card(key, 42), SCOPE)) {
      const opening = option.question.split(/[.?]/)[0];
      assert.doesNotMatch(
        opening,
        /^(Why is this|What is this|Rank them|Show them)/i,
        `${key}: question opens deictically -- ${opening}`,
      );
    }
  }
});

test("completion questions follow the value instead of presuming it is low", () => {
  const low = buildMetricQuestions(card("completion_pct", 43.2, { suffix: "%" }), SCOPE);
  const mid = buildMetricQuestions(card("completion_pct", 62, { suffix: "%" }), SCOPE);
  const high = buildMetricQuestions(card("completion_pct", 91.4, { suffix: "%" }), SCOPE);

  assert.ok(low.some((option) => /this low/i.test(option.question)));
  assert.ok(mid.some((option) => /holding completion back/i.test(option.question)));
  // The original bug: a strong percentage must never be asked why it is low.
  assert.ok(high.some((option) => /driving this level/i.test(option.question)));
  for (const option of high) {
    assert.doesNotMatch(option.question, /why is it (this )?low/i);
  }
});

test("the current value is stated in the question so the answer can use it", () => {
  const [first] = buildMetricQuestions(card("completion_pct", 43.2, { suffix: "%" }), SCOPE);
  assert.match(first.question, /43\.2%/);
});

test("a metric at zero never offers questions about items that do not exist", () => {
  const none = buildMetricQuestions(card("impeded_work", 0), SCOPE);
  assert.ok(none.some((option) => /No work is currently impeded/i.test(option.question)));
  for (const option of none) {
    assert.doesNotMatch(option.question, /which should be unblocked first/i);
  }

  const some = buildMetricQuestions(card("impeded_work", 4), SCOPE);
  assert.ok(some.some((option) => /unblocked first/i.test(option.question)));
  assert.ok(some.some((option) => /4 tickets are currently impeded/i.test(option.question)));
});

test("delivery-risk options match the actual status", () => {
  const flagged = buildMetricQuestions(card("delivery_risk", "Needs Attention"), SCOPE);
  assert.ok(flagged.some((option) => /which attention thresholds were crossed/i.test(option.question)));

  const healthy = buildMetricQuestions(card("delivery_risk", "Healthy"), SCOPE);
  // Asking "why is it flagged" when it is not flagged is the same class of bug.
  for (const option of healthy) {
    assert.doesNotMatch(option.question, /is Needs Attention/i);
  }
  assert.ok(healthy.some((option) => /closest to crossing/i.test(option.question)));
});

test("grounding gives a reused registry question its antecedent", () => {
  const grounded = groundQuestion("Rank them by age and explain the factors.", {
    title: "High-priority Open Bugs",
    value: 12,
    scope: SCOPE,
  });
  // "them" now refers to something inside the message itself.
  assert.match(grounded, /High-priority Open Bugs is currently 12/);
  assert.match(grounded, /squad MBK in DCPM/);
  assert.ok(grounded.endsWith("Rank them by age and explain the factors."));
  assert.ok(DEICTIC.test(grounded), "the original wording is preserved");
});

test("grounding is a no-op without a metric, and safe on empty input", () => {
  assert.equal(groundQuestion("Plain question?"), "Plain question?");
  assert.equal(groundQuestion(""), "");
  assert.equal(groundQuestion(null), "");
});

test("scope wording covers all squads, one squad, and extra filters", () => {
  assert.equal(scopePhrase({}), "all squads in DCPM");
  assert.equal(scopePhrase({ squad: "MBK", project: "DCPM" }), "squad MBK in DCPM");
  assert.equal(
    scopePhrase({ squad: "MBK", sprint: "Sprint 4", release: "R2", project: "DCPM" }),
    "squad MBK, sprint Sprint 4, release R2 in DCPM",
  );
});

test("values are rendered readably and missing values say so", () => {
  assert.equal(describeValue(1434), "1,434");
  assert.equal(describeValue(43.216, "%"), "43.22%");
  assert.equal(describeValue("Needs Attention"), "Needs Attention");
  assert.equal(describeValue(null), "unavailable");
  assert.equal(describeValue(undefined), "unavailable");
});

test("an unknown metric still produces a usable, self-contained question", () => {
  const [option] = buildMetricQuestions(card("something_new", 7, { title: "Something New" }), SCOPE);
  assert.match(option.question, /squad MBK in DCPM/);
  assert.match(option.question, /Something New/);
});

test("the KPI card offers a choice rather than firing one fixed question", () => {
  assert.match(dashboardSource, /function MetricAskMenu/);
  assert.match(dashboardSource, /buildMetricQuestions/);
  assert.match(dashboardSource, /role="menu"/);
  // Escape and an outside click must both dismiss it.
  assert.match(dashboardSource, /event\.key === "Escape"/);
  assert.match(dashboardSource, /metric-ask-scrim/);
  // The old single hardcoded question is gone.
  assert.doesNotMatch(dashboardSource, /suggested_questions\?\.\[0\]/);
});

test("the metric drawer grounds its registry questions before sending", () => {
  assert.match(drawerSource, /groundQuestion\(question/);
  assert.doesNotMatch(drawerSource, /onAsk\(question,/);
});

test("cross-squad options are flagged so they do not inherit one squad's scope", () => {
  // Without this the assistant answers "you're currently viewing MBK; this
  // question requires the All Squads view" and refuses a valid comparison.
  const options = buildMetricQuestions(card("completion_pct", 43.2, { suffix: "%" }), SCOPE);
  const compare = options.find((option) => option.id === "compare");
  assert.equal(compare.crossSquad, true);
  assert.doesNotMatch(compare.question, /squad MBK/);

  for (const status of ["Needs Attention", "Healthy"]) {
    const risk = buildMetricQuestions(card("delivery_risk", status), SCOPE).find((o) => o.id === "compare");
    assert.equal(risk.crossSquad, true, status);
  }
  // Single-squad options must NOT be flagged, or they would lose their scope.
  for (const option of options.filter((o) => o.id !== "compare")) {
    assert.notEqual(option.crossSquad, true, option.id);
  }
  // The card clears the squad only for the flagged ones.
  assert.match(dashboardSource, /option\.crossSquad \? \{ squad: "" \}/);
});
