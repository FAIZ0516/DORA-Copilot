---
name: find-squad
description: List squads with Jira data and their issue counts. Trigger when user asks "which squads exist", "squad list", "teams with data".
---

# find-squad

Discover which squads have Jira data in the DCPM project.

## Queries to Use

- **Primary:** `jira_distinct_squads` — list all squads with issue counts
- **Supplement:** `database_squad_sources` — find all data sources that contain squad information

## Step-by-Step

1. Run `jira_distinct_squads` to get the squad list with counts.
2. **FIRST THING: state that 74.5% of issues have no squad.**

## Interpretation Rules

- 21 non-null squad values exist in the snapshot. 63,481 rows have no squad.
- `dcpsquad` is a project-specific custom field. Whether it means current ownership, historical ownership, or extraction-time mapping **Needs confirmation**.
- Squad name alone does not indicate team size, capacity, or responsibility scope.
- A squad with more issues is not necessarily "busier" — issue type mix, complexity, and team size all affect the count.

## Response Template

> Templates below show *what* to report, not a fixed set of sections. Include a
> line only when this request needs it; omit anything the user did not ask for.
> Never end an answer by offering further help or suggesting a follow-up
> question -- the interface has its own follow-up feature.

```
Squads with Jira data in the DCPM project:

| Squad | Issue Count | % of Assigned |
|---|---|---|
| [name] | X | Y% |

21 squads have data. 63,481 issues (74.5%) have NO squad assigned — the majority of work cannot be attributed to any specific team.

Important: Squad is a custom Jira field. Whether it reflects current or historical ownership is unconfirmed. Issue count does not measure team size, effort, or productivity.
```

## Common Mistakes to Avoid

- ❌ Not leading with the 74.5% missing squad statistic
- ❌ Ranking squads by issue count as though it measures productivity
- ❌ Assuming squad assignment means current ownership
