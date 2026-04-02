from __future__ import annotations

import os
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from p2h.hydro_writer import write_problem_zip
from p2h.polygon_reader import list_problem_slugs_from_names, read_problem


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
) -> ConvertSummary:
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    success = 0

    with tempfile.TemporaryDirectory(prefix="p2h-contest-") as td:
        work_root = Path(td)
        with zipfile.ZipFile(contest_zip) as zf:
            names = zf.namelist()
            zf.extractall(work_root)
            all_slugs = list_problem_slugs_from_names(names)

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

        if run_doall:
            try:
                _run_doall_for_all(work_root, slugs, verbose=verbose)
            except Exception as exc:
                return ConvertSummary(
                    total=len(slugs),
                    success=0,
                    failed=len(slugs),
                    errors=[f"doall failed: {exc}"],
                )

        for idx, slug in enumerate(slugs, start=1):
            pid_num = pid_start_num + idx - 1
            pid = f"{pid_prefix}{pid_num:0{pid_width}d}"
            try:
                problem = read_problem(work_root, slug, verbose=verbose)
                out_path = write_problem_zip(
                    problem=problem,
                    output_dir=output_dir,
                    local_id=idx,
                    pid=pid,
                    owner=owner,
                    tags=tags,
                )
                success += 1
                if verbose:
                    print(f"[{slug}] -> {out_path}")
            except Exception as exc:
                errors.append(f"{slug}: {exc}")
                if verbose:
                    print(f"[{slug}] ERROR: {exc}")

    total = len(slugs)
    return ConvertSummary(total=total, success=success, failed=total - success, errors=errors)


def _run_doall_for_all(work_root: Path, slugs: list[str], *, verbose: bool) -> None:
    for slug in slugs:
        problem_root = work_root / "problems" / slug
        doall = problem_root / "doall.sh"
        if not doall.exists():
            if verbose:
                print(f"[{slug}] skip doall (missing doall.sh)")
            continue

        _make_scripts_executable(problem_root)

        if verbose:
            print(f"[{slug}] running doall.sh")
        env = os.environ.copy()
        env.setdefault("PATH", "/usr/bin:/bin:/usr/local/bin")
        subprocess.run(["bash", "doall.sh"], cwd=problem_root, check=True, env=env)
        if verbose:
            print(f"[{slug}] doall done")


def _make_scripts_executable(problem_root: Path) -> None:
    doall = problem_root / "doall.sh"
    if doall.exists():
        doall.chmod(doall.stat().st_mode | 0o111)

    scripts_dir = problem_root / "scripts"
    if scripts_dir.exists():
        for path in scripts_dir.rglob("*.sh"):
            if path.is_file():
                path.chmod(path.stat().st_mode | 0o111)

    files_dir = problem_root / "files"
    if files_dir.exists():
        for path in files_dir.iterdir():
            if path.is_file() and path.suffix in {".exe", ""}:
                path.chmod(path.stat().st_mode | 0o111)

    sols_dir = problem_root / "solutions"
    if sols_dir.exists():
        for path in sols_dir.iterdir():
            if path.is_file() and path.suffix in {".exe", ""}:
                path.chmod(path.stat().st_mode | 0o111)

    checker = problem_root / "check.exe"
    if checker.exists():
        checker.chmod(checker.stat().st_mode | 0o111)

    for extra in [problem_root / "statements", problem_root / "statement-sections"]:
        if extra.exists():
            for sh in extra.rglob("*.sh"):
                if sh.is_file():
                    sh.chmod(sh.stat().st_mode | 0o111)
