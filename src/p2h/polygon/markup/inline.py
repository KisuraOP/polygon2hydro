"""Inline constructs: images, font commands, emphasis and escapes."""

from __future__ import annotations

import re

from p2h.polygon.markup.text import find_matching_brace


#: Legacy TeX font switches that Polygon authors still write, mapped to the
#: modern command. ``sf``/``rm`` have no markdown equivalent, so only the body
#: is kept. ``t`` is a Polygon-ism for ``\\texttt`` and is handled separately.
LEGACY_FONT_ALIASES = {
    "tt": "texttt",
    "bf": "textbf",
    "it": "textit",
    "em": "emph",
}

_INCLUDEGRAPHICS = r"\\includegraphics(?:\[([^\]]*)\])?\{([^}]+)\}"


def parse_image_width(options: str) -> str | None:
    """Extract a Hydro-friendly width from ``\\includegraphics`` options.

    Both ``width=0.8\\textwidth`` and ``width=62.5%`` are understood and turned
    into a percentage.
    """
    match = re.search(r"width\s*=\s*([0-9]+(?:\.[0-9]+)?\\?%)", options)
    if match:
        return match.group(1).replace("\\", "")

    match = re.search(r"width\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*\\textwidth\b", options)
    if not match:
        return None

    percent = float(match.group(1)) * 100
    if abs(percent - round(percent)) < 1e-9:
        return f"{int(round(percent))}%"
    return f"{percent:g}%"


def image_block(source: str, width: str | None = None, *, file_scheme: bool = True) -> str:
    """Render an image the way Hydro expects it.

    TeX statements reference images by bare filename, which Hydro resolves as a
    package attachment (``file://``). HTML statements already carry a usable
    ``src``, so no scheme is added there.
    """
    src = f"file://{source}" if file_scheme else source
    if width:
        return f"<center>\n<img src=\"{src}\" width=\"{width}\" />\n</center>"
    return f"<center>\n<img src=\"{src}\"/>\n</center>"


def _legacy_font_repl(match: re.Match[str]) -> str:
    name, body = match.group(1), match.group(2)
    alias = LEGACY_FONT_ALIASES.get(name)
    return f"\\{alias}{{{body}}}" if alias else body


_EMPHASIS_MARKERS = {"textbf": "**", "textit": "*", "emph": "*"}


def emphasis_to_markdown(text: str) -> str:
    r"""Convert emphasis commands, balancing braces and recursing into bodies.

    Polygon statements nest emphasis -- real case::

        \textbf{应特别注意\textbf{音高类别}和\textbf{音级}的格式。}

    A flat ``\\textbf\{([^{}]*)\}`` regex cannot see the outer command (its
    body contains braces) and leaves the raw source in the statement, so bodies
    are scanned with brace matching and converted recursively.
    """
    pieces: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "\\":
            pieces.append(text[index])
            index += 1
            continue
        match = re.match(r"\\(textbf|textit|emph)\{", text[index:])
        if match is None:
            pieces.append(text[index])
            index += 1
            continue
        open_index = index + match.end() - 1
        close = find_matching_brace(text, open_index)
        if close is None:
            pieces.append(text[index])
            index += 1
            continue
        body = emphasis_to_markdown(text[open_index + 1:close]).strip()
        marker = _EMPHASIS_MARKERS[match.group(1)]
        if marker == "**" and "**" in body:
            # Bold inside bold: the outer delimiter already applies to the whole
            # body, and ``**a**b**c**`` would alternate instead of covering the
            # whole sentence.  Flat is what the author meant (real case:
            # "应特别注意**音高类别**和**音级**的格式").
            body = body.replace("**", "")
        if body:
            pieces.append(f"{marker}{body}{marker}")
        index = close + 1
    return "".join(pieces)


def normalize_legacy_fonts(text: str) -> str:
    """Rewrite legacy font switches so they never reach the markdown verbatim.

    ``\\tt{fflush(stdout);}`` is the common real-world case; without this the
    rendered statement shows the raw macro.
    """
    s = text
    # \tt{...} / \bf{...} / \it{...} / \em{...} / \sf{...} / \rm{...}
    s = re.sub(r"\\(tt|bf|it|em|sf|rm)\{([^{}]*)\}", _legacy_font_repl, s)
    # group form: {\tt ...}
    s = re.sub(r"\{\\(tt|bf|it|em|sf|rm)\s+([^{}]*)\}", _legacy_font_repl, s)
    # any switch left without a body: drop it, the text that follows stands alone
    return re.sub(r"\\(?:tt|bf|it|em|sf|rm)(?![a-zA-Z])", "", s)


def inline_to_markdown(text: str) -> str:
    """Convert inline TeX to markdown.

    Stages, in order: images, legacy font switches, ``\\texttt`` (wrapped in
    math so Hydro keeps the monospace look), emphasis, remaining escapes.
    """
    s = re.sub(
        _INCLUDEGRAPHICS,
        lambda m: image_block(m.group(2), parse_image_width(m.group(1) or "")),
        text,
    )

    s = normalize_legacy_fonts(s)
    s = re.sub(r"\\t\{([^{}]*)\}", r"\\texttt{\1}", s)

    # \texttt inside an existing math span must not be wrapped a second time.
    protected: dict[str, str] = {}

    def _texttt_in_math(match: re.Match[str]) -> str:
        key = f"__TEXTTT_MATH_{len(protected)}__"
        protected[key] = f"$\\texttt{{{match.group(1)}}}$"
        return key

    s = re.sub(r"(?<!\\)\$\\texttt\{([^{}]*)\}\$", _texttt_in_math, s)
    s = re.sub(r"\\texttt\{([^{}]*)\}", r"$\\texttt{\1}$", s)
    for key, value in protected.items():
        s = s.replace(key, value)

    s = emphasis_to_markdown(s)

    replacements = (
        (r"\\\$", "$"),
        (r"\\(?:left|right|displaystyle|quad|qquad)\b", ""),
        (r"~", " "),
    )
    for pattern, replacement in replacements:
        s = re.sub(pattern, replacement, s)

    s = re.sub(r"\\\\", "\n", s)
    return re.sub(r"\n\s*\n", "\n\n", s)
