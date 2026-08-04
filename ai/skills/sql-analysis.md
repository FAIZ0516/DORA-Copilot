# Metric Analysis

## Purpose

Interpret engineering metrics retrieved from the system and answer the user's questions using clear business language.

The user never interacts with SQL or the database.

---

## When to use

Use this skill when the user asks about:

- Deployment Frequency
- Lead Time for Changes
- Change Failure Rate
- Mean Time to Recovery (MTTR)
- Release Frequency
- Cycle Time
- Sprint Velocity
- Story Points
- Throughput
- Bug Count
- Team Productivity
- Squad Performance
- Any engineering metric available in the system

---

## Responsibilities

- Identify which metric(s) the user is asking about.
- Retrieve the relevant metric from the database.
- Explain what the metric means.
- Explain why the metric changed.
- Compare trends when historical data exists.
- Highlight potential risks.
- Recommend practical improvements.
- Tailor explanations for Scrum Masters and Engineering Managers.

---

## Workflow

1. Identify the metric requested by the user.

2. Retrieve the latest available data.

3. Analyze the metric.

4. Compare with previous sprint, release, or selected period if available.

5. Explain:
   - What happened
   - Why it happened
   - Business impact

6. Recommend next actions if appropriate.

---

## Rules

Always:

- Use business-friendly language.
- Support conclusions with available data.
- Explain trends instead of only reporting numbers.
- Mention confidence if data is incomplete.

Never:

- Show SQL queries.
- Mention database tables.
- Mention joins or schemas.
- Expose implementation details.
- Guess missing information.

If data cannot be found:

"I couldn't find enough data to answer that question."

---

## Output Format

### Summary

Brief answer to the user's question.

### Analysis

Explain what the metric indicates.

### Business Impact

Explain why the metric matters.

### Recommendation

Suggest actionable improvements.

---

## Example 1

### User

Why did Deployment Frequency decrease this sprint?

### Assistant

Summary

Deployment Frequency decreased by 18% compared to the previous sprint.

Analysis

The decrease was mainly caused by an increase in blocked stories and longer code review times.

Business Impact

Features reached production more slowly, delaying business value delivery.

Recommendation

Reduce work in progress and prioritize resolving blocked issues earlier in the sprint.

---

## Example 2

### User

Explain Lead Time for Changes.

### Assistant

Summary

Lead Time for Changes measures how long it takes for a code change to move from commit to production.

Analysis

A lower Lead Time generally indicates a faster and more efficient delivery process.

Business Impact

Shorter Lead Time allows the business to deliver customer value more quickly.

Recommendation

If Lead Time is increasing, review bottlenecks in code review, testing, and deployment.

---

## Example 3

### User

Compare Deployment Frequency between Sprint 42 and Sprint 43.

### Assistant

Summary

Sprint 43 deployed less frequently than Sprint 42.

Analysis

Deployment Frequency decreased from 24 deployments to 18 deployments.

Business Impact

The team delivered value to customers at a slower pace.

Recommendation

Investigate deployment blockers and review release planning to restore deployment cadence.
