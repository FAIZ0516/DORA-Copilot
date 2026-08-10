---
name: safe-reporting
description: Compose safe, responsible reports from Jira data. Trigger when user asks to "build a report", "summarize", "create a summary for leadership", "give me an overview".
---

# safe-reporting

Build safe, responsible reports from DCPM Jira data.

## Knowledge Source

Reference `backend/knowledge/jira_issues.md` — specifically:
- Section 15 (Instructions for AI Assistants) — all 30 rules
- Section 12 (How This Table Can Be Used for Reporting)

## The 30 AI Rules — Condensed Checklist

### Schema & Query Rules
1. Use `public.tbl_gdt_dte_jira_issues` with exact column names
2. PostgreSQL is the database dialect
3. Read-only SELECT only — never suggest data changes
4. Distinguish schema facts, data facts, interpretations, and recommendations
5. Never invent story points, descriptions, due dates, severity, status history, deployments, commits, incidents, or business rules

### Data Presentation Rules
6. Use `key` for issue references, `id` for technical joins only
7. State analysis date range, every important filter, project, type, status, resolution, null handling
8. Only project DCPM exists — no multi-project claims
9. Treat status values as customised — use stored `status_category` mapping
10. Done = end-state, not success — always clarify

### Metric & Calculation Rules
11. Story points are absent — do not substitute anything for them
12. `progress_pct` ≠ story points, time spent, or effort — most values are null
13. `resolved - created` = calendar issue resolution duration, NOT cycle time or DORA lead time
14. Check nulls and invalid intervals before calculating metrics
15. Use `COUNT(DISTINCT id)` after expanding JSON or joining views

### Data Quality Rules
16. Test inner JSON array length, not just column nullability
17. Check materialized view freshness
18. Treat logical links as logical (no FK enforcement)
19. Check unmatched feature links — don't invent missing parents
20. Timestamps are timezone-unknown

### Privacy & Safety Rules
21. Distinguish Jira `updated` from warehouse `superset_updated_ts`
22. NEVER expose summary, reporter, assignee, root_cause, how_to_fix, labels, release/squad names unless authorized
23. Aggregate or anonymise personal data — never rank individuals
24. Issue count ≠ team productivity — issue type ≠ equal effort
25. Correlation ≠ causation

### Judgment Rules
26. Do not label a person or team as underperforming
27. Clearly state when additional data sources are needed
28. Treat organisation-specific metrics as organisation-specific
29. Ask for clarification when terms are ambiguous
30. Recommendations are suggestions, not confirmed root causes

## Response Template for Reports

```
## [Report Title]
**Scope:** DCPM project | **Date:** [snapshot date] | **Filters:** [list all filters]

### Key Findings
1. [Finding with supporting number]
2. [Finding with supporting number]
3. [Finding with supporting number]

### Detailed Breakdown
[Present data with context and limitations]

### Data Quality Notes
- [Flag any relevant quality issues: missing squad, nulls, invalid intervals]
- [Note any applied filters or exclusions]

### Limitations
- This is a snapshot, not historical trend data
- [Other relevant limitations from the explain-limitations skill]
- These are delivery indicators, NOT official DORA metrics

### Possible Next Questions
- [Question 1]
- [Question 2]
```

## Common Mistakes to Avoid

- ❌ Building a report without stating scope, date, and filters
- ❌ Including personal data (names, summaries, root_cause text)
- ❌ Ranking squads or individuals
- ❌ Presenting organisation-specific metrics as standard DORA
- ❌ Making recommendations sound like proven root causes
- ❌ Omitting data quality caveats
- ❌ Exceeding 550 words without user requesting detail
