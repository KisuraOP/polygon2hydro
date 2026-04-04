from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from p2h.models import ProblemData, TestCase
from p2h.statement_markdown import html_to_markdown, tex_block_to_markdown, tex_to_markdown


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")


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
                return html_to_markdown(html_path.read_text(encoding="utf-8", errors="ignore")), html_path.parent

        if tex_rel:
            tex_path = base / PurePosixPath(tex_rel)
            if tex_path.exists():
                return tex_to_markdown(tex_path.read_text(encoding="utf-8", errors="ignore")), tex_path.parent

    return "# Description\n\n(Statement not found)\n", None


def _sections_to_markdown(sections_dir: Path, *, is_interactive: bool) -> str:
    legend = _read_tex_file(sections_dir / "legend.tex")
    interaction = _read_tex_file(sections_dir / "interaction.tex")
    input_text = _read_tex_file(sections_dir / "input.tex")
    output_text = _read_tex_file(sections_dir / "output.tex")
    notes = _read_tex_file(sections_dir / "notes.tex")

    lines: list[str] = []
    lines.extend(["# Description", tex_block_to_markdown(legend) if legend else "(No description provided)", ""])

    if is_interactive or interaction:
        lines.extend(["# Interaction", tex_block_to_markdown(interaction) if interaction else "(No interaction provided)", ""])
    else:
        lines.extend(["# Format", ""])
        lines.extend(["## Input", tex_block_to_markdown(input_text) if input_text else "(No input format provided)", ""])
        lines.extend(["## Output", tex_block_to_markdown(output_text) if output_text else "(No output format provided)", ""])


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
        lines.extend(["# Note", tex_block_to_markdown(notes), ""])

    content = "\n".join(lines).strip()
    return content + "\n" if content else ""


def _read_tex_file(path: Path) -> str:
    if not path.exists():
        return ""
    return _normalize_newlines(path.read_text(encoding="utf-8", errors="ignore")).strip()


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
