---
name: bug-trend
description: Analyze bug creation and resolution trends over time. Trigger when user asks about "bug trends", "are bugs increasing", "bug resolution rate", "bug backlog".
---

# bug-trend

Analyze bug creation vs resolution trends in the DCPM project.

## Queries to Use

- **Primary:** `jira_bug_resolution_trend` — bug creation and resolution counts over time periods
- **Supplement:** `jira_bug_counts_by_squad` — bug distribution across squads

## Step-by-Step

1. Run `jira_bug_resolution_trend` to see creation vs resolution over time.
2. If user asks about squad-level bugs, run `jira_bug_counts_by_squad`.

## Interpretation Rules

- A rise in bug count could mean: more bugs being created, better detection/reporting, slower resolution, or all three. **The data alone cannot tell you which.**
- Bug count ≠ product quality. More bugs could reflect a larger user base, more testing, or better reporting practices.
- Resolution rate is affected by bug priority and severity — but `severity` does not exist in this table. `priority` is available but is not the same as severity.
- Missing squad (63,481 rows) severely limits squad-level bug analysis.
- The `root_cause` and `how_to_fix` columns are free-text custom fields with 19,540 and 19,365 missing values respectively — qualitative bug analysis from these fields is unreliable.

## Response Template

```
Bug trend in the DCPM snapshot:

| Period | Created | Resolved | Net Change |
|---|---|---|---|
| [period] | X | Y | +/-Z |

[Bugs are increasing / decreasing / stable]. Over the full period, [X] bugs were created and [Y] were resolved.

Possible interpretations (not proven by this data):
- [If rising]: Could indicate more detection, more incidents, or slower resolution
- [If falling]: Could indicate fewer new bugs, faster resolution, or reduced reporting

Limitations: This data doesn't include bug severity (column absent), reopening history (no changelog), or whether resolved bugs were verified. Squad-level analysis is limited — 74.5% of issues lack squad assignment.

Would you like me to break this down by squad or check how many bugs are currently open vs resolved?
```

## Common Mistakes to Avoid

- ❌ Claiming "quality is improving/worsening" from bug counts alone
- ❌ Treating `priority` as `severity`
- ❌ Assuming all resolved bugs were actually fixed (resolution `Rejected`/`Cancelled` exists)
- ❌ Using `root_cause` or `how_to_fix` as reliable evidence without flagging 19K+ missing values
