---
name: dora-release-detail
description: Show per-release DORA metric details. Trigger when user asks about "release details", "per-release metrics", "how did release X perform".
---

# dora-release-detail

Present per-release DORA metric details for the DCPM project.

## Query to Use

- **Primary:** `dora_metrics_release_detail` — per-release breakdown of DORA metrics

## Step-by-Step

1. Run `dora_metrics_release_detail`.
2. Present key metrics per release.
3. Note the relationship between Jira fix versions and releases.

## Interpretation Rules

- Fix version association (via `fixversions` JSON and `mvw_gdt_dte_jira_fixversions`) does NOT prove production deployment. An issue linked to a release may not have been deployed.
- Release records come from `tbl_gdt_dte_releases` and `tbl_gdt_dte_release_info`. The columns `outcome_rating`, `release_category`, and `redeploy` have business meanings that **Need confirmation**.
- `release_info` contains 30 rows vs 67 release names — not all releases have detailed info.
- No foreign keys enforce the fix-version-to-release relationship. Naming consistency is what ties them together.
- The `_dev` variant tables exist but should not be mixed with production reporting.

## Response Template

```
Per-release metrics for DCPM:

| Release | Date | Issues | Lead Time | CFR |
|---|---|---|---|---|
| [name] | [date] | X | Y mo | Z% |

[X] releases found. [Y] have detailed release info records.

Important: Fix version association with an issue does not prove it was deployed to production. Release metrics use project-specific definitions — they are NOT official DORA.

Would you like me to analyze a specific release's issue composition?
```

## Common Mistakes to Avoid

- ❌ Treating fix-version association as confirmed deployment
- ❌ Mixing `_dev` release data with production reporting
- ❌ Assuming all releases are production deployments
- ❌ Not flagging that some releases lack detailed info records
