# Database Overview

Purpose

This database stores engineering delivery metrics for Scrum Masters.

Main tables

- bugs
- features
- sprints
- releases
- test_cases
- squads


Relationships

A Feature belongs to one Sprint.

A Sprint belongs to one Squad.

A Bug belongs to one Feature.

A Feature belongs to one Release.

Business Rules

- Closed bugs are excluded from active bug counts.
- Deployment Frequency is calculated per release.
- Story Points are aggregated by sprint.
