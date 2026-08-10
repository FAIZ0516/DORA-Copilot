---
name: dora-overview
description: Present DORA delivery metrics overview by year. Trigger when user asks about "DORA metrics", "delivery performance", "release frequency", "lead time", "change failure rate".
---

# dora-overview

Present DORA delivery performance metrics for the DCPM project.

## Query to Use

- **Primary:** `dora_metrics_by_year` — all 4 DORA metrics by release year

## Step-by-Step

1. Run `dora_metrics_by_year`.
2. Present all 4 metrics with their values per year.
3. Label EVERY metric as organisation-specific — the business definitions are not confirmed as standard DORA.

## The 4 Metrics (as defined in this project)

| Metric | What It Measures | Column |
|---|---|---|
| Release Frequency | How often releases occur | `release_frequency_months` |
| Lead Time for Change | Time from code start to production | `lead_time_for_change_months` |
| Change Failure Rate | Percentage of changes that fail | `change_failure_rate_pct` |
| Delivery Cycle Time | Time from work start to delivery | `delivery_cycle_time_months` |

## Interpretation Rules

- **CRITICAL: These are organisation-specific metrics.** Backend metadata explicitly labels them as such. Their business definitions (what counts as a "release", "deployment", "failure") are **Needs confirmation**.
- **These are NOT official DORA metrics** as defined by the DORA research program. Official DORA requires deployment events, CI/CD data, production incidents, and confirmed linking rules — none of which are in the Jira table.
- Calendar year comparisons: the current year is incomplete. State this limitation when comparing.
- Never call an earlier completed year "year-to-date", "so far", or "partial" merely because it has fewer rows.
- Jira issue data alone cannot calculate DORA metrics. The release tables (`tbl_gdt_dte_releases`, `tbl_gdt_dte_release_info`) provide additional data, but their definitions for `outcome_rating`, `release_category`, `success_rel_freq`, `cfr_by_year`, `ltc`, and `redeploy` all **Need confirmation**.

## Response Template

```
DORA-style delivery metrics for the DCPM project (organisation-specific definitions):

| Year | Release Frequency | Lead Time | Change Failure Rate | Cycle Time |
|---|---|---|---|---|
| [year] | X/mo | Y mo | Z% | W mo |

[Current year] is incomplete — comparisons with earlier full years should note this limitation.

Important: These metrics use project-specific definitions and data sources. They are NOT official DORA metrics. The underlying data comes from project release tables and Jira issue snapshots — not from CI/CD deployment events, production incidents, or commit-to-deploy tracking. Deployment frequency, lead time for changes, change failure rate, and recovery time as defined by the DORA research program require additional data sources this project does not contain.

Would you like me to break these down by squad or look at a specific year in detail?
```

## Common Mistakes to Avoid

- ❌ Calling these "official DORA metrics" or "standard DORA"
- ❌ Comparing current incomplete year to completed years without flagging the incompleteness
- ❌ Implying that release frequency = deployment frequency
- ❌ Equating calendar issue resolution duration with DORA lead time
- ❌ Presenting `change_failure_rate_pct` without explaining it's from release tables, not production incidents
