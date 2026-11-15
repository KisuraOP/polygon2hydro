"""Contest orchestration: unpack, filter, build, package.

This module only wires the layers together, one problem at a time:

* :mod:`p2h.polygon`  reading a Polygon contest package
* :mod:`p2h.build`    running the package's own build scripts
* :mod:`p2h.hydro`    writing the Hydro problem package
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from p2h.build.doall import precheck_doall, run_doall_for_all
from p2h.build.platform import host_label
from p2h.hydro.package import write_problem_zip
from p2h.polygon.archive import list_slugs, safe_extract
from p2h.polygon.problem import read_problem
from p2h.polygon.statement import detect_contest_language


@dataclass(slots=True)
class ConvertSummary:
    total: int
    success: int
    failed: int
    errors: list[str] = field(default_factory=list)


def convert_contest(
    *,
    contest_zip: Path,
    output_dir: Path,
    pid_prefix: str,
    pid_start_num: int,
    pid_width: int,
    owner: int,
    tags: list[str],
    only_slugs: list[str] | None = None,
    run_doall: bool = True,
    verbose: bool = False,
    missing_env_policy: str = "warn",
    interactive_runner: str = "auto",
) -> ConvertSummary:
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    success = 0

    with tempfile.TemporaryDirectory(prefix="p2h-contest-") as td:
        work_root = Path(td)
        try:
            names = safe_extract(contest_zip, work_root)
        except Exception as exc:
            return ConvertSummary(
                total=0,
                success=0,
                failed=0,
                errors=[f"invalid contest zip: {exc}"],
            )
        all_slugs = list_slugs(names)

        slugs = all_slugs
        if only_slugs:
            slug_set = set(all_slugs)
            missing = [s for s in only_slugs if s not in slug_set]
            if missing:
                return ConvertSummary(
                    total=0,
                    success=0,
                    failed=0,
                    errors=[f"unknown slug(s): {', '.join(missing)}"],
                )
            slugs = only_slugs

        total = len(slugs)
        start_pid = f"{pid_prefix}{pid_start_num:0{pid_width}d}"
        statement_language = detect_contest_language(work_root)
        print(
            f"start: total={total} output={output_dir} run_doall={'yes' if run_doall else 'no'} pid_start={start_pid}"
        )
        if verbose:
            print(f"host: {host_label()}")

        doall_failures: dict[str, str] = {}
        if run_doall:
            abort_reason = precheck_doall(work_root, slugs, missing_env_policy)
            if abort_reason is not None:
                return ConvertSummary(total=total, success=0, failed=total, errors=[abort_reason])
            doall_failures = run_doall_for_all(
                work_root, slugs, verbose=verbose, interactive_runner=interactive_runner
            )

        for idx, slug in enumerate(slugs, start=1):
            pid_num = pid_start_num + idx - 1
            pid = f"{pid_prefix}{pid_num:0{pid_width}d}"
            print(f"[{idx}/{total}] {slug} (pid={pid})")
            try:
                problem = read_problem(work_root, slug, verbose=verbose, statement_language=statement_language)
                out_path = write_problem_zip(
                    problem=problem,
                    output_dir=output_dir,
                    local_id=idx,
                    pid=pid,
                    owner=owner,
                    tags=tags,
                )
                success += 1
                print(f"[{idx}/{total}] OK {slug} -> {out_path}")
            except Exception as exc:
                message = f"{slug}: {exc}"
                if slug in doall_failures:
                    message += f" (doall failed: {doall_failures[slug]})"
                errors.append(message)
                print(f"[{idx}/{total}] ERROR {slug}: {exc}")

    total = len(slugs)
    return ConvertSummary(total=total, success=success, failed=total - success, errors=errors)
