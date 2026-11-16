"""Block-level TeX environments: lists, centered images, code and epigraphs."""

from __future__ import annotations

import re

from p2h.polygon.markup.inline import image_block, parse_image_width
from p2h.polygon.markup.text import (
    find_matching_brace,
    normalize_newlines,
    strip_tex_definitions,
)


def center_to_markdown(match: re.Match[str]) -> str:
    """Convert a ``center`` environment, keeping its images and other content.

    A ``center`` block holds images most of the time, but also tables, ``\\def``
    definitions and plain text (real case: a reference table inside ``center``).
    Dropping the non-image part silently deletes statement content, so the
    remaining text is passed on to the later block stages.
    """
    body = match.group(1)
    blocks = [
        image_block(source, parse_image_width(options or ""))
        for options, source in re.findall(
            r"\\includegraphics(?:\[([^\]]*)\])?\{([^}]+)\}", body
        )
    ]
    remaining = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}", "", body)
    remaining = strip_tex_definitions(remaining).strip()
    if remaining:
        blocks.append(remaining)
    if not blocks:
        return ""
    return "\n" + "\n\n".join(blocks) + "\n"


def _list_items(body: str) -> list[str]:
    items = re.findall(r"\\item\s*(.*?)(?=(?:\\item|$))", body, flags=re.S)
    return [re.sub(r"\s+", " ", item.strip()) for item in items if item.strip()]


def itemize_to_markdown(match: re.Match[str]) -> str:
    """Convert an ``itemize`` environment to a markdown bullet list."""
    items = _list_items(match.group(1))
    return "\n" + "\n".join(f"- {item}" for item in items) + "\n"


def enumerate_to_markdown(match: re.Match[str]) -> str:
    """Convert an ``enumerate`` environment to a numbered markdown list."""
    items = _list_items(match.group(1))
    return "\n" + "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1)) + "\n"


#: Sectioning commands that Polygon statements use as sub-headings inside a
#: statement section (``\subsubsection*{第一次运行}``).  Markdown has no levels
#: below ``###`` worth distinguishing here, and ``paragraph`` reads as bold.
_SECTION_COMMAND = re.compile(
    r"^\s*\\(section|subsection|subsubsection|paragraph|subparagraph)\*?\{([^{}]*)\}\s*$",
    re.MULTILINE,
)
_SECTION_MARKERS = {"section": "##", "subsection": "###", "subsubsection": "###"}


def section_commands_to_markdown(text: str) -> str:
    """Turn standalone sectioning commands into markdown headings."""

    def repl(match: re.Match[str]) -> str:
        command, title = match.group(1), match.group(2).strip()
        if not title:
            return ""
        marker = _SECTION_MARKERS.get(command)
        return f"\n{marker} {title}\n" if marker else f"\n**{title}**\n"

    return _SECTION_COMMAND.sub(repl, text)


def code_block_to_markdown(match: re.Match[str]) -> str:
    """Convert a verbatim-like environment to a fenced code block."""
    body = normalize_newlines(match.group(2)).strip("\n")
    if not body.strip():
        return ""
    return f"\n```text\n{body}\n```\n"


def tabular_to_markdown(match: re.Match[str]) -> str:
    """Convert a ``tabular`` environment to a markdown table.

    The column spec is ignored: markdown has no alignment/rule control, and the
    usual statement table is a simple grid.  ``\\hline`` disappears, and
    ``\\multicolumn`` falls back to its text.  A table with a single row (or no
    ``&`` at all) is kept as plain text rather than forced into a table.
    """
    body = match.group(2)
    body = re.sub(
        r"\\multicolumn\{[^}]*\}\{[^}]*\}\{([^{}]*)\}", r"\1", body
    )
    rows: list[list[str]] = []
    for raw in re.split(r"\\\\", body):
        raw = re.sub(r"\\hline", "", raw).strip()
        if not raw:
            continue
        cells = [re.sub(r"\s+", " ", cell).strip() for cell in re.split(r"(?<!\\)&", raw)]
        rows.append(cells)

    if len(rows) < 2 or max(len(row) for row in rows) < 2:
        return "\n" + "\n\n".join(" ".join(row) for row in rows) + "\n"

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n" + "\n".join(lines) + "\n"


def _find_matching_brace(text: str, open_index: int) -> int | None:
    """Index of the ``}`` matching the ``{`` at ``open_index``."""
    return find_matching_brace(text, open_index)


def epigraph_to_markdown(text: str) -> str:
    """Convert ``\\epigraph{body}{source}`` to a markdown block quote.

    Hand-written scanner rather than a regex: the body may contain nested braces
    and escaped characters that a regex cannot balance.
    """
    s = text
    pieces: list[str] = []
    pos = 0

    while True:
        index = s.find(r"\epigraph", pos)
        if index < 0:
            pieces.append(s[pos:])
            break

        pieces.append(s[pos:index])
        i = index + len(r"\epigraph")
        while i < len(s) and s[i].isspace():
            i += 1

        if i >= len(s) or s[i] != "{":
            pieces.append(s[index:index + len(r"\epigraph")])
            pos = index + len(r"\epigraph")
            continue

        body_close = _find_matching_brace(s, i)
        if body_close is None:
            pieces.append(s[index:])
            break

        j = body_close + 1
        while j < len(s) and s[j].isspace():
            j += 1
        if j >= len(s) or s[j] != "{":
            pieces.append(s[index:body_close + 1])
            pos = body_close + 1
            continue

        source_close = _find_matching_brace(s, j)
        if source_close is None:
            pieces.append(s[index:])
            break

        body = s[i + 1:body_close]
        source = s[j + 1:source_close]

        body_text = normalize_newlines(body)
        body_text = re.sub(r"\\\\\s*", "\n", body_text)
        quote_lines = [line.strip() for line in body_text.split("\n") if line.strip()]
        source_text = normalize_newlines(source).strip()
        source_text = re.sub(r"^[\-\u2014\s]+", "", source_text)

        lines = [f"> {line}  " for line in quote_lines]
        if source_text:
            lines.append(f"> ——{source_text}")

        block = "\n".join(lines)
        if block:
            pieces.append("\n" + block + "\n")

        pos = source_close + 1

    return "".join(pieces)
