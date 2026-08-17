---
name: data-quality
description: Check Jira data completeness and flag quality issues. Trigger when user asks about "data quality", "missing data", "how clean is the data", "data problems".
---

# data-quality

Run data quality checks on the DCPM Jira issue snapshot.

## Query to Use

- **Primary:** `jira_dashboard_data_quality` — missing squad, missing assignee, done-without-resolved, resolved-before-created, invalid resolution intervals

## Step-by-Step

1. Run `jira_dashboard_data_quality`.
2. Present each quality metric with its count and the impact on reporting.
3. Prioritize the most impactful gaps: missing squad (74.5% of rows) is the biggest.

## Key Quality Metrics

| Metric | Count | Impact |
|---|---|---|
| Missing squad | 63,481 (74.5%) | Squad/team reporting is severely limited |
| Missing progress_pct | 64,874 (76.1%) | Progress tracking from this field is unreliable |
| Missing assignee | 7,763 (9.1%) | Assignment coverage is good but not complete |
| Missing resolved (unresolved) | 9,520 (11.2%) | Expected — unresolved work should have null resolved |
| Done without resolved date | 4 | Inconsistent — should be investigated |
| Resolved before created | 2 | Invalid intervals — exclude from duration calcs |
| Resolved but not Done category | 11 | Status/disagreement — custom workflow behavior |
| Unmatched featurelink_key | 73 | Broken logical references — no FK to enforce |

## Interpretation Rules

- A null value is not always an error. Unresolved issues SHOULD have null `resolved`. Low-priority issues may legitimately lack `root_cause`.
- Missing squad is the single biggest data quality issue — always flag it when presenting team-level analysis.
- The 2 `resolved < created` rows MUST be filtered out before calculating any duration metric.
- JSON columns (fixversions, labels, issuelinks, sprints, subtasks) are non-null wrapper objects — checking `IS NOT NULL` misleadingly suggests data exists. Use `json_array_length(column -> 'inner_key') > 0`.

## Response Template

> Templates below show *what* to report, not a fixed set of sections. Include a
> line only when this request needs it; omit anything the user did not ask for.
> Never end an answer by offering further help or suggesting a follow-up
> question -- the interface has its own follow-up feature.

```
Data quality summary for the DCPM Jira snapshot (85,223 rows):

| Check | Count | % of Total |
|---|---|---|
| Missing squad | 63,481 | 74.5% |
| Missing assignee | 7,763 | 9.1% |
| Missing progress_pct | 64,874 | 76.1% |
| Done without resolved | 4 | <0.01% |
| Resolved before created | 2 | <0.01% |
| Resolved, not Done | 11 | <0.01% |
| Unmatched feature links | 73 | — |

Biggest concern: 74.5% of issues have no squad assigned. Any team-level report MUST acknowledge this gap — you cannot attribute most work to specific teams.

The 2 invalid resolution intervals and 4 inconsistent Done rows should be filtered before calculating metrics. They are small in count but would produce misleading averages if included.
```

## Common Mistakes to Avoid

- ❌ Presenting null `resolved` as a data quality problem (unresolved work should have null resolved)
- ❌ Treating `progress_pct` coverage as a metric when 76% is missing
- ❌ Checking `sprints IS NOT NULL` instead of `json_array_length(sprints -> 'sprints') > 0`
- ❌ Not flagging that missing squad makes team reporting unreliable
