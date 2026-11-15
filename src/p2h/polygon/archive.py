"""Unpacking a contest zip and discovering the problems inside it."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path, PurePosixPath


def safe_extract(contest_zip: Path, work_root: Path) -> list[str]:
    """Extract ``contest_zip`` under ``work_root``; return the entry names.

    Every entry is checked against the workspace: absolute paths, ``..`` and
    anything that resolves outside ``work_root`` are rejected before a single
    byte is written, so a hostile package cannot escape the temp directory.
    """
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


def list_slugs(names: list[str]) -> list[str]:
    """Problem slugs declared by ``problems/<slug>/...`` zip entries."""
    slugs: set[str] = set()
    for name in names:
        if not name.startswith("problems/"):
            continue
        parts = PurePosixPath(name).parts
        if len(parts) >= 3:
            slugs.add(parts[1])
    return sorted(slugs)
