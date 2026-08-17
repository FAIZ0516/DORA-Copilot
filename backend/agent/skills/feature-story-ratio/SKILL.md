---
name: feature-story-ratio
description: Analyze feature vs user story distribution and ratios. Trigger when user asks about "feature story ratio", "feature breakdown", "story to feature mapping".
---

# feature-story-ratio

Analyze feature-to-user-story relationships in the DCPM project.

## Queries to Use

- **Primary:** `feature_vs_user_story` — feature counts vs user story counts
- **Supplement:** `story_to_feature_ratio` — ratio analysis

## Step-by-Step

1. Run the appropriate query based on what the user wants.
2. Present feature count, user story count, and the ratio.
3. Flag missing `featurelink_key` values.

## Interpretation Rules

- **`featurelink_key` is a custom logical link** — not a database foreign key. 73 values point to non-existent keys.
- Only 24,192 issues (28.4%) have a populated `featurelink_key`. Most issues are not linked to any feature.
- A Feature is normally a larger capability; a User Story normally describes user-facing value. These are common Jira meanings — the organisation's exact definitions **Need confirmation**.
- Feature-to-story ratio is affected by how the organization defines and links features — not just by development practices.
- The materialized view `mvw_gdt_dte_jira_fuslist` connects releases to features and excludes two rejected status names. It may be stale between refreshes.
- Sub-tasks, Tests, and Bugs are typically not linked via `featurelink_key` — they represent different work types.

## Response Template

> Templates below show *what* to report, not a fixed set of sections. Include a
> line only when this request needs it; omit anything the user did not ask for.
> Never end an answer by offering further help or suggesting a follow-up
> question -- the interface has its own follow-up feature.

```
Feature-to-story analysis for DCPM:

- Total features: [X]
- Total user stories: [Y]
- Ratio: [Z] stories per feature

Issues with feature links: 24,192 (28.4% of all issues). 73 feature link values reference keys that don't exist in the current snapshot.

Limitations: `featurelink_key` is a custom project field without FK enforcement. This ratio reflects how features are defined and linked in Jira, not necessarily development patterns. Tests, Bugs, and Sub-tasks are typically not feature-linked.
```

## Common Mistakes to Avoid

- ❌ Treating `featurelink_key` as a mandatory or enforced relationship
- ❌ Claiming the ratio means "too many/few stories per feature"
- ❌ Ignoring the 73 broken links and 71.6% unlinked issues
- ❌ Presenting this as a delivery health metric
