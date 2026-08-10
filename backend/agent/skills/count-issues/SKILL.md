---
name: count-issues
description: Count Jira issues by type, status, or category. Trigger when user asks "how many issues/bugs/stories/tasks/features are there?"
---

# count-issues

Count Jira issues in the DCPM project snapshot.

## Query to Use

- **Primary:** `jira_dashboard_kpis` — total issues, open work, impeded, missing squad
- **Detail:** `jira_issue_counts_by_status` — breakdown by detailed status
- **By type:** `jira_dashboard_issue_types` — breakdown by issuetype

## Step-by-Step

1. Run `jira_dashboard_kpis` to get totals (total_issues, open_work_count, impeded_issues, missing_squad_count).
2. If user asks "how many bugs/stories/tasks/features", run `jira_dashboard_issue_types`.
3. If user asks "how many by status", run `jira_issue_counts_by_status`.
4. If user asks for a specific type + status combination, run both queries and cross-reference.

## Interpretation Rules

- This is a **snapshot** — counts reflect the current state, not historical trends.
- `Done` category includes Cancelled and Rejected — it is an end-state, NOT successful delivery.
- Total issues (85,223) includes tests, sub-tasks, cancelled items — it is NOT "delivery volume."
- Different issue types represent different kinds of work — never add Bug count + Feature count and call it "work done."
- Missing squad (63,481 rows) means most issues cannot be attributed to a team.

## Response Template

```
[Direct count with number]. This represents [what is being counted] out of [total] total issues in the DCPM snapshot.

Breakdown:
- Type A: X
- Type B: Y
- Type C: Z

Keep in mind: [key caveat about Done ≠ success, or tests/sub-tasks included].

Would you like me to break this down by [status/priority/squad]?
```

## Common Mistakes to Avoid

- ❌ Calling total issue count "delivery volume"
- ❌ Treating Bug + Story + Feature counts as equivalent effort
- ❌ Saying "we completed X issues" when Done includes Cancelled/Rejected
- ❌ Forgetting to mention missing squad impact on team-level counts
