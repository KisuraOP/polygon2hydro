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
