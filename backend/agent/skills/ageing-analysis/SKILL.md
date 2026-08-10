---
name: ageing-analysis
description: Analyze how long open issues have been unresolved, grouped by age buckets. Trigger when user asks about "old issues", "ageing", "stale work", "how long has this been open".
---

# ageing-analysis

Analyze the age distribution of unresolved Jira issues.

## Query to Use

- **Primary:** `jira_dashboard_open_ageing` — open issues grouped by age bucket (<30, 30-60, 61-90, >90 days)

## Step-by-Step

1. Run `jira_dashboard_open_ageing`.
2. Note the distribution across the 4 age buckets.
3. If user asks about a specific bucket, focus there.

## Interpretation Rules

- Calendar age is measured from `created` date to now — it is **not** cycle time, not DORA lead time, not time-in-status.
- Timestamps are `timestamp without time zone` — the exact timezone is unknown, so age buckets are approximate.
- Old ≠ neglected. Some issues may be intentionally long-running (epics, long-term features) or deferred by design.
- Old + `IMPEDED` is a stronger signal of a problem than old alone.
- Issues can age without being worked on, or age while actively being worked on — the snapshot cannot distinguish these.

## Response Template

```
Open issues by calendar age in the DCPM snapshot:

| Age Bucket | Count | % of Open |
|---|---|---|
| <30 days | X | Y% |
| 30-60 days | X | Y% |
| 61-90 days | X | Y% |
| >90 days | X | Y% |

[X] issues have been open for more than 90 days. Of these, [Y] are currently IMPEDED.

Important: Calendar age measures time since creation, not time spent actively working. Some long-running issues may be epics or features with extended timelines. This is not the same as DORA lead time or cycle time.

Would you like me to break down the oldest issues by type or priority?
```

## Common Mistakes to Avoid

- ❌ Calling calendar age "cycle time" or "lead time"
- ❌ Claiming old issues are neglected without checking priority and type
- ❌ Forgetting to mention timezone is unknown
- ❌ Presenting age as a negative metric without context about the issue type
