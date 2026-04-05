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


def _normalize_arrow_tokens(text: str) -> str:
    s = text
    s = re.sub(r"\\rightarrow\b", r"\\to", s)
    s = re.sub(r"\\Rightarrow\b", r"\\to", s)
    s = re.sub(r"\\Longrightarrow\b", r"\\to", s)
    s = re.sub(r"\\longrightarrow\b", r"\\to", s)
    s = re.sub(r"(?<!\\)\barrow\b", r"\\to", s)
    s = re.sub(r"\\to\s+", r"\\to ", s)
    return s


def _normalize_math_arrow_tokens(text: str) -> str:
    s = text

    s = re.sub(r"\$\$(.*?)\$\$", lambda m: "$$" + _normalize_arrow_tokens(m.group(1)) + "$$", s, flags=re.S)
    s = re.sub(r"(?<!\$)\$([^\n$]+?)\$", lambda m: "$" + _normalize_arrow_tokens(m.group(1)) + "$", s)
    s = re.sub(r"\\\((.*?)\\\)", lambda m: r"\(" + _normalize_arrow_tokens(m.group(1)) + r"\)", s, flags=re.S)
    s = re.sub(r"\\\[(.*?)\\\]", lambda m: r"\[" + _normalize_arrow_tokens(m.group(1)) + r"\]", s, flags=re.S)

    return s


def _matrix_to_array_repl(match: re.Match[str]) -> str:
    body = _normalize_newlines(match.group(1))
    rows = [line.strip() for line in body.split("\n") if line.strip()]
    if not rows:
        return r"\begin{array}{ll}\end{array}"

    normalized: list[str] = []
    for idx, row in enumerate(rows):
        row = re.sub(r"\s*\\\\\s*$", "", row)
        row = _normalize_arrow_tokens(row)
        if idx < len(rows) - 1:
            row = row + " __MATRIX_ROW_BREAK__"
        normalized.append(row)

    return r"\begin{array}{ll}" + "\n" + "\n".join(normalized) + "\n" + r"\end{array}"


def _normalize_matrix_envs(text: str) -> str:
    return re.sub(r"\\begin\{matrix\}(.*?)\\end\{matrix\}", _matrix_to_array_repl, text, flags=re.S)


def _restore_math_placeholders(text: str) -> str:
    return text.replace("__MATRIX_ROW_BREAK__", r" \\")


