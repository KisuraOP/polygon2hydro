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
    zip_name = _safe_filename(problem.title or problem.slug) + ".zip"
    zip_path = output_dir / zip_name

    with tempfile.TemporaryDirectory(prefix="p2h-") as td:
        root = Path(td) / str(local_id)
        (root / "testdata").mkdir(parents=True, exist_ok=True)

        (root / "problem.yaml").write_text(_build_problem_yaml(pid, owner, problem.title, tags), encoding="utf-8")
        (root / "problem_zh.md").write_text(problem.statement_md, encoding="utf-8")
        (root / "testdata" / "config.yaml").write_text(_build_config_yaml(problem.time_ms, problem.memory_mb), encoding="utf-8")

        for case in problem.tests:
            idx = f"{case.index:02d}"
            (root / "testdata" / f"tests{idx}.in").write_bytes(case.input_data)
            (root / "testdata" / f"tests{idx}.out").write_bytes(case.output_data)

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


def _build_config_yaml(time_ms: int | None, memory_mb: int | None) -> str:
    lines = ["type: default"]
    if time_ms is not None:
        lines.append(f"time: {time_ms}ms")
    if memory_mb is not None:
        lines.append(f"memory: {memory_mb}MB")
    lines.append("subtasks: []")
    lines.append("")
    return "\n".join(lines)


def _safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*\n\r\t'
    cleaned = "".join("_" if ch in bad else ch for ch in name).strip()
    return cleaned or "problem"
