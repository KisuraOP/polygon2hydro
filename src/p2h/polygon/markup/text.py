"""Text hygiene shared by every conversion stage.

Nothing here knows about TeX semantics: these helpers only normalise line
endings, drop comments and strip HTML tags.
"""

from __future__ import annotations

import re


def normalize_newlines(text: str) -> str:
    """Unify line endings without touching TeX macros such as ``\\n``.

    Polygon writes CRLF, but also the odd ``\\r\\\\n`` sequence produced by
    older exports; both are converted while ``\\neq`` and friends are left
    alone.
    """
    return text.replace("\r\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")


def strip_comments(text: str) -> str:
    """Remove TeX comments, keeping escaped ``\\%`` intact.

    A ``%`` that is preceded by a backslash is a literal percent sign, not the
    start of a comment, so it must survive.
    """
    return re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)


def strip_tags(text: str) -> str:
    """Drop every HTML tag, leaving the text content."""
    return re.sub(r"(?is)<[^>]+>", "", text)


def find_matching_brace(text: str, open_index: int) -> int | None:
    """Index of the ``}`` matching the ``{`` at ``open_index``."""
    if open_index < 0 or open_index >= len(text) or text[open_index] != "{":
        return None

    depth = 0
    i = open_index
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


_DEFINITION_START = re.compile(r"\\def\s*\\?[a-zA-Z]+[^{}]*\{")


def strip_tex_definitions(text: str) -> str:
    """Remove ``\\def`` definitions such as ``\\def \\htmlPixelsInCm {45}``.

    Polygon statements often smuggle macro definitions into a ``center`` block
    next to an image.  Markdown has no equivalent, and leaving them in would
    show the definition source to the reader.
    """
    pieces: list[str] = []
    pos = 0
    while True:
        match = _DEFINITION_START.search(text, pos)
        if match is None:
            pieces.append(text[pos:])
            break
        pieces.append(text[pos:match.start()])
        close = find_matching_brace(text, match.end() - 1)
        if close is None:
            pieces.append(text[match.start():])
            break
        pos = close + 1
    return "".join(pieces)
