"""The two conversion pipelines, expressed as ordered stages.

``tex_block_to_markdown`` converts a fragment (``legend.tex``, ``input.tex``, …).
``tex_to_markdown`` converts a whole statement file and additionally turns
``\\section`` into headings and drops macros markdown cannot express.
Both share the same stage helpers, so a fix in one place reaches both.
"""

from __future__ import annotations

import html
import re

from p2h.polygon.markup.blocks import (
    center_to_markdown,
    code_block_to_markdown,
    enumerate_to_markdown,
    epigraph_to_markdown,
    itemize_to_markdown,
)
from p2h.polygon.markup.inline import image_block, inline_to_markdown
from p2h.polygon.markup.math import (
    equation_block_to_markdown,
    normalize_arrows,
    normalize_display_math,
    normalize_matrices,
    restore_matrix_placeholders,
)
from p2h.polygon.markup.text import normalize_newlines, strip_comments, strip_tags


_CENTER = r"\\begin\{center\}(.*?)\\end\{center\}"
_ENUMERATE = r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}"
_ITEMIZE = r"\\begin\{itemize\}(.*?)\\end\{itemize\}"
_CODE = r"\\begin\{(verbatim|lstlisting|BVerbatim)\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}"
_MATH_BLOCK = r"\\begin\{(equation\*?|align\*?)\}(.*?)\\end\{\1\}"
_PROBLEM_HEADER = r"\\begin\{problem\}\{.*?\}\{.*?\}\{.*?\}\{.*?\}\{.*?\}"
_SECTION = r"\\section\*?\{([^}]*)\}"
_SUBSECTION = r"\\subsection\*?\{([^}]*)\}"
_UNSUPPORTED_COMMAND = r"\\(?!texttt\b|begin\b|end\b|to\b)[a-zA-Z]+\*?(\[[^\]]*\])?"


def _prepare(text: str) -> str:
    """Stages shared by both pipelines, before any block is rewritten."""
    s = normalize_newlines(text)
    s = strip_comments(s)
    s = normalize_matrices(s)
    s = normalize_arrows(s)
    return epigraph_to_markdown(s)


def _replace_blocks(text: str, *, lists: bool = True, center: bool = False) -> str:
    """Rewrite environments into their markdown equivalents."""
    s = text
    if center:
        s = re.sub(_CENTER, center_to_markdown, s, flags=re.S)
    if lists:
        s = re.sub(_ENUMERATE, enumerate_to_markdown, s, flags=re.S)
        s = re.sub(_ITEMIZE, itemize_to_markdown, s, flags=re.S)
    s = re.sub(_CODE, code_block_to_markdown, s, flags=re.S)
    s = re.sub(_MATH_BLOCK, equation_block_to_markdown, s, flags=re.S)
    return normalize_display_math(s)


def _finish_inline(text: str) -> str:
    """Run the inline stage and restore placeholders it had to protect."""
    return restore_matrix_placeholders(inline_to_markdown(text))


def tex_block_to_markdown(text: str) -> str:
    """Convert a statement fragment (section file) to markdown."""
    s = _prepare(text)
    s = _replace_blocks(s, lists=True, center=True)
    s = _finish_inline(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def tex_to_markdown(text: str) -> str:
    """Convert a whole TeX statement file to markdown."""
    content = _prepare(text)
    content = re.sub(_PROBLEM_HEADER, "", content, flags=re.S)
    content = content.replace("\\end{problem}", "")
    content = re.sub(_SECTION, lambda m: f"\n# {m.group(1)}\n", content)
    content = re.sub(_SUBSECTION, lambda m: f"\n## {m.group(1)}\n", content)
    content = _replace_blocks(content, lists=True, center=False)
    content = _finish_inline(content)
    # Anything left is a macro markdown cannot express; dropping it beats
    # leaking the source to the reader.
    content = re.sub(_UNSUPPORTED_COMMAND, "", content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip()

    if not content:
        return "# Description\n\n(Statement conversion fallback from TeX)\n"
    if not content.lstrip().startswith("#"):
        content = "# Description\n\n" + content
    return content + "\n"


def html_to_markdown(text: str) -> str:
    """Convert an HTML statement to markdown.

    Images become the ``<center><img src=...></center>`` block Hydro expects;
    everything else is reduced to text with headings, paragraphs and list items
    preserved.
    """
    body = re.sub(r"(?is)<script.*?>.*?</script>", "", text)
    body = re.sub(r"(?is)<style.*?>.*?</style>", "", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?is)</p>", "\n\n", body)
    body = re.sub(
        r"(?is)<h([1-6])[^>]*>(.*?)</h\1>",
        lambda m: "#" * int(m.group(1)) + " " + strip_tags(m.group(2)) + "\n\n",
        body,
    )
    body = re.sub(r"(?is)<li[^>]*>(.*?)</li>", lambda m: "- " + strip_tags(m.group(1)) + "\n", body)

    placeholders: dict[str, str] = {}

    def _image_repl(match: re.Match[str]) -> str:
        source = match.group(1)
        width = re.search(r'width\s*=\s*"([^"]+)"', match.group(2) or "")
        key = f"__IMG_BLOCK_{len(placeholders)}__"
        placeholders[key] = image_block(source, width.group(1) if width else None, file_scheme=False)
        return key

    body = re.sub(r'(?is)<img[^>]*src="([^"]+)"([^>]*)>', _image_repl, body)
    body = strip_tags(body)
    body = html.unescape(body)
    for key, block in placeholders.items():
        body = body.replace(key, block)

    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not body:
        return "# Description\n\n(Empty statement)\n"
    if not body.lstrip().startswith("#"):
        body = "# Description\n\n" + body
    return body + "\n"
