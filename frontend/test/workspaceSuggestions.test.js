import test from "node:test";
import assert from "node:assert/strict";
import { getSuggestionPrompt, WORKSPACE_SUGGESTIONS } from "../src/workspaceSuggestions.js";

test("business workspace exposes only its four approved cards", () => {
  assert.deepEqual(WORKSPACE_SUGGESTIONS.business.map((item) => item.title), [
    "Work Overview", "Delivery Risks", "Data Quality", "Management Focus",
  ]);
});

test("technical workspace exposes only its four approved cards", () => {
  assert.deepEqual(WORKSPACE_SUGGESTIONS.technical.map((item) => item.title), [
    "Explore Jira Data", "Understand Workflow", "Explore Squads", "Check DORA Metrics",
  ]);
});

test("card selection supplies the full prompt, not its description", () => {
  assert.equal(
    getSuggestionPrompt("technical", 2),
    "List the available squad values in the Jira issues data.",
  );
  assert.notEqual(getSuggestionPrompt("business", 0), WORKSPACE_SUGGESTIONS.business[0].description);
});
