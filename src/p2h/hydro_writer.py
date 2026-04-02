from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

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

        (root / "problem.yaml").write_text(_build_problem_yaml(pid, owner, problem.title, tags), encoding="utf-8")
        (root / "problem_zh.md").write_text(problem.statement_md, encoding="utf-8")
        (root / "testdata" / "config.yaml").write_text(
            _build_config_yaml(
                problem.time_ms,
                problem.memory_mb,
                is_interactive=problem.is_interactive,
                interactor_name=problem.interactor_name,
            ),
            encoding="utf-8",
        )

        for case in problem.tests:
            idx = f"{case.index:02d}"
            (root / "testdata" / f"tests{idx}.in").write_bytes(case.input_data)
            (root / "testdata" / f"tests{idx}.out").write_bytes(case.output_data)

        if problem.testdata_files:
            for name, data in problem.testdata_files:
                target = root / "testdata" / name
                if target.exists():
                    raise ValueError(f"testdata file collision: {name}")
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
    *,
    is_interactive: bool,
    interactor_name: str | None,
) -> str:
    lines = ["type: interactive" if is_interactive else "type: default"]
    if is_interactive:
        if not interactor_name:
            raise ValueError("interactive problem missing interactor source filename")
        lines.append(f"interactor: {interactor_name}")
    if time_ms is not None:
        lines.append(f"time: {time_ms}ms")
    if memory_mb is not None:
        lines.append(f"memory: {memory_mb}MB")
    lines.append("subtasks: []")
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
