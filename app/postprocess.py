"""Cleanup applied to raw Whisper output. Rule based, no model involved."""
from __future__ import annotations

import re

FILLERS = [
    "um", "umm", "uh", "uhh", "uhm", "erm", "hmm", "hm", "mmm",
    "ahm", "ah", "eh", "er",
]

_FILLER_RE = re.compile(
    r"(?<![\w'])(" + "|".join(FILLERS) + r")(?![\w'])[,.]?\s*",
    flags=re.IGNORECASE,
)
_REPEAT_RE = re.compile(r"\b(\w+)(\s+\1\b)+", flags=re.IGNORECASE)
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:])")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def apply_dictionary(text: str, dictionary: dict) -> str:
    for spoken, written in dictionary.items():
        if not spoken:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(spoken)}(?!\w)", flags=re.IGNORECASE)
        text = pattern.sub(written, text)
    return text


def clean(text: str, *, remove_fillers: bool = True, capitalize_first: bool = True,
          trailing_space: bool = True, dictionary: dict | None = None) -> str:
    if not text:
        return ""
    text = text.strip()

    if remove_fillers:
        stripped = _FILLER_RE.sub("", text)
        # Never hand back an empty string just because the whole utterance
        # looked like a filler.
        if stripped.strip():
            text = stripped

    text = _REPEAT_RE.sub(r"\1", text)

    if dictionary:
        text = apply_dictionary(text, dictionary)

    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text).strip()

    if capitalize_first and text:
        text = text[0].upper() + text[1:]

    if trailing_space and text:
        text += " "
    return text
