---
name: dora-vs-jira
description: Clarify the difference between Jira-based delivery indicators and official DORA metrics. Trigger when user asks "is this DORA", "are these official metrics", "DORA vs Jira".
---

# dora-vs-jira

Clarify what is and isn't DORA in the DCPM project data.

## Knowledge Source

Reference `backend/knowledge/jira_issues.md` — specifically:
- Section 13 (Relationship to DORA Metrics)
- Section 12 (How This Table Can Be Used for Reporting)

## The Core Distinction

**Jira issue data** → can provide delivery context and indicators
**DORA metrics** → require deployment events, CI/CD data, production incidents

This project has both Jira data AND release tables. But the release metrics are **organisation-specific** — their business definitions are not confirmed as standard DORA.

## What Each DORA Metric Actually Requires

| Official DORA Metric | What It Needs | What This Project Has |
|---|---|---|
| **Deployment Frequency** | CI/CD deployment events with environment, service, result, timestamps | Release tables + `vw_gdt_dte_release_frequency` (org-specific, needs confirmation) |
| **Lead Time for Changes** | Commit/merge event → production deployment timestamp | `resolved - created` (issue resolution duration, NOT lead time) |
| **Change Failure Rate** | Production deployment → incident/failure link, rollback/redeploy events | `cfr_by_year`, `outcome_rating`, `redeploy` (org-specific, needs confirmation) |
| **Failed Deployment Recovery** | Incident start → verified recovery time | Not available in this project |

## What Jira Data CAN Provide (Delivery Indicators)

These are useful but are NOT DORA metrics:
- Current work by status category
- Issue arrivals and resolved-issue counts over time
- Calendar age of unresolved work
- Calendar issue resolution duration
- Current IMPEDED or Reopened issue counts
- Bugs created/resolved over time
- Feature/user-story counts associated with fix versions
- Missing squad, assignment, release, and sprint coverage

## Response Template

```
The metrics in this project use organisation-specific definitions — they are NOT official DORA metrics as defined by the DORA research program.

**What official DORA requires** (and this project doesn't have):
- Deployment Frequency → CI/CD deployment events with environment and timestamps
- Lead Time → commit-to-deploy tracking, not issue resolution duration
- Change Failure Rate → production incident data linked to specific deployments
- Recovery Time → incident start and recovery timestamps

**What this project CAN show** (delivery indicators, not DORA):
- Release patterns and issue resolution trends
- Current work distribution by status, type, and age
- Squad-level delivery patterns (for the 25% with squad data)
- Bug creation and resolution rates over time

These indicators are useful for asking questions, but they don't prove delivery performance by themselves.

Would you like me to show the available delivery indicators?
```

## Common Mistakes to Avoid

- ❌ Letting the user believe project metrics are standard DORA
- ❌ Calling `resolved - created` lead time in any context
- ❌ Presenting release frequency as deployment frequency
- ❌ Not explaining WHY the distinction matters
