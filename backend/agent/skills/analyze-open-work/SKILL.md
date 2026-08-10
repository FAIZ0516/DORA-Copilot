---
name: analyze-open-work
description: Analyze open/unresolved Jira work by type, priority, squad, and age. Trigger when user asks about "open work", "pending", "unresolved", "what's not done".
---

# analyze-open-work

Analyze unresolved Jira issues in the DCPM project.

## Queries to Use

- **Primary:** `jira_open_work_breakdown` — open work by type, priority, squad
- **Supplement:** `jira_dashboard_open_ageing` — how long open work has been sitting
- **Context:** `jira_dashboard_kpis` — open_work_count for the headline number

## Step-by-Step

1. Run `jira_dashboard_kpis` — note the `open_work_count` value.
2. Run `jira_open_work_breakdown` — get the full breakdown.
3. If the user cares about age, run `jira_dashboard_open_ageing`.

## Interpretation Rules

- "Open" means `status_category ≠ 'Done'` and `resolved IS NULL` — this is a local definition, not Jira's official one.
- 63,481 rows (74.5%) have no squad — any team-level open work analysis MUST flag this gap.
- Open ≠ blocked. Blocked issues are a subset (see `check-impeded` skill).
- Calendar age ≠ neglect. Some issues are intentionally long-running or deferred.
- `IMPEDED` is the only clear blocked status, but other waiting statuses may also indicate blockers.

## Response Template

```
There are [X] open issues in the DCPM snapshot — [Y]% of all [Z] total issues.

By type:
- [Type]: [count] ([% of open])

By priority:
- [Priority]: [count]

By age:
- <30 days: [count]
- 30-60 days: [count]
- 61-90 days: [count]
- >90 days: [count]

[Flag: X open issues (Y%) have no squad assigned — team-level analysis is limited.]

The oldest open issue dates from [date]. [Note if any are IMPEDED.]

Would you like me to analyze the blocked issues specifically, or break this down by squad?
```

## Common Mistakes to Avoid

- ❌ Calling all open work "backlog" (backlog has a specific status meaning)
- ❌ Assuming old = neglected without context
- ❌ Presenting squad breakdowns without flagging the 63,481 missing
- ❌ Mixing open work with impeded work as though they're the same
