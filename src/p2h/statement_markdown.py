from __future__ import annotations

import html
import re


def _normalize_newlines(text: str) -> str:
    # Polygon section files commonly use CRLF or CR+escaped-LF sequences.
    # Only normalize actual line separators; do not rewrite TeX macros like \neq.
    return text.replace("\r\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")


def _strip_tex_comments(text: str) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        escaped = re.sub(r"\\%", "", line)
        idx = escaped.find("%")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _parse_includegraphics_width(opts: str) -> str | None:
    m = re.search(r"width\s*=\s*([0-9]+(?:\.[0-9]+)?\\?%)", opts)
    if not m:
        return None
    width = m.group(1).replace("\\", "")
    return width


def _center_block_to_markdown(match: re.Match[str]) -> str:
    body = match.group(1)
    imgs = re.findall(r"\\includegraphics(?:\[([^\]]*)\])?\{([^}]+)\}", body)
    if not imgs:
        return ""

    blocks: list[str] = []
    for opts, img in imgs:
        width = _parse_includegraphics_width(opts or "")
        if width:
            blocks.append(f"<center>\n<img src=\"file://{img}\" width=\"{width}\" />\n</center>")
        else:
            blocks.append(f"<center>\n<img src=\"file://{img}\"/>\n</center>")
    return "\n" + "\n\n".join(blocks) + "\n"


def _tex_itemize_to_md(match: re.Match[str]) -> str:
    body = match.group(1)
    items = re.findall(r"\\item\s*(.*?)(?=(?:\\item|$))", body, flags=re.S)
    normalized = [re.sub(r"\s+", " ", i.strip()) for i in items if i.strip()]
    return "\n" + "\n".join(f"- {i}" for i in normalized) + "\n"


def _tex_enum_to_md(match: re.Match[str]) -> str:
    body = match.group(1)
    items = re.findall(r"\\item\s*(.*?)(?=(?:\\item|$))", body, flags=re.S)
    normalized = [re.sub(r"\s+", " ", i.strip()) for i in items if i.strip()]
    return "\n" + "\n".join(f"{idx}. {i}" for idx, i in enumerate(normalized, start=1)) + "\n"


def _tex_code_to_md(match: re.Match[str]) -> str:
    body = _normalize_newlines(match.group(2)).strip("\n")
    if not body.strip():
        return ""
    return f"\n```text\n{body}\n```\n"


def _tex_math_block_to_md(match: re.Match[str]) -> str:
    body = _normalize_newlines(match.group(2)).strip()
    if not body:
        return ""
    return f"\n$$\n{body}\n$$\n"


def _tex_inline_to_markdown(text: str) -> str:
    s = text
    s = re.sub(
        r"\\includegraphics(?:\[([^\]]*)\])?\{([^}]+)\}",
        lambda m: (
            f"<center>\n<img src=\"file://{m.group(2)}\" width=\"{w}\" />\n</center>"
            if (w := _parse_includegraphics_width(m.group(1) or ""))
            else f"<center>\n<img src=\"file://{m.group(2)}\"/>\n</center>"
        ),
        s,
    )
    replacements = [
        (r"\\textbf\{([^{}]*)\}", r"**\1**"),
        (r"\\textit\{([^{}]*)\}", r"*\1*"),
        (r"\\emph\{([^{}]*)\}", r"*\1*"),
        (r"\\texttt\{([^{}]*)\}", r"`\1`"),
        (r"\\t\{([^{}]*)\}", r"`\1`"),
        (r"\\\$", "$"),
        (r"\\(left|right|displaystyle|quad|qquad)", ""),
        (r"~", " "),
    ]
    for old, new in replacements:
        s = re.sub(old, new, s)
    s = re.sub(r"\\\\", "\n", s)
    s = re.sub(r"\n\s*\n", "\n\n", s)
    return s


def _strip_tags(text: str) -> str:
    return re.sub(r"(?is)<[^>]+>", "", text)


def html_to_markdown(text: str) -> str:
    body = re.sub(r"(?is)<script.*?>.*?</script>", "", text)
    body = re.sub(r"(?is)<style.*?>.*?</style>", "", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?is)</p>", "\n\n", body)
    body = re.sub(
        r"(?is)<h([1-6])[^>]*>(.*?)</h\1>",
        lambda m: "#" * int(m.group(1)) + " " + _strip_tags(m.group(2)) + "\n\n",
        body,
    )
    body = re.sub(r"(?is)<li[^>]*>(.*?)</li>", lambda m: "- " + _strip_tags(m.group(1)) + "\n", body)

    placeholders: dict[str, str] = {}

    def _img_repl(m: re.Match[str]) -> str:
        src = m.group(1)
        attrs = m.group(2) or ""
        w_match = re.search(r'width\s*=\s*"([^"]+)"', attrs)
        if w_match:
            block = f"<center>\n<img src=\"{src}\" width=\"{w_match.group(1)}\" />\n</center>"
        else:
            block = f"<center>\n<img src=\"{src}\"/>\n</center>"
        key = f"__IMG_BLOCK_{len(placeholders)}__"
        placeholders[key] = block
        return key

    body = re.sub(r'(?is)<img[^>]*src="([^"]+)"([^>]*)>', _img_repl, body)
    body = _strip_tags(body)
    body = html.unescape(body)
    for key, block in placeholders.items():
        body = body.replace(key, block)

    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not body:
        return "# Description\n\n(Empty statement)\n"
    if not body.lstrip().startswith("#"):
        body = "# Description\n\n" + body
    return body + "\n"


def tex_block_to_markdown(text: str) -> str:
    s = _normalize_newlines(text)
    s = _strip_tex_comments(s)
    s = re.sub(r"\\begin\{center\}(.*?)\\end\{center\}", _center_block_to_markdown, s, flags=re.S)
    s = re.sub(r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", _tex_enum_to_md, s, flags=re.S)
    s = re.sub(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", _tex_itemize_to_md, s, flags=re.S)
    s = re.sub(r"\\begin\{(verbatim|lstlisting)\}(.*?)\\end\{\1\}", _tex_code_to_md, s, flags=re.S)
    s = re.sub(r"\\begin\{(equation\*?|align\*?)\}(.*?)\\end\{\1\}", _tex_math_block_to_md, s, flags=re.S)
    s = _tex_inline_to_markdown(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def tex_to_markdown(text: str) -> str:
    content = _normalize_newlines(text)
    content = _strip_tex_comments(content)
    content = re.sub(r"\\begin\{problem\}\{.*?\}\{.*?\}\{.*?\}\{.*?\}\{.*?\}", "", content, flags=re.S)
    content = content.replace("\\end{problem}", "")
    content = re.sub(r"\\section\*?\{([^}]*)\}", lambda m: f"\n# {m.group(1)}\n", content)
    content = re.sub(r"\\subsection\*?\{([^}]*)\}", lambda m: f"\n## {m.group(1)}\n", content)
    content = re.sub(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", _tex_itemize_to_md, content, flags=re.S)
    content = re.sub(r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", _tex_enum_to_md, content, flags=re.S)
    content = re.sub(r"\\begin\{(verbatim|lstlisting)\}(.*?)\\end\{\1\}", _tex_code_to_md, content, flags=re.S)
    content = re.sub(r"\\begin\{(equation\*?|align\*?)\}(.*?)\\end\{\1\}", _tex_math_block_to_md, content, flags=re.S)
    content = _tex_inline_to_markdown(content)
    content = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", "", content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    if not content:
        return "# Description\n\n(Statement conversion fallback from TeX)\n"
    if not content.lstrip().startswith("#"):
        content = "# Description\n\n" + content
    return content + "\n"
