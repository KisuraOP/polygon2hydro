from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from p2h.hydro import run_twice
from p2h.kinds import ProblemKind
from p2h.models import ProblemData


def write_problem_zip(
    *,
    problem: ProblemData,
    output_dir: Path,
    local_id: int,
    pid: str,
    owner: int,
    tags: list[str],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = _next_available_zip_path(output_dir, _safe_filename(problem.title or problem.slug))

    with tempfile.TemporaryDirectory(prefix="p2h-") as td:
        root = Path(td) / str(local_id)
        (root / "testdata").mkdir(parents=True, exist_ok=True)
        testdata_files = list(problem.testdata_files)
        interactor_name = problem.interactor_name
        if problem.kind.answer_source == "twopass":
            existing = {name for name, _ in testdata_files}
            for name, data in _build_adapter_files(problem):
                if name in existing:
                    raise ValueError(f"{problem.slug}: testdata file collision: {name}")
                testdata_files.append((name, data))
            interactor_name = run_twice.ADAPTER_FILENAME

        # newline="\n" keeps the package byte-identical on Windows and POSIX:
        # without it write_text() would translate \n to \r\n on Windows.
        (root / "problem.yaml").write_text(
            _build_problem_yaml(pid, owner, problem.title, tags), encoding="utf-8", newline="\n"
        )
        (root / "problem_zh.md").write_text(problem.statement_md, encoding="utf-8", newline="\n")
        (root / "testdata" / "config.yaml").write_text(
            _build_config_yaml(
                problem.time_ms,
                problem.memory_mb,
                test_files=[
                    (
                        case.input_name or f"tests{case.index:02d}.in",
                        case.output_name or f"tests{case.index:02d}.out",
                    )
                    for case in problem.tests
                ],
                kind=problem.kind,
                interactor_name=interactor_name,
                checker_name=problem.checker_name,
                run_count=problem.run_count,
            ),
            encoding="utf-8",
            newline="\n",
        )

        for case in problem.tests:
            input_name = case.input_name or f"tests{case.index:02d}.in"
            output_name = case.output_name or f"tests{case.index:02d}.out"
            (root / "testdata" / input_name).write_bytes(case.input_data)
            (root / "testdata" / output_name).write_bytes(case.output_data)

        for name, data in testdata_files:
            target = root / "testdata" / name
            if target.exists():
                raise ValueError(f"{problem.slug}: testdata file collision: {name}")
            target.write_bytes(data)

        if problem.additional_files:
            add_dir = root / "additional_file"
            add_dir.mkdir(parents=True, exist_ok=True)
            for name, data in problem.additional_files:
                target = add_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in root.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(root.parent).as_posix())

    return zip_path


def _build_adapter_files(problem: ProblemData) -> list[tuple[str, bytes]]:
    """The generated interactor source that judges a run-twice problem."""
    if problem.interactor_source is None or problem.checker_source is None:
        raise ValueError(
            f"{problem.slug}: run-twice problem is missing its interactor/checker source"
        )
    source = run_twice.build_adapter_source(
        interactor_source=problem.interactor_source,
        checker_source=problem.checker_source,
        run_count=problem.run_count,
        interactor_runs=problem.interactor_runs,
    )
    return [(run_twice.ADAPTER_FILENAME, source.encode("utf-8"))]


def _build_problem_yaml(pid: str, owner: int, title: str, tags: list[str]) -> str:
    lines = [
        f"pid: {pid}",
        f"owner: {owner}",
        f"title: {title}",
        "tag:",
    ]
    if tags:
        lines.extend([f"  - '{t}'" for t in tags])
    lines.extend(["nSubmit: 0", "nAccept: 0", ""])
    return "\n".join(lines)


def _build_config_yaml(
    time_ms: int | None,
    memory_mb: int | None,
    test_files: list[tuple[str, str]],
    *,
    kind: ProblemKind,
    interactor_name: str | None,
    checker_name: str | None,
    run_count: int = 1,
) -> str:
    lines = [f"type: {kind.hydro_type}"]
    if kind.answer_source == "twopass":
        # Hydro runs the interactor once per pass; the generated interactor
        # emulates one Polygon run per pass.
        if run_count < 2:
            raise ValueError(f"{kind.key} problem needs at least 2 runs, got {run_count}")
        lines.append(f"multi_pass: {run_count}")
    if kind.needs_checker and not kind.needs_interactor:
        if not checker_name:
            raise ValueError(f"{kind.key} problem missing checker source filename")
        lines.append("checker_type: testlib")
        lines.append("checker:")
        lines.append(f"  file: {checker_name}")
    if kind.needs_interactor:
        if not interactor_name:
            raise ValueError(f"{kind.key} problem missing interactor source filename")
        lines.append(f"interactor: {interactor_name}")
    if time_ms is not None:
        lines.append(f"time: {time_ms}ms")
    if memory_mb is not None:
        lines.append(f"memory: {memory_mb}MB")
    lines.extend(
        [
            "subtasks:",
            "  - score: 100",
            "    if: []",
            "    id: 1",
            "    type: min",
            "    cases:",
        ]
    )
    for input_name, output_name in test_files:
        lines.extend(
            [
                f"      - input: {input_name}",
                f"        output: {output_name}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _next_available_zip_path(output_dir: Path, base_name: str) -> Path:
    first = output_dir / f"{base_name}.zip"
    if not first.exists():
        return first

    i = 2
    while True:
        candidate = output_dir / f"{base_name} ({i}).zip"
        if not candidate.exists():
            return candidate
        i += 1


def _safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*\n\r\t'
    cleaned = "".join("_" if ch in bad else ch for ch in name).strip()
    return cleaned or "problem"
