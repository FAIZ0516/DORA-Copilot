---
name: backlog-status
description: Analyze the Jira backlog composition by status. Trigger when user asks about "backlog", "backlog health", "what's in the backlog".
---

# backlog-status

Analyze Jira backlog composition in the DCPM project.

## Query to Use

- **Primary:** `jira_backlog_by_status` — issues grouped by status within the backlog

## Step-by-Step

1. Run `jira_backlog_by_status` to see the status distribution of backlog items.
2. Identify which statuses dominate the backlog.

## Interpretation Rules

- "Backlog" typically means `status_category = 'To Do'` or specific `To Do` statuses like `New`, `Grooming`, `Ready 4 Development`.
- The database contains no sprint commitment history — you cannot distinguish "planned for this sprint" from "general backlog."
- Issues in `Grooming` or `Ready 4 Development` are closer to being actionable than bare `To Do` or `New` items.
- `To Do` statuses observed: `To Do`, `New`, `Ready 4 Development`, `Grooming`.

## Response Template

```
The DCPM backlog contains [X] issues in To Do status category.

Breakdown by status:
- [Status]: [count] ([%])
- [Status]: [count] ([%])

[X] issues are in actionable states (Ready 4 Development, Grooming), while [Y] are in New/To Do with no further detail.

Note: This is a current snapshot. I cannot show sprint commitment history or how long items have been in the backlog. Backlog size alone does not indicate health — it depends on team capacity, priorities, and whether items are actively groomed.

Would you like me to break the backlog down by issue type or check for aged items?
```

## Common Mistakes to Avoid

- ❌ Calling the entire backlog "unplanned work"
- ❌ Equating backlog size with delivery problems
- ❌ Claiming items are "forgotten" without checking if they're actively groomed
- ❌ Not distinguishing between raw `To Do`/`New` and groomed `Ready 4 Development` items
