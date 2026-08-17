---
name: explain-status
description: Explain Jira status values, status categories, and the workflow. Trigger when user asks "what does status X mean", "explain the workflow", "what status categories exist".
---

# explain-status

Explain Jira workflow statuses and categories in the DCPM project.

## Knowledge Source

Reference `backend/knowledge/jira_issues.md` — specifically:
- Section 5 (Jira Concepts — Status and status category)
- Section 8 (Jira Issue Lifecycle) — for the actual observed status-to-category mappings

## Step-by-Step

1. If user asks about a specific status, look it up in the observed mappings below.
2. If user asks about categories, explain the 3 categories and what each means.
3. If user asks about workflow, explain the generic flow but caution that actual transitions are unknown.

## Status Categories (Observed)

### To Do (Not Started)
`To Do`, `New`, `Ready 4 Development`, `Grooming`

### In Progress (Active or Waiting)
`Ready For Execution`, `Review In progress`, `InProgress`, `READY FOR TEST`, `Deferred`, `In Development`, `TEST IN PROGRESS`, `IMPEDED`, `Requirement Clarification`, `Impact Analysis`, `Rework`, `Assigned`, `Fix In Progress`, `Ready for PO Review`, `IMPLEMENTATION`, `Pending for Cancellation`, `Implementation`, `Reopened`, `Fixed`, `Pending Defer Approval`

### Done (End-State)
`Done`, `Closed`, `Cancelled`, `Rejected`, `Rejected/ Cancelled`

## Interpretation Rules

- **`Done` category = end-state, NOT success.** `Cancelled`, `Rejected`, and `Rejected/ Cancelled` all live in the `Done` category. Always filter resolution when discussing successful completion.
- **`IMPEDED` is the clearest blocked status**, but other waiting states (`Deferred`, `Pending for Cancellation`, `Pending Defer Approval`) may also indicate blockers. Need confirmation.
- **`Deferred` stays in `In Progress`** — do not reclassify it silently.
- **`Fixed` stays in `In Progress`** — it may require validation or closure later.
- **`Reopened` is a current state, not a reopen count.** You cannot know how many times an issue was reopened — no changelog exists.
- **`Closed` vs `Done`** — both are end-states in `Done` category. The business distinction between them is not defined in the repository.

## What You CANNOT See

- ❌ Status transition history — you see only the current status.
- ❌ Time spent in each status — no changelog.
- ❌ Who changed the status — no audit trail.
- ❌ Whether Reopened issues were previously Done, Cancelled, or something else.
- ❌ Workflow configuration — the allowed transitions between statuses.

## Response Template

> Templates below show *what* to report, not a fixed set of sections. Include a
> line only when this request needs it; omit anything the user did not ask for.
> Never end an answer by offering further help or suggesting a follow-up
> question -- the interface has its own follow-up feature.

For a specific status:
```
**Status:** [name] → **Category:** [To Do / In Progress / Done]

This status means [explanation based on its category and any known semantics].

[If relevant]: Don't confuse this with [commonly confused status] — [key difference].
```

For the full workflow:
```
The DCPM Jira project uses 29 custom statuses grouped into 3 categories:

**To Do (4 statuses):** Work that hasn't started — includes New, Grooming, Ready 4 Development.
**In Progress (20 statuses):** Work that is active or waiting — includes development, testing, review, IMPEDED, and deferred states.
**Done (5 statuses):** End-states — includes Done, Closed, Cancelled, and Rejected.

Important: Done means the issue reached an end-state, not necessarily that work was successfully delivered. Cancelled and Rejected items are in the Done category. I cannot show the workflow path or transition rules — this snapshot only shows current status.
```
