from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from p2h.convert import convert_contest


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
        )
        print(
            f"done: total={summary.total} success={summary.success} failed={summary.failed}",
            file=sys.stderr if summary.failed else sys.stdout,
        )
        if summary.failed:
            for line in summary.errors:
                print(f"- {line}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
