"""Block-level TeX environments: lists, centered images, code and epigraphs."""

from __future__ import annotations

import re

from p2h.polygon.markup.inline import image_block, parse_image_width
from p2h.polygon.markup.text import normalize_newlines


def center_to_markdown(match: re.Match[str]) -> str:
    """Turn a ``center`` environment holding images into centered image blocks."""
    images = re.findall(r"\\includegraphics(?:\[([^\]]*)\])?\{([^}]+)\}", match.group(1))
    if not images:
        return ""

    blocks = [image_block(source, parse_image_width(options or "")) for options, source in images]
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


def code_block_to_markdown(match: re.Match[str]) -> str:
    """Convert a verbatim-like environment to a fenced code block."""
    body = normalize_newlines(match.group(2)).strip("\n")
    if not body.strip():
        return ""
    return f"\n```text\n{body}\n```\n"


def _find_matching_brace(text: str, open_index: int) -> int | None:
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
