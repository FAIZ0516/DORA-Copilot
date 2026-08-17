---
name: check-impeded
description: Analyze blocked/impeded Jira issues by type, priority, and age. Trigger when user asks about "blocked", "impeded", "stuck", "what's being held up".
---

# check-impeded

Analyze impeded (blocked) Jira issues in the DCPM project.

## Queries to Use

- **Primary:** `jira_impeded_breakdown` — impeded issues by type, priority, age
- **Context:** `jira_dashboard_kpis` — impeded_issues count

## Step-by-Step

1. Run `jira_dashboard_kpis` — note `impeded_issues`.
2. Run `jira_impeded_breakdown` — full breakdown by type, priority, age buckets.

## Interpretation Rules

- `IMPEDED` is the clearest blocked-like status in this dataset, but it may not be the ONLY blocked state. Other waiting statuses (`Deferred`, `Pending for Cancellation`, `Pending Defer Approval`) may also indicate blockers — flag this ambiguity.
- The database has **no status history** — you cannot see how long an issue has been impeded, only that it currently IS impeded.
- `Deferred` remains in `In Progress` category per stored data — do not reclassify it silently.
- No blocker-reason field exists — you cannot say WHY issues are blocked, only THAT they are.

## Response Template

> Templates below show *what* to report, not a fixed set of sections. Include a
> line only when this request needs it; omit anything the user did not ask for.
> Never end an answer by offering further help or suggesting a follow-up
> question -- the interface has its own follow-up feature.

```
There are [X] impeded issues in the DCPM snapshot — [Y]% of all open work.

By type:
- [Type]: [count]

By priority:
- [Priority]: [count]

By age:
- <30 days: [count]
- 30-60 days: [count]
- 61-90 days: [count]
- >90 days: [count]

Important: IMPEDED is the clearest blocked status, but other waiting states (Deferred, Pending for Cancellation) may also indicate blockers. The database shows only current status — I cannot see how long these issues have been blocked or why.
```

## Common Mistakes to Avoid

- ❌ Claiming you know WHY issues are blocked (no blocker-reason column exists)
- ❌ Assuming IMPEDED is the only blocked state
- ❌ Claiming you know how long issues have been blocked (no status history)
- ❌ Treating impeded count alone as a delivery health metric without context
