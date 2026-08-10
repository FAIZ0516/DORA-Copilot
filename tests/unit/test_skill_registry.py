"""Skill registry: discovery, deterministic matching, and playbook loading.

Covers the gap this module fixes: previously the runtime only ever sent the
model a skill's name+description, never the body (query IDs, interpretation
rules, response template) that INSTRUCTIONS.md Section 2 tells the model to
"load and follow".
"""

from __future__ import annotations

from backend.agent.skill_registry import (
    discover_skills,
    load_skill_playbooks,
    match_skills,
    skill_catalogue,
)


def test_all_nineteen_skills_are_discovered_with_name_and_description() -> None:
    skills = discover_skills()
    assert len(skills) == 19
    assert skills["count-issues"].description.startswith("Count Jira issues")
    assert all(skill.body for skill in skills.values())


def test_catalogue_lists_every_skill_name_once() -> None:
    catalogue = skill_catalogue()
    for name in discover_skills():
        assert f"**{name}**" in catalogue


def test_count_issues_message_matches_count_issues_skill() -> None:
    assert match_skills("How many bugs are there?") == ["count-issues"]


def test_impeded_message_matches_check_impeded_skill() -> None:
    assert "check-impeded" in match_skills("What issues are currently blocked?")


def test_ambiguous_message_matches_no_skill() -> None:
    assert match_skills("What is the weather like today?") == []


def test_squad_dora_question_can_match_multiple_skills_up_to_limit() -> None:
    matched = match_skills("How is the Jaeger squad performing on DORA metrics?", limit=2)
    assert "dora-by-squad" in matched
    assert len(matched) <= 2


def test_natural_phrasing_variants_still_match() -> None:
    """Regression cases for trigger phrasings that don't literally match a
    skill's frontmatter description but should still route correctly."""

    assert match_skills("What is in the backlog right now?") == ["backlog-status"]
    assert match_skills("What can this data not tell me?") == ["explain-limitations"]
    assert match_skills("Show feature to story ratio") == ["feature-story-ratio"]


def test_load_skill_playbooks_returns_full_body_not_just_description() -> None:
    playbooks = load_skill_playbooks("How many bugs are there?")
    assert "Active skill playbook: count-issues" in playbooks
    # Content that only exists in the SKILL.md body, never in the
    # name/description catalogue -- proves the full playbook was injected.
    assert "Query to Use" in playbooks
    assert "Common Mistakes to Avoid" in playbooks


def test_load_skill_playbooks_is_empty_when_nothing_matches() -> None:
    assert load_skill_playbooks("What is the weather like today?") == ""
