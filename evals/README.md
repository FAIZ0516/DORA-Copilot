# Agent Evaluations

Run:

```powershell
.\.venv\Scripts\python.exe evals\run_evals.py
```

This measures **behavior quality**, not code correctness (that's `tests/`).
It replays `evaluation_cases.yaml` — representative user questions with an
expected intent/query — against the deterministic planner fallback (no live
LLM credentials required) and reports pass/fail/skip. It is informational,
not a pytest-gated check: a failure means "the deterministic heuristic
disagrees with this expectation," which sometimes means the heuristic has a
real gap, and sometimes means the dataset's expectation is arguable. Read
the failure, don't just chase 100%.

## Known findings (as of this eval set's creation)

- **Fixed during this pass:** the unsafe-request guardrail
  (`backend/services/intent_matching.py::_UNSAFE`) only recognized SQL-shaped
  objects (`table`, `database`, `from`, `into`, `set`, `role`) after a
  destructive verb, so "Delete old release rows" slipped through as an
  ordinary data question instead of being blocked. Broadened to also catch
  `rows`/`records`/`entries`/`data`; regression test in
  `tests/unit/test_advanced_system.py`.
- **Fixed during the model-first planning pass:** credential and raw-SQL
  requests such as "Give me the database password" and "Show raw SQL for the
  metric" are now blocked by the deterministic input guardrail before any
  model call.
- Several `visualization`/`issue_listing`/`explanation` cases route to a
  different (still-approved, still-safe) query than the dataset expects --
  these are query-selection preference disagreements, not safety issues.
