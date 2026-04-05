from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from p2h import __version__
from p2h.convert import _detect_contest_statement_language, convert_contest
from p2h.polygon_reader import _extract_interactive_meta, _extract_statement_markdown
from p2h.statement_markdown import html_to_markdown, tex_block_to_markdown, tex_to_markdown


_PID_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def _parse_pid_start(value: str) -> tuple[str, int, int]:
    m = _PID_RE.match(value)
    if not m:
        raise argparse.ArgumentTypeError("--pid-start must look like P1145")
    prefix, digits = m.groups()
    return prefix, int(digits), len(digits)


def _flatten_only(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        parts = [x.strip() for x in v.split(",") if x.strip()]
        out.extend(parts)
    # preserve order and remove duplicates
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="p2h")
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser("convert", help="convert polygon contest zip to hydro zips")
    p_convert.add_argument("contest_zip", type=Path)
    p_convert.add_argument("-o", "--output", type=Path, required=True)
    p_convert.add_argument("--pid-start", type=_parse_pid_start, required=True)
    p_convert.add_argument("--owner", type=int, default=1)
    p_convert.add_argument("--tag", action="append", default=[])
    p_convert.add_argument("--only", action="append", default=[], help="convert only specified problem slug(s); repeatable or comma-separated")
    p_convert.add_argument("--run-doall", dest="run_doall", action="store_true", default=True, help="run each problem's doall.sh to generate tests/answers (default: enabled)")
    p_convert.add_argument("--no-run-doall", dest="run_doall", action="store_false", help="skip doall execution and use pre-generated tests only")
    p_convert.add_argument("--verbose", action="store_true")
    p_convert.add_argument(
        "--missing-env",
        choices=["warn", "ask", "error"],
        default="warn",
        help="behavior when doall precheck finds missing tools: warn (default), ask, or error",
    )

    p_stmt = sub.add_parser("statement-md", help="convert statement source (html/tex) to markdown")
    p_stmt.add_argument("input_path", type=Path)
    p_stmt.add_argument("--type", dest="statement_type", choices=["auto", "html", "tex", "tex-block"], default="auto")
    p_stmt.add_argument("--lang", choices=["auto", "chinese", "english"], default="auto")
    p_stmt.add_argument("-o", "--output", type=Path)

    return parser


def _infer_statement_type(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".tex":
        return "tex"
    return None


def _render_statement_markdown(path: Path, statement_type: str) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if statement_type == "html":
        return html_to_markdown(text)
    if statement_type == "tex":
        return tex_to_markdown(text)
    if statement_type == "tex-block":
        content = tex_block_to_markdown(text)
        return (content + "\n") if content and not content.endswith("\n") else content
    raise ValueError(f"unknown statement type: {statement_type}")


def _is_problem_directory(path: Path) -> bool:
    return path.is_dir() and (path / "problem.xml").exists()


def _resolve_statement_language_for_problem_dir(problem_dir: Path, lang: str) -> str | None:
    if lang in {"chinese", "english"}:
        return lang

    if problem_dir.parent.name == "problems":
        work_root = problem_dir.parent.parent
        return _detect_contest_statement_language(work_root)
    return None


def _render_statement_markdown_from_problem_dir(problem_dir: Path, lang: str) -> str:
    import xml.etree.ElementTree as ET

    xml_path = problem_dir / "problem.xml"
    if not xml_path.exists():
        raise ValueError(f"missing problem.xml under {problem_dir}")

    root = ET.fromstring(xml_path.read_bytes())
    statement_language = _resolve_statement_language_for_problem_dir(problem_dir, lang)
    is_interactive, _ = _extract_interactive_meta(root)
    md, _ = _extract_statement_markdown(
        problem_dir,
        root,
        is_interactive=is_interactive,
        statement_language=statement_language,
    )
    return md


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    print(f"p2h version: {__version__}")

    if args.command == "convert":
        summary = convert_contest(
            contest_zip=args.contest_zip,
            output_dir=args.output,
            pid_prefix=args.pid_start[0],
            pid_start_num=args.pid_start[1],
            pid_width=args.pid_start[2],
            owner=args.owner,
            tags=args.tag,
            only_slugs=_flatten_only(args.only),
            run_doall=args.run_doall,
            verbose=args.verbose,
            missing_env_policy=args.missing_env,
        )
        print(
            f"done: total={summary.total} success={summary.success} failed={summary.failed}",
            file=sys.stderr if summary.failed else sys.stdout,
        )
        if summary.failed:
            for line in summary.errors:
                print(f"- {line}", file=sys.stderr)
            return 1

    if args.command == "statement-md":
        if _is_problem_directory(args.input_path):
            rendered = _render_statement_markdown_from_problem_dir(args.input_path, args.lang)
            output_path = args.output or (args.input_path / "problem_zh.md")
            output_path.write_text(rendered, encoding="utf-8")
            return 0

        if args.input_path.is_dir():
            parser.error("input directory must contain problem.xml")

        statement_type = args.statement_type
        if statement_type == "auto":
            inferred = _infer_statement_type(args.input_path)
            if inferred is None:
                parser.error("cannot infer --type from input path; please set --type explicitly")
            statement_type = inferred

        rendered = _render_statement_markdown(args.input_path, statement_type)
        if args.output is None:
            sys.stdout.write(rendered)
        else:
            args.output.write_text(rendered, encoding="utf-8")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
