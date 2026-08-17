---
name: dora-by-squad
description: Break down DORA metrics by squad/team. Trigger when user asks about "squad performance", "team DORA metrics", "which team is performing best".
---

# dora-by-squad

Present DORA metrics broken down by squad for the DCPM project.

## Query to Use

- **Primary:** `dora_metrics_by_squad` — all 4 DORA metrics per squad

## Step-by-Step

1. Run `dora_metrics_by_squad`.
2. Present metrics per squad.
3. **FIRST THING: flag the 74.5% missing squad gap.** Most issues have no squad — squad-level analysis covers only ~25% of the data.

## Interpretation Rules

- **63,481 rows (74.5%) have no squad.** Squad-level DORA metrics cover only ~25% of all issues. The majority of work is unaccounted for in any squad breakdown.
- **Never rank squads** or imply one squad is "better" than another. Metrics vary by squad scope, issue mix, team size, and responsibilities.
- Squads may own different types of work — a squad focused on bugs will have different metrics than one focused on features.
- Missing squad assignment may correlate with certain issue types or statuses — check before drawing conclusions.
- All organisation-specific metric caveats from `dora-overview` skill apply here too.

## Response Template

> Templates below show *what* to report, not a fixed set of sections. Include a
> line only when this request needs it; omit anything the user did not ask for.
> Never end an answer by offering further help or suggesting a follow-up
> question -- the interface has its own follow-up feature.

```
DORA-style metrics by squad in the DCPM project:

| Squad | Release Freq | Lead Time | CFR | Cycle Time |
|---|---|---|---|---|
| [name] | X/mo | Y mo | Z% | W mo |

⚠️ Critical: 74.5% of all issues (63,481 rows) have NO squad assigned. These metrics represent only the ~25% of work with squad mappings. The patterns seen here may not reflect the full project.

These are organisation-specific metrics — not official DORA. Different squads may handle different issue types and scopes, so direct comparison is not meaningful.
```

## Common Mistakes to Avoid

- ❌ Presenting squad rankings or leaderboards
- ❌ Not leading with the 74.5% missing squad caveat
- ❌ Comparing squads without noting they may handle different work types
- ❌ Implying a squad with slower metrics is "underperforming"
