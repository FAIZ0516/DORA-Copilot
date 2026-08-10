---
name: explore-schema
description: Explore the DoraDB database schema — list tables, views, columns. Trigger when user asks "what tables exist", "show database structure", "what's in the database".
---

# explore-schema

Explore the DoraDB database schema for the DCPM project.

## Queries to Use

- **Primary:** `database_schema_objects` — list all visible tables and views
- **Detail:** `database_columns` — list columns for a specific table
- **Table check:** `database_table_presence` — verify a table exists
- **Metrics:** `database_metric_columns` — find metric-related columns
- **Squads:** `database_squad_sources` — find squad-related data sources

## Step-by-Step

1. If user asks "what tables exist", run `database_schema_objects`.
2. If user asks about a specific table's columns, run `database_columns` with `table_name = '[name]'`.
3. If user asks if a table exists, run `database_table_presence`.

## Key Tables & Views

### Main Jira Table
- `public.tbl_gdt_dte_jira_issues` — 85,223 rows, 26 columns. The primary data source.

### Materialized Views (expanded JSON arrays, may be stale)
- `mvw_gdt_dte_jira_fixversions` — expanded fix version associations
- `mvw_gdt_dte_jira_fuslist` — feature/user story connections
- `mvw_gdt_dte_jira_issuelinks` — expanded issue links
- `mvw_gdt_dte_jira_labels` — expanded labels
- `mvw_gdt_dte_jira_sprints` — expanded sprint memberships
- `mvw_gdt_dte_jira_subtasks` — expanded sub-task references

### Release Tables
- `tbl_gdt_dte_releases` — 67 release names
- `tbl_gdt_dte_release_info` — 30 release detail records
- `tbl_gdt_dte_release_info_dev` — 37 development variant records

### Other
- `tbl_gdt_dte_excluded_issues` — 0 rows currently, exclusion list
- `tbl_gdt_dte_fixversionmap` — 2,125 fix-version grouping mappings

## Interpretation Rules

- Tables with the same name exist in `public`, `enp`, and `tmpdump` schemas. The application uses `public`. Always include the schema name.
- Materialized views are stored query results — they may be stale between refreshes. Row counts from views may exceed base table counts because one issue can have multiple labels, links, sprints, versions, or sub-tasks.
- No foreign keys enforce relationships between these tables. All relationships are logical, established by view SQL and approved application queries.
- The `_dev` variants should not be mixed with production reporting.

## Response Template

```
The DoraDB database contains:

**Tables:**
- [table name] — [brief purpose] ([X] rows)

**Materialized Views:**
- [view name] — [brief purpose] ([X] rows, may be stale)

All tables are in the `public` schema. Logical relationships exist between tables but are not enforced by foreign keys — they rely on naming conventions and approved query logic.

Would you like me to show the columns for any specific table?
```
