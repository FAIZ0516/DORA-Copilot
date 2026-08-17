---
name: list-values
description: List current governed dimension values from DoraDB. Trigger when user asks "what squads/releases/years/types/statuses exist", "list all X", "show me available X".
---

# list-values

Discover what dimension values currently exist in the DCPM project.

## Query to Use

- **Primary:** `list_dimension_values` — REQUIRED FILTER: `dimension`
- **Available dimensions:** `project`, `squad`, `release_year`, `release`, `issuetype`, `status`, `metric`

## Step-by-Step

1. Determine which dimension the user is asking about.
2. Run `list_dimension_values` with `dimension = '[dimension_name]'`.
3. List the returned values. Note the total and any applied limit.

## Interpretation Rules

- Values are **discovered dynamically from DoraDB** — they are never hard-coded. If the database changes, the list changes.
- An empty result for a specific dimension + filter combination does NOT mean DoraDB is empty overall — only that no values matched those specific filters.
- `list_dimension_values` is a discovery tool, not an analytical query. Use it to find WHAT exists, then use other queries to analyze the data.
- For squad specifically: only 21 non-null values exist, and 63,481 rows have no squad. The squad list represents only the ~25% of issues with squad data.

## Response Template

> Templates below show *what* to report, not a fixed set of sections. Include a
> line only when this request needs it; omit anything the user did not ask for.
> Never end an answer by offering further help or suggesting a follow-up
> question -- the interface has its own follow-up feature.

```
Here are the [dimension] values currently in DoraDB for project DCPM:

[list of values, optionally with counts]

[X] total values found [note if limited].

[If relevant: flag any data quality concern, e.g. "Only 21 squads have data — 74.5% of issues have no squad assigned."]
```
