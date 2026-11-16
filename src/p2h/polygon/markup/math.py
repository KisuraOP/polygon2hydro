"""Math-mode fixes.

These helpers only rewrite content *inside* math spans or convert whole math
environments to the ``$$`` form markdown-it / KaTeX understands.
"""

from __future__ import annotations

import re

from p2h.polygon.markup.text import normalize_newlines


#: Placeholder for a matrix row separator, restored after the surrounding
#: markdown passes have run (they would otherwise eat the backslashes).
_MATRIX_ROW_BREAK = "__MATRIX_ROW_BREAK__"

_ARROW_COMMANDS = (
    (r"\\rightarrow\b", r"\\to"),
    (r"\\Rightarrow\b", r"\\to"),
    (r"\\Longrightarrow\b", r"\\to"),
    (r"\\longrightarrow\b", r"\\to"),
)


def _arrow_commands(text: str) -> str:
    s = text
    for pattern, replacement in _ARROW_COMMANDS:
        s = re.sub(pattern, replacement, s)
    s = re.sub(r"(?<!\\)\barrow\b", r"\\to", s)
    return re.sub(r"\\to\s+", r"\\to ", s)


def normalize_arrows(text: str) -> str:
    """Rewrite arrow aliases inside every math span.

    ``\\to`` is the only arrow form KaTeX and markdown share; the variants are
    collapsed before rendering. Text outside math is left untouched.
    """
    s = text
    s = re.sub(r"\$\$(.*?)\$\$", lambda m: "$$" + _arrow_commands(m.group(1)) + "$$", s, flags=re.S)
    s = re.sub(r"(?<!\$)\$([^\n$]+?)\$", lambda m: "$" + _arrow_commands(m.group(1)) + "$", s)
    s = re.sub(r"\\\((.*?)\\\)", lambda m: r"\(" + _arrow_commands(m.group(1)) + r"\)", s, flags=re.S)
    s = re.sub(r"\\\[(.*?)\\\]", lambda m: r"\[" + _arrow_commands(m.group(1)) + r"\]", s, flags=re.S)
    return s


def _matrix_to_array(match: re.Match[str]) -> str:
    body = normalize_newlines(match.group(1))
    rows = [line.strip() for line in body.split("\n") if line.strip()]
    if not rows:
        return r"\begin{array}{ll}\end{array}"

    normalized: list[str] = []
    for idx, row in enumerate(rows):
        row = re.sub(r"\s*\\\\\s*$", "", row)
        row = _arrow_commands(row)
        if idx < len(rows) - 1:
            row = row + " " + _MATRIX_ROW_BREAK
        normalized.append(row)

    return r"\begin{array}{ll}" + "\n" + "\n".join(normalized) + "\n" + r"\end{array}"


def normalize_matrices(text: str) -> str:
    """Rewrite ``matrix`` environments as ``array`` (KaTeX has no ``matrix``)."""
    return re.sub(r"\\begin\{matrix\}(.*?)\\end\{matrix\}", _matrix_to_array, text, flags=re.S)


def restore_matrix_placeholders(text: str) -> str:
    """Turn the row-break placeholder back into ``\\\\``."""
    return text.replace(_MATRIX_ROW_BREAK, r" \\")


def equation_block_to_markdown(match: re.Match[str]) -> str:
    """Convert an ``equation`` / ``align`` environment to a display-math block."""
    body = normalize_newlines(match.group(2)).strip()
    if not body:
        return ""
    return f"\n$$\n{body}\n$$\n"


def _display_math_to_block(match: re.Match[str]) -> str:
    body = match.group(1).strip()
    if not body:
        return ""
    # markdown-it only treats $$ as display math when the delimiters own their
    # lines and the block is separated from the surrounding paragraph.
    return f"\n\n$$\n{body}\n$$\n\n"


def normalize_display_math(text: str) -> str:
    """Expand inline ``$$ ... $$`` into the block form markdown-it recognises."""
    parts = re.split(r"(```.*?```)", text, flags=re.S)
    for i, part in enumerate(parts):
        if part.startswith("```"):
            continue  # never rewrite code blocks
        parts[i] = re.sub(r"\$\$(.+?)\$\$", _display_math_to_block, part, flags=re.S)
    return "".join(parts)
