# ECHO role dashboard data capabilities

Verified against the configured local DoraDB on 2026-08-05 using a read-only
transaction. The production dashboard queries the live database; this document
records capability rules rather than snapshot values.

## Authoritative sources

| Relation | Confirmed use |
|---|---|
| `public.tbl_gdt_dte_jira_issues` | One current Jira issue snapshot row per unique `key`; operational dashboard source. |
| `public.mvw_gdt_dte_jira_fixversions` | Expands issue `fixversions` JSON into `id`, `fixversion`. |
| `public.mvw_gdt_dte_jira_sprints` | Expands sprint membership and provides sprint ID/name-derived fields, state, start, and end. |
| `public.tbl_gdt_dte_release_info` | Release/fix-version date and outcome fields, including planned and actual development/UAT/release dates. |
| `public.tbl_gdt_dte_releases` | Release names, date, year, major/official/hide flags. |
| `public.vw_gdt_dte_release_frequency` / `vw_gdt_dte_release_success` | Existing governed organisation-specific release metrics; not inferred from Jira issue counts. |

The Jira table fields used by the dashboard are `key`, `summary`, `issuetype`,
`priority`, `status`, `status_category`, `project_key`, `dcpsquad`, `assignee`,
`created`, `updated`, `resolved`, `fixversions`, `sprints`, `featurelink_key`, and
`resolution`. `progress_pct` exists but has incomplete coverage and an unconfirmed
source rule, so it does not drive primary metrics.

## Supported dashboard metrics

| Metric | Rule | Important limitation |
|---|---|---|
| Total Work | Count distinct issue keys in scope. | Issues are not equal units of effort or value. |
| Active Jira Work | `resolved IS NULL` and `status_category <> 'Done'`. | Local snapshot definition, not sprint commitment. |
| End-state Work / Percentage | `status_category = 'Done'`; percentage over all scoped rows. | Done includes rejected and cancelled outcomes; it is not a success/productivity score. |
| In Progress / To Do | Exact Jira status-category values. | Current state only; no transition history. |
| Open Bugs | `issuetype = 'Bug'`, unresolved, non-Done. | Bug count does not establish impact. |
| High-priority Open Bugs | Open Bugs where `priority = 'High'`. | Priority is not severity. |
| Unassigned Open Work | Active work with null/blank `assignee`. | Queue ownership may be valid. |
| Missing Squad | Null/blank `dcpsquad`. | Missing rows are visible and excluded from named-squad comparisons. |
| Unresolved Age | Calendar days from `created` for unresolved non-Done work. | Not engineering cycle time or DORA Lead Time for Changes. |
| Feature Work Status | Feature issues grouped by status category. | Not committed features. |
| Test Work Status | Test issues grouped by Jira status category. | Not a test execution result or pass rate. |
| Release-linked Work | Issue membership in `fixversions.fixversions`. | Association does not prove deployment. |
| Sprint-linked Work | Issue membership in `sprints.sprints`. | Stored membership is not scope-at-commitment history. |
| Release Dates | Planned/actual dates in `tbl_gdt_dte_release_info`. | Missing dates remain unavailable; no fabricated readiness score. |

## Deterministic attention status

Thresholds live in `backend/dashboard_registry.py` and are returned by the API.
They are configurable constants and must never be described as AI confidence.

- **Needs Attention:** any of High-priority open bugs ≥ 3, oldest unresolved age
  ≥ 90 days, end-state percentage below 50%, or at least one current issue with
  exact status `IMPEDED`.
- **Monitor:** any of High-priority open bugs ≥ 1, oldest unresolved age ≥ 60
  days, end-state percentage below 75%, or unassigned open work ≥ 1.
- **Data Incomplete:** scoped issues have a missing status category required for
  the rule.
- **Healthy:** none of the above rules match.

These are prioritisation aids. They do not prove root cause, business impact,
delivery success, or team performance.

## Unsupported or uncertain capabilities

| Requested metric | Missing required evidence | Dashboard behaviour |
|---|---|---|
| Story-point velocity | Story points and commitment history | Hidden / unsupported. |
| True sprint commitment or rigorous sprint completion | Scope-at-commitment and sprint history | Hidden / unsupported. |
| Test passed, failed, blocked, pass rate, execution recency | Dedicated test execution outcome/date | Use **Test Work Status** only. |
| Due-date compliance | Due date | Hidden / unsupported. |
| Defect severity | Severity field | Use actual Jira priority without renaming it. |
| Capacity utilisation | Capacity and effort | Hidden / unsupported. |
| Historical blocked duration | Flag/status transition history | Only exact current `IMPEDED` status is supported. |
| Historical reopen rate | Status history/changelog | Hidden / unsupported. |
| MTTR | Incident start and restoration evidence | Hidden / unsupported. |
| Official deployment frequency | Deployment events | Do not infer from Jira issues; existing release metrics remain separately governed. |
| Official Change Failure Rate | Deployment failure/incident evidence | Do not infer from Jira bugs; existing `outcome_rating` metric remains organisation-specific. |

## Filter semantics and data quality

- Project uses exact `project_key`; the inspected snapshot currently contains
  only `DCPM`.
- Squad values are trimmed, nonblank, sorted, and validated by a documented
  placeholder rule. Excluded values and reasons are returned by the squad API.
- Release and sprint filters use parameterized comparisons against JSON arrays.
- Date range filters `created::date`; the API returns the field name so the UI
  does not imply a different timestamp.
- Query-controlled sort columns and directions come from allowlists. All user
  values are bound parameters. Page size is capped at 100.
- Database errors return unavailable/error states and never fabricated zeroes.
