---
name: explain-limitations
description: Explain what the Jira data CANNOT tell you — known gaps, missing data, and fundamental limitations. Trigger when user asks "what can't this data tell me", "limitations", "what's missing".
---

# explain-limitations

Explain the known limitations of the DCPM Jira issue snapshot.

## Knowledge Source

Reference `backend/knowledge/jira_issues.md` — specifically:
- Section 17 (Known Limitations and Open Questions)
- Section 12 (How This Table Can Be Used for Reporting)
- Section 13 (Relationship to DORA Metrics)

## Confirmed Limitations (Cannot Be Changed)

| Limitation | Impact |
|---|---|
| **Snapshot only — no history** | Cannot see status transitions, reopen history, or field changes over time |
| **Single project (DCPM)** | No cross-project comparison possible |
| **No story points** | Cannot estimate effort or do velocity reporting |
| **No due dates** | Cannot report on overdue or on-time delivery |
| **No descriptions** | Cannot analyze issue content or requirements |
| **No status changelog** | Cannot calculate time-in-status or cycle time |
| **No timezone on timestamps** | Date-based calculations are approximate |
| **No FK enforcement** | Relationships are logical, not guaranteed |
| **74.5% missing squad** | Team-level reporting covers only ~25% of issues |
| **76.1% missing progress_pct** | Progress field is unreliable for reporting |
| **JSON inner arrays** | Expansion creates duplicates — must use COUNT(DISTINCT id) |
| **Materialized views may be stale** | Expanded data may not match current base table |

## What This Data CANNOT Calculate

- ❌ Official DORA metrics (needs CI/CD, deployment, incident data)
- ❌ Cycle time (needs status transition history)
- ❌ Sprint completion rate (needs sprint commitment history)
- ❌ Team velocity (needs story points, sprint history)
- ❌ Developer productivity (inherently not measurable from issue counts)
- ❌ Time-to-resolve by assignee (needs assignment history)
- ❌ Reopen rate (needs status changelog)
- ❌ Root cause trends (root_cause has 19,540 missing, meaning unconfirmed)

## Open Questions (Needs Confirmation)

- What timezone applies to Jira and warehouse timestamps?
- How frequently is the snapshot refreshed?
- What exact Jira field produces `progress_pct`?
- Is `dcpsquad` current or historical ownership?
- Which issue types should have `root_cause` and `how_to_fix`?
- What are the approved business meanings of Done, Closed, Fixed, Deferred, IMPEDED?
- Do release records represent production deployments or planning events?
- What explains the 73 unmatched feature links and 2 negative resolution intervals?

## Response Template

> Templates below show *what* to report, not a fixed set of sections. Include a
> line only when this request needs it; omit anything the user did not ask for.
> Never end an answer by offering further help or suggesting a follow-up
> question -- the interface has its own follow-up feature.

```
The DCPM Jira snapshot has several important limitations:

**Fundamental:**
- This is a point-in-time snapshot — no status history, no field changes over time
- Single project (DCPM) — no cross-project comparison
- No story points, due dates, descriptions, or timezone metadata

**Data Coverage:**
- 74.5% of issues have no squad — team reporting covers only 25%
- 76.1% have no progress_pct — progress tracking is unreliable

**What this data CANNOT do:**
- Calculate official DORA metrics (requires deployment/CI-CD data)
- Measure cycle time (requires status transition history)
- Assess team or individual productivity

For any analysis, I will state these limitations when they affect the results. Is there a specific area you'd like me to explore despite these constraints?
```

## Common Mistakes to Avoid

- ❌ Saying "the data can't do X" without offering what it CAN do
- ❌ Presenting limitations as excuses rather than transparency
- ❌ Forgetting to mention the biggest gaps (squad, progress_pct)
