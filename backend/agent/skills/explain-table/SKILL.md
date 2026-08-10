---
name: explain-table
description: Explain the Jira issues table structure — columns, types, relationships, and commonly confused fields. Trigger when user asks "what columns exist", "what does this table have", "explain the table structure".
---

# explain-table

Explain the structure of `public.tbl_gdt_dte_jira_issues`.

## Knowledge Source

Reference `backend/knowledge/jira_issues.md` — specifically:
- Section 6 (Data Dictionary) for all 26 columns
- Section 7 (Commonly Confused Columns) for field distinctions
- Section 9 (Related Tables) for relationships

## Step-by-Step

1. Ask the user: "Are you looking for a specific column, or do you want an overview of all 26 columns?"
2. If overview: group columns by category (Identifiers, Classification, Ownership, Dates, JSON relationships, Custom text).
3. If specific column: explain type, nullability, business meaning, common mistakes, and which queries use it.

## Column Categories

### Identifiers (2)
- `id` (bigint, PK) — Numeric internal ID. Use for joins only.
- `key` (varchar(20), UNIQUE) — Human-facing Jira key (DCPM-XXXX). Use for reports.

### Classification & Workflow (7)
- `issuetype` — Bug, Story, Task, Feature, Test, Sub-task
- `status` — 29 custom workflow states
- `status_category` — To Do, In Progress, Done
- `priority` — High, Medium, Low (NOT severity)
- `resolution` — Done, Rejected, Cancelled (how it ended)
- `progress_pct` — 0-100, 76% missing (NOT story points)
- `summary` — Issue title (SENSITIVE — do not expose)

### Project, Team & People (5)
- `project_key` — Always "DCPM" in this snapshot
- `project_name` — "DCPM - Digital Channel Platform"
- `dcpsquad` — Squad/team (74.5% missing)
- `reporter` — Who reported it (PII)
- `assignee` — Who owns it (PII)

### Dates (4)
- `created` — Issue creation time (timezone unknown)
- `updated` — Last Jira update (NOT a status transition time)
- `resolved` — Resolution time (timezone unknown)
- `superset_updated_ts` — Warehouse refresh time (NOT a Jira timestamp)

### JSON Relationships (5)
- `fixversions` — Release associations (41,384 populated)
- `labels` — Free-text tags (40,585 populated)
- `issuelinks` — Issue-to-issue links (50,604 populated)
- `sprints` — Sprint membership (38,387 populated)
- `subtasks` — Child issues (8,540 populated)

### Custom Text (2)
- `root_cause` — Free text, 19,540 missing (SENSITIVE)
- `how_to_fix` — Free text, 19,365 missing (SENSITIVE)

## Commonly Confused Pairs

| Column A | Column B | Key Difference |
|---|---|---|
| `id` | `key` | id = internal number, key = human-readable DCPM-XXXX |
| `status` | `status_category` | status = detailed (29 values), category = broad (3 values) |
| `status` | `resolution` | status = where it is now, resolution = how it ended |
| `created` | `updated` | created = when made, updated = last change (NOT a transition) |
| `updated` | `superset_updated_ts` | updated = from Jira, superset = warehouse refresh time |
| `priority` | severity | priority exists, severity DOES NOT EXIST |
| `progress_pct` | story points | progress_pct = percentage, story points DO NOT EXIST |

## Important: What DOES NOT Exist

- ❌ Story points, time estimates, due dates
- ❌ Descriptions, comments, attachments
- ❌ Status transition history / changelog
- ❌ Severity, components, boards
- ❌ Parent issue ID (featurelink_key is a custom logical link, not a FK)
- ❌ Deployment links, commit links, PR links

## Response Template

For a specific column:
```
[Column name] (`[data type]`, [nullable/not null]) — [one-sentence business meaning].

Example values: [safe examples from jira_issues.md].

Used in queries: [which approved queries use this column].

Don't confuse with: [commonly confused column] — [key difference].
```
