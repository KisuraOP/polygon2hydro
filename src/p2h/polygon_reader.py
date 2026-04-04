from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from p2h.models import ProblemData, TestCase


def list_problem_slugs_from_names(names: list[str]) -> list[str]:
    slugs: set[str] = set()
    for name in names:
        if not name.startswith("problems/"):
            continue
        parts = PurePosixPath(name).parts
        if len(parts) >= 3:
            slugs.add(parts[1])
    return sorted(slugs)


def read_problem(
    work_root: Path,
    slug: str,
    *,
    verbose: bool = False,
    statement_language: str | None = None,
) -> ProblemData:
    base = work_root / "problems" / slug
    xml_path = base / "problem.xml"
    if not xml_path.exists():
        raise ValueError(f"{slug}: missing problem.xml")
    root = ET.fromstring(xml_path.read_bytes())

    title = _extract_title(root, statement_language=statement_language) or slug
    time_ms, memory_mb = _extract_limits(root)
    is_interactive, interactor_name = _extract_interactive_meta(root)
    checker_name = _extract_checker_name(root)
    if not is_interactive and not checker_name:
        raise ValueError(f"{slug}: missing checker source in problem.xml assets/checker")

    statement_md, statement_dir = _extract_statement_markdown(
        base,
        root,
        is_interactive=is_interactive,
        statement_language=statement_language,
    )
    tests = _extract_tests(base, slug)
    additional = _extract_additional_files(base, statement_dir)
    testdata_files = _extract_testdata_files(base, root, slug, is_interactive=is_interactive)

    if verbose:
        print(
            f"[{slug}] title={title} interactive={is_interactive} tests={len(tests)} additional={len(additional)} testdata_files={len(testdata_files)} "
            f"time={time_ms}ms memory={memory_mb}MB"
        )

    return ProblemData(
        slug=slug,
        title=title,
        time_ms=time_ms,
        memory_mb=memory_mb,
        statement_md=statement_md,
        tests=tests,
        additional_files=additional,
        testdata_files=testdata_files,
        is_interactive=is_interactive,
        interactor_name=interactor_name,
        checker_name=checker_name,
    )


def _language_priority(statement_language: str | None) -> tuple[str, ...]:
    if statement_language == "english":
        return ("english", "chinese")
    return ("chinese", "english")


def _extract_title(root: ET.Element, *, statement_language: str | None) -> str | None:
    names = root.find("names")
    if names is None:
        return None
    by_lang: dict[str, str] = {}
    for node in names.findall("name"):
        lang = node.attrib.get("language", "")
        value = node.attrib.get("value", "").strip()
        if value:
            by_lang[lang] = value

    for lang in _language_priority(statement_language):
        if by_lang.get(lang):
            return by_lang[lang]
    return next(iter(by_lang.values()), None)


