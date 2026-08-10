#!/usr/bin/env python
"""Agent evaluation harness (guide Section 46).

Tests prove code correctness; this measures AI *behavior* quality against a
stable, representative question set (``evaluation_cases.yaml``) -- whether
the deterministic planner assigns the intent/query a human would expect.
It intentionally evaluates structural properties (intent classification,
selected query, safety routing), never exact wording, per the guide's
explicit instruction not to evaluate only exact wording.

This runs against the *deterministic* fallback path only (no live LLM
credentials required), because that path is what the app falls back to
whenever the configured provider is unavailable, and it is what makes
in-scope/out-of-scope/discovery routing decisions testable without network
access. Cases whose expected outcome depends on multi-turn conversation
memory ("follow_up") cannot be evaluated statelessly and are reported as
skipped, not failed.

Usage:
    .venv/Scripts/python.exe evals/run_evals.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agent.planner import deterministic_plan  # noqa: E402
from backend.services import classify_intent  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "evaluation_cases.yaml"

# classify_intent()'s vocabulary doesn't have a "follow_up" or
# "clarification" outcome of its own -- those are planner-level modes.
# This maps the dataset's expected `intent` label to how we check it.
_NO_QUERY_INTENTS = {"clarification", "help", "out_of_scope"}
_UNVERIFIABLE_INTENTS = {"follow_up"}  # requires conversation memory


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def evaluate_case(case: dict) -> tuple[str, str]:
    """Return (status, detail). status is one of pass/fail/skip."""

    question = case["question"]
    expected_intent = case["intent"]
    expected_query = case.get("query")

    if expected_intent in _UNVERIFIABLE_INTENTS:
        return "skip", "requires conversation memory (multi-turn only)"

    plan = deterministic_plan(question, {"turns": [], "last_context": {}})

    if expected_intent == "out_of_scope":
        if plan["mode"] == "out_of_scope":
            return "pass", ""
        return "fail", f"expected out_of_scope, got mode={plan['mode']!r}"

    if expected_intent in {"clarification", "help"}:
        if plan["mode"] in {"clarification", "conversation"}:
            return "pass", ""
        return "fail", f"expected {expected_intent}, got mode={plan['mode']!r}"

    actual_query = plan["actions"][0]["query_id"] if plan["actions"] else None
    intent = classify_intent(question)
    intent_ok = intent["name"] == expected_intent or plan["intent"] == expected_intent
    query_ok = expected_query is None or actual_query == expected_query

    if intent_ok and query_ok:
        return "pass", ""
    return (
        "fail",
        f"expected intent={expected_intent!r} query={expected_query!r}, "
        f"got classify_intent={intent['name']!r} plan_intent={plan['intent']!r} "
        f"query={actual_query!r} mode={plan['mode']!r}",
    )


def main() -> int:
    cases = load_cases()
    counts = {"pass": 0, "fail": 0, "skip": 0}
    failures: list[str] = []

    for case in cases:
        status, detail = evaluate_case(case)
        counts[status] += 1
        # ASCII-only: Windows consoles default to a codepage that can't
        # encode Unicode check/cross marks and raises UnicodeEncodeError.
        marker = {"pass": "OK", "fail": "XX", "skip": "--"}[status]
        print(f"{marker} [{status:4}] {case['question']}")
        if status == "fail":
            print(f"         {detail}")
            failures.append(case["question"])

    total = sum(counts.values())
    print(
        f"\n{counts['pass']}/{total} passed, {counts['fail']} failed, "
        f"{counts['skip']} skipped (unverifiable without conversation state)"
    )
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
