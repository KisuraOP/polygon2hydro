from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

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
    missing_env_policy: str = "warn",
) -> ConvertSummary:
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    success = 0

    with tempfile.TemporaryDirectory(prefix="p2h-contest-") as td:
        work_root = Path(td)
        try:
            names = _safe_extract_contest_zip(contest_zip, work_root)
        except Exception as exc:
            return ConvertSummary(
                total=0,
                success=0,
                failed=0,
                errors=[f"invalid contest zip: {exc}"],
            )
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

        total = len(slugs)
        start_pid = f"{pid_prefix}{pid_start_num:0{pid_width}d}"
        statement_language = _detect_contest_statement_language(work_root)
        print(
            f"start: total={total} output={output_dir} run_doall={'yes' if run_doall else 'no'} pid_start={start_pid}"
        )

        if run_doall:
            missing_tools = _detect_missing_doall_tools(work_root, slugs)
            if missing_tools:
                missing_text = ", ".join(missing_tools)
                msg = (
                    "missing environment tools for doall (precheck warning): "
                    f"{missing_text}; doall may still work in special environments"
                )
                if missing_env_policy == "error":
                    return ConvertSummary(
                        total=total,
                        success=0,
                        failed=total,
                        errors=[msg + "; abort due to --missing-env error"],
                    )

                print(f"warning: {msg}", file=sys.stderr)
                if missing_env_policy == "ask":
                    if not _confirm_continue_after_missing_env(missing_tools):
                        return ConvertSummary(
                            total=total,
                            success=0,
                            failed=total,
                            errors=["user aborted after missing environment warning"],
                        )

            try:
                _run_doall_for_all(work_root, slugs, verbose=verbose)
            except Exception as exc:
                return ConvertSummary(
                    total=total,
                    success=0,
                    failed=total,
                    errors=[f"doall failed: {exc}"],
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
                errors.append(f"{slug}: {exc}")
                print(f"[{idx}/{total}] ERROR {slug}: {exc}")

    total = len(slugs)
    return ConvertSummary(total=total, success=success, failed=total - success, errors=errors)


def _detect_contest_statement_language(work_root: Path) -> Literal["chinese", "english"] | None:
    statements_root = work_root / "statements"
    if not statements_root.exists() or not statements_root.is_dir():
        return None

    if (statements_root / "chinese").exists():
        return "chinese"
    if (statements_root / "english").exists():
        return "english"
    return None


def _safe_extract_contest_zip(contest_zip: Path, work_root: Path) -> list[str]:
    work_root_resolved = work_root.resolve()
    with zipfile.ZipFile(contest_zip) as zf:
        names = zf.namelist()
        for info in zf.infolist():
            raw_name = info.filename
            rel_path = PurePosixPath(raw_name)

            if rel_path.is_absolute():
                raise ValueError(f"zip contains absolute path: {raw_name}")

            if any(part in {"", ".", ".."} for part in rel_path.parts):
                raise ValueError(f"zip contains unsafe path: {raw_name}")

            target = work_root / Path(*rel_path.parts)
            target_resolved = target.resolve()
            if target_resolved != work_root_resolved and work_root_resolved not in target_resolved.parents:
                raise ValueError(f"zip path escapes workspace: {raw_name}")

            if info.is_dir() or raw_name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)

        return names


def _detect_missing_doall_tools(work_root: Path, slugs: list[str]) -> list[str]:
    tools: set[str] = set()

    for slug in slugs:
        problem_root = work_root / "problems" / slug
        _collect_tools_from_script(problem_root / "doall.sh", tools)

        scripts_dir = problem_root / "scripts"
        if scripts_dir.exists():
            for path in scripts_dir.rglob("*.sh"):
                if path.is_file():
                    _collect_tools_from_script(path, tools)

    return [t for t in sorted(tools) if shutil.which(t) is None]


def _collect_tools_from_script(script_path: Path, tools: set[str]) -> None:
    if not script_path.exists() or not script_path.is_file():
        return

    shell_keywords = {
        "if",
        "then",
        "fi",
        "for",
        "do",
        "done",
        "case",
        "esac",
        "while",
        "until",
        "function",
        "local",
        "export",
        "unset",
        "readonly",
        "eval",
        "echo",
        "read",
        "rm",
        "mv",
        "cp",
        "mkdir",
        "cd",
        "test",
        "true",
        "false",
        "exit",
        "return",
        "set",
        "shift",
        "source",
        ".",
        "in",
    }

    text = script_path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", stripped):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{?", stripped):
            continue

        if re.search(r"(^|\s)wine\s", stripped):
            tools.add("wine")
        if re.search(r"(^|\s)java\s", stripped):
            tools.add("java")
        if re.search(r"(^|\s)javac\s", stripped):
            tools.add("javac")

        try:
            first = shlex.split(stripped, posix=True)[0]
        except Exception:
            continue

        if first in shell_keywords:
            continue
        if first in {"bash", "sh"}:
            continue
        if first.startswith("scripts/"):
            continue
        if first.startswith("$"):
            continue
        if first.startswith("./") or first.startswith("../"):
            continue

        tools.add(first)


def _confirm_continue_after_missing_env(missing_tools: list[str]) -> bool:
    prompt = (
        "missing environment precheck warning for doall: "
        f"{', '.join(missing_tools)}. Continue anyway? [y/N]: "
    )
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return False
    return ans in {"y", "yes"}


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