def _extract_limits(root: ET.Element) -> tuple[int | None, int | None]:
    testset = root.find("./judging/testset")
    if testset is None:
        return None, None
    time_text = (testset.findtext("time-limit") or "").strip()
    memory_text = (testset.findtext("memory-limit") or "").strip()
    time_ms = int(time_text) if time_text.isdigit() else None
    memory_mb = (int(memory_text) // (1024 * 1024)) if memory_text.isdigit() else None
    return time_ms, memory_mb


def _extract_interactive_meta(root: ET.Element) -> tuple[bool, str | None]:
    interactor = root.find("./assets/interactor")
    if interactor is None:
        return False, None

    source = interactor.find("source")
    if source is None:
        return True, None

    rel = (source.attrib.get("path") or "").strip()
    if not rel:
        return True, None
    return True, PurePosixPath(rel).name


def _extract_checker_name(root: ET.Element) -> str | None:
    checker = root.find("./assets/checker")
    if checker is None:
        return None

    rel = (checker.attrib.get("path") or "").strip()
    if not rel:
        source = checker.find("source")
        if source is not None:
            rel = (source.attrib.get("path") or "").strip()

    if not rel:
        return None
    return PurePosixPath(rel).name or None


def _extract_statement_markdown(
    base: Path,
    root: ET.Element,
    *,
    is_interactive: bool,
    statement_language: str | None,
) -> tuple[str, Path | None]:
    for lang in _language_priority(statement_language):
        sections_dir = base / "statement-sections" / lang
        if sections_dir.exists():
            md = _sections_to_markdown(sections_dir, is_interactive=is_interactive)
            if md.strip():
                return md, sections_dir

    statements = root.find("statements")
    if statements is None:
        return "# Description\n\n(Empty statement)\n", None

    for lang in _language_priority(statement_language):
        html_rel = None
        tex_rel = None
        for st in statements.findall("statement"):
            if st.attrib.get("language") != lang:
                continue
            stype = st.attrib.get("type", "")
            rel = st.attrib.get("path")
            if not rel:
                continue
            if stype == "text/html":
                html_rel = rel
            elif stype == "application/x-tex":
                tex_rel = rel

        if html_rel:
            html_path = base / PurePosixPath(html_rel)
            if html_path.exists():
                return _html_to_markdown(html_path.read_text(encoding="utf-8", errors="ignore")), html_path.parent

        if tex_rel:
            tex_path = base / PurePosixPath(tex_rel)
            if tex_path.exists():
                return _tex_to_markdown(tex_path.read_text(encoding="utf-8", errors="ignore")), tex_path.parent

    return "# Description\n\n(Statement not found)\n", None


def _sections_to_markdown(sections_dir: Path, *, is_interactive: bool) -> str:
    legend = _read_tex_file(sections_dir / "legend.tex")
    interaction = _read_tex_file(sections_dir / "interaction.tex")
    input_text = _read_tex_file(sections_dir / "input.tex")
    output_text = _read_tex_file(sections_dir / "output.tex")
    notes = _read_tex_file(sections_dir / "notes.tex")

    lines: list[str] = []
    lines.extend(["# Description", _tex_block_to_markdown(legend) if legend else "(No description provided)", ""])

    if is_interactive or interaction:
        lines.extend(["# Interaction", _tex_block_to_markdown(interaction) if interaction else "(No interaction provided)", ""])
    else:
        lines.extend(["# Format", ""])
        lines.extend(["## Input", _tex_block_to_markdown(input_text) if input_text else "(No input format provided)", ""])
        lines.extend(["## Output", _tex_block_to_markdown(output_text) if output_text else "(No output format provided)", ""])


    example_indices = sorted({
        m.group(1)
        for p in sections_dir.iterdir()
        if p.is_file() and (m := re.fullmatch(r"example\.(\d+)(\.a)?", p.name))
    })
    if example_indices:
        lines.extend(["# Samples", ""])
        for i, idx in enumerate(example_indices, start=1):
            in_path = sections_dir / f"example.{idx}"
            out_path = sections_dir / f"example.{idx}.a"
            if not in_path.exists() or not out_path.exists():
                continue
            lines.extend(
                [
                    f"```input{i}",
                    _normalize_newlines(in_path.read_text(encoding="utf-8", errors="ignore")).rstrip(),
                    "```",
                    "",
                    f"```output{i}",
                    _normalize_newlines(out_path.read_text(encoding="utf-8", errors="ignore")).rstrip(),
                    "```",
                    "",
                ]
            )

    if notes:
        lines.extend(["# Note", _tex_block_to_markdown(notes), ""])

    content = "\n".join(lines).strip()
    return content + "\n" if content else ""


def _read_tex_file(path: Path) -> str:
    if not path.exists():
        return ""
    return _normalize_newlines(path.read_text(encoding="utf-8", errors="ignore")).strip()


def _normalize_newlines(text: str) -> str:
    # Polygon section files commonly use CRLF or CR+escaped-LF sequences.
    # Only normalize actual line separators; do not rewrite TeX macros like \neq.
    return text.replace("\r\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")


def _tex_block_to_markdown(text: str) -> str:
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


def _strip_tex_comments(text: str) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        escaped = re.sub(r"\\%", "", line)
        idx = escaped.find("%")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


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


def _parse_includegraphics_width(opts: str) -> str | None:
    m = re.search(r"width\s*=\s*([0-9]+(?:\.[0-9]+)?\\?%)", opts)
    if not m:
        return None
    width = m.group(1).replace("\\", "")
    return width


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


def _html_to_markdown(text: str) -> str:
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


def _tex_to_markdown(text: str) -> str:
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


def _strip_tags(text: str) -> str:
    return re.sub(r"(?is)<[^>]+>", "", text)


def _extract_tests(base: Path, slug: str) -> list[TestCase]:
    test_dir = base / "tests"
    ins: dict[str, tuple[str, bytes]] = {}
    outs: dict[str, tuple[str, bytes]] = {}

    if not test_dir.exists():
        raise ValueError(f"{slug}: no tests under problems/{slug}/tests")

    for path in test_dir.iterdir():
        if not path.is_file():
            continue

        name = path.name
        if name.endswith(".a"):
            stem = name[:-2]
            if not stem:
                continue
            outs[stem] = (name, path.read_bytes())
            continue

        if name.endswith(".out"):
            stem = name[:-4]
            if not stem:
                continue
            outs[stem] = (name, path.read_bytes())
            continue

        if name.endswith(".in"):
            stem = name[:-3]
            if not stem:
                continue
            ins[stem] = (name, path.read_bytes())
            continue

        ins[name] = (name, path.read_bytes())

    keys = sorted(set(ins) | set(outs))
    if not keys:
        raise ValueError(f"{slug}: no tests under problems/{slug}/tests")

    cases: list[TestCase] = []
    for new_idx, key in enumerate(keys, start=1):
        input_item = ins.get(key)
        if input_item is None:
            raise ValueError(f"{slug}: missing input for test key {key}")
        output_item = outs.get(key)
        if output_item is None:
            raise ValueError(
                f"{slug}: missing answer for test key {key}; run with --run-doall or pre-generate tests"
            )

        input_name = f"{key}.in"
        output_name = f"{key}.out"
        cases.append(
            TestCase(
                index=new_idx,
                input_data=input_item[1],
                output_data=output_item[1],
                input_name=input_name,
                output_name=output_name,
            )
        )
    return cases


def _extract_additional_files(base: Path, statement_dir: Path | None) -> list[tuple[str, bytes]]:
    out: dict[str, bytes] = {}

    if statement_dir is not None and statement_dir.exists():
        for path in statement_dir.iterdir():
            if not path.is_file():
                continue
            if path.name in {"problem.tex", "problem.html", "problem-statement.css"}:
                continue
            out.setdefault(path.name, path.read_bytes())

    attach_dir = base / "attachments"
    if attach_dir.exists():
        for path in attach_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(attach_dir).as_posix()
            out.setdefault(rel, path.read_bytes())

    return sorted(out.items(), key=lambda x: x[0])


def _extract_testdata_files(base: Path, root: ET.Element, slug: str, *, is_interactive: bool) -> list[tuple[str, bytes]]:
    out: dict[str, bytes] = {}
    out_sources: dict[str, str] = {}

    def _add_rel_path(rel: str) -> None:
        rel_norm = PurePosixPath(rel).as_posix()
        path = base / PurePosixPath(rel_norm)
        if not path.exists() or not path.is_file():
            raise ValueError(f"{slug}: declared testdata file not found: {rel_norm}")

        flat_name = PurePosixPath(rel_norm).name
        if not flat_name:
            raise ValueError(f"{slug}: invalid declared testdata file path: {rel_norm}")

        if flat_name in out:
            if out_sources.get(flat_name) == rel_norm:
                return
            raise ValueError(f"{slug}: testdata filename collision after flatten: {flat_name}")

        out[flat_name] = path.read_bytes()
        out_sources[flat_name] = rel_norm

    def _declared_source_path(node: ET.Element) -> str:
        direct = (node.attrib.get("path") or "").strip()
        if direct:
            return direct
        source = node.find("source")
        if source is None:
            return ""
        return (source.attrib.get("path") or "").strip()

    for exe in root.findall("./files/executables/executable"):
        rel = _declared_source_path(exe)
        if rel:
            _add_rel_path(rel)

    for sol in root.findall("./assets/solutions/solution"):
        rel = _declared_source_path(sol)
        if rel:
            _add_rel_path(rel)

    if not is_interactive:
        checker = root.find("./assets/checker")
        if checker is not None:
            rel = _declared_source_path(checker)
            if rel:
                _add_rel_path(rel)

        default_rel = "files/check.cpp"
        default_checker = base / PurePosixPath(default_rel)
        if default_checker.exists() and default_checker.is_file():
            _add_rel_path(default_rel)

    return sorted(out.items(), key=lambda x: x[0])
