"""Relevance validation: nothing in the answer that the request did not earn.

``response_validator`` checks that an answer is *true*. This one checks that it
is *wanted* -- that every section traces to the current information need rather
than to a habit of looking thorough.

Detection alone is not the mechanism. The blocks in ``ResponseDecision``
constrain generation first; this is the deterministic backstop for the part
that is reliably checkable, principally headings, which is why the strict rules
live here and the semantic judgement stays in the prompt.

``strip_unpermitted_sections`` is deliberately a removal rather than a
regeneration. A second model round trip would double an already slow turn to
delete a paragraph the user never asked for.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

from ..response.response_decision import PROHIBITED_HEADINGS


class RelevanceViolation(NamedTuple):
    code: str
    detail: str


# Which block a heading is offering. Only used to decide admissibility, so it
# maps the phrasings the model actually produces rather than every synonym.
_HEADING_BLOCKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:evidence|supporting data|the numbers|data)$", re.I), "evidence"),
    (re.compile(r"^(?:breakdown|by \w+|details?|values?|list)$", re.I), "breakdown"),
    (re.compile(r"^(?:comparison|compared|side by side)$", re.I), "comparison"),
    (re.compile(r"^(?:definition|what this means|meaning)$", re.I), "definition"),
    (re.compile(r"^(?:chart|graph|visual(?:isation|ization)?)$", re.I), "chart"),
    (
        re.compile(
            r"^(?:limitation|limitations|data coverage|caveats?|"
            r"what this does(?:n't| not) cover)$",
            re.I,
        ),
        "limitation",
    ),
    (re.compile(r"^(?:recommendations?|what to do|suggested actions?)$", re.I), "recommendation"),
    (re.compile(r"^(?:next steps?|next action|suggested next steps?)$", re.I), "next_step"),
)

# A heading on its own line: "**Worth knowing**", "## Worth knowing", or
# "Worth knowing:" -- the three shapes the model actually emits.
_HEADING_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*([A-Za-z][A-Za-z '\-]{2,40}?)\s*"
    r"(?:\*\*|__)?\s*:?\s*$"
)

_OFFER_OF_MORE = re.compile(
    r"(?:would you like me to|would you like a|shall i|do you want me to|"
    r"i can also|you can also|you may also want|next,? you should|"
    r"let me know if you)",
    re.I,
)
_RECOMMENDATION_LANGUAGE = re.compile(
    r"\b(?:i recommend|we recommend|it'?s recommended|you should consider|"
    r"the team should|consider (?:prioritis|prioritiz|reviewing|addressing)|"
    r"my recommendation)\b",
    re.I,
)
# Padding connectives that introduce material the user did not ask about.
_ASIDE = re.compile(
    r"\b(?:as an aside|as a side note|it'?s (?:also )?worth noting|"
    r"for (?:added |extra )?context,|by way of background|"
    r"you might also find it (?:useful|interesting))\b",
    re.I,
)


def _heading_of(line: str) -> str | None:
    """The heading text on a line, if the line is a heading at all."""

    # Bare prose can match the shape by accident, so require an explicit
    # marker: a hash, bold, or a trailing colon.
    if not re.search(r"^\s*(?:#{1,6}\s|\*\*|__)|:\s*$", line):
        return None
    match = _HEADING_LINE.match(line)
    if not match:
        return None
    heading = match.group(1).strip()
    return heading or None


def _block_for_heading(heading: str) -> str | None:
    for pattern, block in _HEADING_BLOCKS:
        if pattern.match(heading.strip()):
            return block
    return None


def _sentences(text: str) -> list[str]:
    """Sentences, with heading lines removed.

    Headings are dropped rather than kept so that the same conclusion restated
    under **Evidence** still compares equal to the original -- otherwise the
    heading text alone makes the duplicate look like a different sentence.
    """

    body = "\n".join(line for line in text.splitlines() if not _heading_of(line))
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", body))
        if len(sentence.strip()) > 25
    ]


def find_relevance_violations(
    answer: str,
    decision: dict[str, Any],
    *,
    previous_answer: str = "",
) -> list[RelevanceViolation]:
    """Report content the current request does not justify."""

    violations: list[RelevanceViolation] = []
    allowed = set(decision.get("allowed_blocks") or ())
    prohibited = {item.lower() for item in decision.get("prohibited_headings") or PROHIBITED_HEADINGS}

    for line in answer.splitlines():
        heading = _heading_of(line)
        if not heading:
            continue
        if heading.lower() in prohibited:
            violations.append(
                RelevanceViolation(
                    "generic_supplementary_heading",
                    f"Generic supplementary heading {heading!r}.",
                )
            )
            continue
        block = _block_for_heading(heading)
        if block and block not in allowed:
            violations.append(
                RelevanceViolation(
                    "unexpected_section",
                    f"Section {heading!r} is not admissible for this request.",
                )
            )

    if "recommendation" not in allowed and _RECOMMENDATION_LANGUAGE.search(answer):
        violations.append(
            RelevanceViolation(
                "unrequested_recommendation", "Recommendation given but not requested."
            )
        )
    # A clarification is exempt: asking the user which of two things they meant
    # is naturally phrased as an offer, and it is the whole answer. The strip
    # skips it for the same reason, and the two must agree.
    if (
        "next_step" not in allowed
        and decision.get("profile") != "clarification"
        and _OFFER_OF_MORE.search(answer)
    ):
        violations.append(
            RelevanceViolation(
                "unrequested_next_steps",
                "Answer offers further help or a next step that was not requested. "
                "The interface already suggests follow-up questions.",
            )
        )
    if _ASIDE.search(answer) and decision.get("profile") in {
        "direct_fact",
        "list",
        "comparison",
        "no_result",
        "error",
    }:
        violations.append(
            RelevanceViolation("irrelevant_content", "Answer digresses from the request.")
        )
    if (
        "limitation" in allowed
        and not decision.get("limitation_required")
        and any(
            _block_for_heading(heading) == "limitation"
            for heading in filter(None, (_heading_of(line) for line in answer.splitlines()))
        )
    ):
        violations.append(
            RelevanceViolation(
                "unnecessary_limitation",
                "Limitations section added without a limitation that changes the result.",
            )
        )

    sentences = _sentences(answer)
    repeated = {sentence for sentence in sentences if sentences.count(sentence) > 1}
    if repeated:
        violations.append(
            RelevanceViolation(
                "repeated_conclusion", "The same conclusion appears more than once."
            )
        )

    if previous_answer:
        previous = set(_sentences(previous_answer))
        current = _sentences(answer)
        if previous and current:
            reused = sum(1 for sentence in current if sentence in previous)
            # Half of a follow-up being the previous answer verbatim is a
            # restatement, not an answer to the new question.
            if reused * 2 >= len(current):
                violations.append(
                    RelevanceViolation(
                        "follow_up_repeats_previous_answer",
                        "The follow-up largely restates the previous answer.",
                    )
                )
    return violations


def strip_unpermitted_sections(answer: str, decision: dict[str, Any]) -> str:
    """Remove sections the request does not admit, leaving the rest intact.

    Only whole heading-led sections are removed, and only when the heading is
    prohibited outright or maps to a block that is not admissible. Prose with
    no heading is never touched here -- guessing at sentence relevance without
    a heading to anchor it would delete real answers.
    """

    allowed = set(decision.get("allowed_blocks") or ())
    prohibited = {item.lower() for item in decision.get("prohibited_headings") or PROHIBITED_HEADINGS}

    kept: list[str] = []
    dropping = False
    for line in answer.splitlines():
        heading = _heading_of(line)
        if heading:
            block = _block_for_heading(heading)
            dropping = heading.lower() in prohibited or (
                block is not None and block not in allowed
            )
            if dropping:
                continue
        if not dropping:
            kept.append(line)

    cleaned = "\n".join(kept)

    # The habit that survives section-stripping: a closing "Would you like me
    # to break this down by squad?". It is prose, not a section, so it has to
    # be removed sentence by sentence.
    #
    # Never for a clarification, where asking what the user wants *is* the
    # answer, and never if it would leave nothing behind.
    if "next_step" not in allowed and decision.get("profile") != "clarification":
        cleaned = _drop_offers_of_more(cleaned)

    # Collapse the blank runs left where content was removed.
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _drop_offers_of_more(text: str) -> str:
    """Remove sentences that offer further help, keeping everything else."""

    surviving_lines: list[str] = []
    for line in text.splitlines():
        if not _OFFER_OF_MORE.search(line):
            surviving_lines.append(line)
            continue
        # The line may hold an offer alongside real content, so split it.
        remainder = " ".join(
            sentence
            for sentence in re.split(r"(?<=[.!?])\s+", line.strip())
            if not _OFFER_OF_MORE.search(sentence)
        ).strip()
        if remainder:
            surviving_lines.append(remainder)

    stripped = "\n".join(surviving_lines).strip()
    # An answer that was *only* an offer is left alone: something is better
    # than an empty reply.
    return stripped if stripped else text


__all__ = [
    "RelevanceViolation",
    "find_relevance_violations",
    "strip_unpermitted_sections",
]
