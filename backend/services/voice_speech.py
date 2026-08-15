"""Turn a validated assistant answer into speakable segments.

Answers are Markdown written for the eye: headings, bullets, bold, tables,
column names in backticks. Read aloud verbatim they are unlistenable, so this
strips the formatting and splits the result into sentence-sized pieces.

Segmenting matters for more than pacing. The first segment can be synthesised
and start playing while the rest are still queued, and when the user interrupts
the remaining segments are simply never requested -- so an interruption stops
consuming ElevenLabs credits immediately.

Deterministic: no model is involved in deciding what is said, only in having
said it. The words are the agent's validated answer.
"""

from __future__ import annotations

import re

# Roughly a comfortable spoken breath. Long enough that ordinary sentences stay
# whole, short enough that the first audio starts quickly.
MAX_SEGMENT_CHARS = 240
MIN_SEGMENT_CHARS = 24

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s*")
_BULLET = re.compile(r"(?m)^\s*[-*+]\s+")
_NUMBERED = re.compile(r"(?m)^\s*\d+[.)]\s+")
_BLOCKQUOTE = re.compile(r"(?m)^\s*>\s?")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(.+?)\1", re.DOTALL)
_TABLE_DIVIDER = re.compile(r"(?m)^\s*\|?[\s:-]*\|[\s|:-]*$")
_TABLE_ROW = re.compile(r"(?m)^\s*\|(.+)\|\s*$")
_HORIZONTAL_RULE = re.compile(r"(?m)^\s*([-*_])\s*(\1\s*){2,}$")
_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{2,}")

# Abbreviations that end in a period without ending a sentence.
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "approx.", "no.", "fig.")


def markdown_to_speech(text: str) -> str:
    """Strip Markdown to plain prose a voice can read."""

    if not text:
        return ""
    cleaned = _CODE_FENCE.sub(" ", text)
    cleaned = _IMAGE.sub(" ", cleaned)
    cleaned = _LINK.sub(r"\1", cleaned)
    cleaned = _HORIZONTAL_RULE.sub(" ", cleaned)
    cleaned = _TABLE_DIVIDER.sub(" ", cleaned)
    # A table row read aloud as pipes is noise; speak the cells instead.
    cleaned = _TABLE_ROW.sub(
        lambda match: ", ".join(
            cell.strip() for cell in match.group(1).split("|") if cell.strip()
        )
        + ".",
        cleaned,
    )
    cleaned = _HEADING.sub("", cleaned)
    cleaned = _BLOCKQUOTE.sub("", cleaned)
    # Bullets become sentences so the reader hears a list, not a wall.
    cleaned = _BULLET.sub("", cleaned)
    cleaned = _NUMBERED.sub("", cleaned)
    cleaned = _EMPHASIS.sub(r"\2", cleaned)
    cleaned = _INLINE_CODE.sub(r"\1", cleaned)
    # Underscored identifiers are unreadable aloud.
    cleaned = re.sub(r"\b(\w+)_(\w+)\b", r"\1 \2", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    cleaned = _MULTI_NEWLINE.sub("\n", cleaned)
    lines = [line.strip() for line in cleaned.split("\n")]
    # Give every line terminal punctuation so segmentation can find boundaries.
    spoken = [
        line if line.endswith((".", "!", "?", ":", ";")) else f"{line}."
        for line in lines
        if line
    ]
    return " ".join(spoken).strip()


def _sentences(text: str) -> list[str]:
    parts: list[str] = []
    buffer = ""
    for token in re.split(r"(?<=[.!?])\s+", text):
        candidate = f"{buffer} {token}".strip() if buffer else token
        lowered = candidate.lower()
        # Keep "e.g." attached to what follows rather than ending a sentence.
        if any(lowered.endswith(abbrev) for abbrev in _ABBREVIATIONS):
            buffer = candidate
            continue
        parts.append(candidate)
        buffer = ""
    if buffer:
        parts.append(buffer)
    return [part for part in parts if part.strip()]


def _split_long(sentence: str) -> list[str]:
    """Break a sentence too long to speak comfortably, at clause boundaries."""

    if len(sentence) <= MAX_SEGMENT_CHARS:
        return [sentence]
    pieces: list[str] = []
    current = ""
    for clause in re.split(r"(?<=[,;:])\s+", sentence):
        if current and len(current) + len(clause) + 1 > MAX_SEGMENT_CHARS:
            pieces.append(current.strip())
            current = clause
        else:
            current = f"{current} {clause}".strip()
    if current:
        pieces.append(current.strip())
    # A clause longer than the limit still has to be spoken; hard-split it.
    final: list[str] = []
    for piece in pieces:
        while len(piece) > MAX_SEGMENT_CHARS:
            cut = piece.rfind(" ", 0, MAX_SEGMENT_CHARS) or MAX_SEGMENT_CHARS
            final.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            final.append(piece)
    return final


def segment_for_speech(text: str) -> list[str]:
    """Markdown answer to ordered, speakable segments.

    Short trailing fragments are merged backwards so the voice does not stop
    for a two-word sentence.
    """

    spoken = markdown_to_speech(text)
    if not spoken:
        return []
    segments: list[str] = []
    for sentence in _sentences(spoken):
        for piece in _split_long(sentence):
            if (
                segments
                and len(piece) < MIN_SEGMENT_CHARS
                and len(segments[-1]) + len(piece) + 1 <= MAX_SEGMENT_CHARS
            ):
                segments[-1] = f"{segments[-1]} {piece}"
            else:
                segments.append(piece)
    return segments


__all__ = [
    "MAX_SEGMENT_CHARS",
    "MIN_SEGMENT_CHARS",
    "markdown_to_speech",
    "segment_for_speech",
]