def _find_matching_brace(text: str, open_idx: int) -> int | None:
    if open_idx < 0 or open_idx >= len(text) or text[open_idx] != "{":
        return None

    depth = 0
    i = open_idx
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _epigraph_to_markdown(text: str) -> str:
    s = text
    out: list[str] = []
    pos = 0

    while True:
        idx = s.find(r"\epigraph", pos)
        if idx < 0:
            out.append(s[pos:])
            break

        out.append(s[pos:idx])
        i = idx + len(r"\epigraph")
        while i < len(s) and s[i].isspace():
            i += 1

        if i >= len(s) or s[i] != "{":
            out.append(s[idx:idx + len(r"\epigraph")])
            pos = idx + len(r"\epigraph")
            continue

        body_close = _find_matching_brace(s, i)
        if body_close is None:
            out.append(s[idx:])
            break

        j = body_close + 1
        while j < len(s) and s[j].isspace():
            j += 1
        if j >= len(s) or s[j] != "{":
            out.append(s[idx:body_close + 1])
            pos = body_close + 1
            continue

        source_close = _find_matching_brace(s, j)
        if source_close is None:
            out.append(s[idx:])
            break

        body = s[i + 1:body_close]
        source = s[j + 1:source_close]

        body_text = _normalize_newlines(body)
        body_text = re.sub(r"\\\\\s*", "\n", body_text)
        quote_lines = [line.strip() for line in body_text.split("\n") if line.strip()]
        source_text = _normalize_newlines(source).strip()
        source_text = re.sub(r"^[\-—\s]+", "", source_text)

        lines: list[str] = []
        for line in quote_lines:
            lines.append(f"> {line}  ")
        if source_text:
            lines.append(f"> ——{source_text}")

        block = "\n".join(lines)
        if block:
            out.append("\n" + block + "\n")

        pos = source_close + 1

    return "".join(out)


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

    s = re.sub(r"\\t\{([^{}]*)\}", r"\\texttt{\1}", s)
    placeholders: dict[str, str] = {}

    def _texttt_in_math_repl(m: re.Match[str]) -> str:
        key = f"__TEXTTT_MATH_{len(placeholders)}__"
        placeholders[key] = f"$\\texttt{{{m.group(1)}}}$"
        return key

    s = re.sub(r"(?<!\\)\$\\texttt\{([^{}]*)\}\$", _texttt_in_math_repl, s)
    s = re.sub(r"\\texttt\{([^{}]*)\}", r"$\\texttt{\1}$", s)
    for key, value in placeholders.items():
        s = s.replace(key, value)

    replacements = [
        (r"\\textbf\{([^{}]*)\}", r"**\1**"),
        (r"\\textit\{([^{}]*)\}", r"*\1*"),
        (r"\\emph\{([^{}]*)\}", r"*\1*"),
        (r"\\\$", "$"),
        (r"\\(?:left|right|displaystyle|quad|qquad)\b", ""),
        (r"~", " "),
    ]
    for old, new in replacements:
        s = re.sub(old, new, s)
    s = re.sub(r"\\\\", "\n", s)
    s = re.sub(r"\n\s*\n", "\n\n", s)
    s = _restore_math_placeholders(s)
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
    s = _normalize_matrix_envs(s)
    s = _normalize_math_arrow_tokens(s)
    s = _epigraph_to_markdown(s)
    s = re.sub(r"\\begin\{center\}(.*?)\\end\{center\}", _center_block_to_markdown, s, flags=re.S)
    s = re.sub(r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", _tex_enum_to_md, s, flags=re.S)
    s = re.sub(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", _tex_itemize_to_md, s, flags=re.S)
    s = re.sub(r"\\begin\{(verbatim|lstlisting|BVerbatim)\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}", _tex_code_to_md, s, flags=re.S)
    s = re.sub(r"\\begin\{(equation\*?|align\*?)\}(.*?)\\end\{\1\}", _tex_math_block_to_md, s, flags=re.S)
    s = _tex_inline_to_markdown(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def tex_to_markdown(text: str) -> str:
    content = _normalize_newlines(text)
    content = _strip_tex_comments(content)
    content = _normalize_matrix_envs(content)
    content = _normalize_math_arrow_tokens(content)
    content = _epigraph_to_markdown(content)
    content = re.sub(r"\\begin\{problem\}\{.*?\}\{.*?\}\{.*?\}\{.*?\}\{.*?\}", "", content, flags=re.S)
    content = content.replace("\\end{problem}", "")
    content = re.sub(r"\\section\*?\{([^}]*)\}", lambda m: f"\n# {m.group(1)}\n", content)
    content = re.sub(r"\\subsection\*?\{([^}]*)\}", lambda m: f"\n## {m.group(1)}\n", content)
    content = re.sub(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", _tex_itemize_to_md, content, flags=re.S)
    content = re.sub(r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", _tex_enum_to_md, content, flags=re.S)
    content = re.sub(r"\\begin\{(verbatim|lstlisting|BVerbatim)\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}", _tex_code_to_md, content, flags=re.S)
    content = re.sub(r"\\begin\{(equation\*?|align\*?)\}(.*?)\\end\{\1\}", _tex_math_block_to_md, content, flags=re.S)
    content = _tex_inline_to_markdown(content)
    content = re.sub(r"\\(?!texttt\b|begin\b|end\b|to\b)[a-zA-Z]+\*?(\[[^\]]*\])?", "", content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    if not content:
        return "# Description\n\n(Statement conversion fallback from TeX)\n"
    if not content.lstrip().startswith("#"):
        content = "# Description\n\n" + content
    return content + "\n"
