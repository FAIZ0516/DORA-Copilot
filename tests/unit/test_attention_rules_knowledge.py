"""The dashboard's risk rules must reach the assistant.

The dashboard labels squads "Needs Attention" from ATTENTION_THRESHOLDS, but
those numbers lived only on the dashboard side. Asking Zara to explain a risk
badge produced "the material does not define any attention reasons" -- two
halves of one product with different knowledge of the same rule.
"""

from backend.dashboard_registry import ATTENTION_THRESHOLDS, attention_rules_text
from backend.knowledge_service import (
    ATTENTION_SECTION_TITLE,
    attention_rules_section,
    select_knowledge_sections,
)


def test_every_threshold_value_appears_in_the_generated_text() -> None:
    text = attention_rules_text()
    for band, rules in ATTENTION_THRESHOLDS.items():
        for metric, value in rules.items():
            assert str(value) in text, f"{band}.{metric}={value} is not described"


def test_the_description_is_generated_not_transcribed() -> None:
    """A hand-copied threshold would silently start lying when the dict
    changed, and a confidently wrong explanation is worse than 'I don't know'.
    Changing the constant must change the prose."""

    original = ATTENTION_THRESHOLDS["needs_attention"]["oldest_unresolved_days"]
    try:
        ATTENTION_THRESHOLDS["needs_attention"]["oldest_unresolved_days"] = 137
        assert "137 days old" in attention_rules_text()
    finally:
        ATTENTION_THRESHOLDS["needs_attention"]["oldest_unresolved_days"] = original
    assert "137 days old" not in attention_rules_text()


def test_a_new_rule_cannot_be_added_without_being_described() -> None:
    """An unphrased metric still renders, rather than vanishing silently."""

    ATTENTION_THRESHOLDS["needs_attention"]["brand_new_signal"] = 9
    try:
        assert "brand_new_signal" in attention_rules_text()
        assert "9" in attention_rules_text()
    finally:
        del ATTENTION_THRESHOLDS["needs_attention"]["brand_new_signal"]


def test_risk_questions_receive_the_rules() -> None:
    for question in (
        "Explain every attention reason.",
        "Why is this squad at risk?",
        "Which squads currently need attention?",
        "The delivery-risk status for squad MBK is Needs Attention. "
        "Explain which attention thresholds were crossed.",
        "Which signals are closest to crossing an attention threshold?",
    ):
        titles = [section.title for section in select_knowledge_sections(question)]
        assert ATTENTION_SECTION_TITLE in titles, question


def test_unrelated_questions_do_not_pay_for_the_rules() -> None:
    for question in ("How many bugs does each squad have?", "List all the squads"):
        titles = [section.title for section in select_knowledge_sections(question)]
        assert ATTENTION_SECTION_TITLE not in titles, question


def test_the_rules_survive_the_context_budget() -> None:
    """Placed first, so a question matching many Markdown sections cannot
    push the rules out of the prompt."""

    sections = select_knowledge_sections(
        "Explain every attention reason for the squad status and issue data"
    )
    assert sections[0].title == ATTENTION_SECTION_TITLE


def test_section_content_is_non_empty() -> None:
    section = attention_rules_section()
    assert section.title == ATTENTION_SECTION_TITLE
    assert len(section.content) > 200


def test_completion_questions_are_answerable() -> None:
    """"What changed in this scope?" asked for history the table does not
    hold -- it stores current status only, with no record of past values."""

    from backend.dashboard_registry import METRIC_REGISTRY

    questions = METRIC_REGISTRY["completion_pct"]["suggested_questions"]
    assert "What changed in this scope?" not in questions
    assert "Why is this percentage low?" not in questions
    # Neutral phrasing: active work is not always high.
    assert "Why is active work high?" not in METRIC_REGISTRY["active_work"]["suggested_questions"]
