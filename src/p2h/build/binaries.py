"""Locating the programs a Polygon package ships for judging.

Polygon exports its own compiled binaries next to the sources: the interactor as
``files/interactor.exe``, the checker as ``check.exe`` and the model solutions as
``solutions/<name>.exe``. Two build-time steps need to run them:

* :mod:`p2h.build.crossrun`  hosts one interactor/solution dialogue (answers for
  ordinary interactive problems)
* :mod:`p2h.build.twopass`   hosts one dialogue per run (answers for run-twice
  problems)

The lookup rules are the same in both cases and live here once.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from p2h.polygon.judging import load_problem_xml


#: Solution tags in the order we would rather use them to produce answers.
_PREFERRED_TAGS = ("main", "accepted")

#: Tags that deliberately produce a wrong verdict; only used as a last resort.
_MISBEHAVING_TAGS = {"rejected", "wrong-answer", "time-limit-exceeded", "runtime-error"}


def declared_path(node: ET.Element) -> str:
    """The path declared on ``node`` itself or inside its ``<source>`` child."""
    direct = (node.attrib.get("path") or "").strip()
    if direct:
        return direct
    source = node.find("source")
    if source is None:
        return ""
    return (source.attrib.get("path") or "").strip()


def _with_exe_suffix(declared: str) -> str:
    return str(Path(declared).with_suffix(".exe")).replace("\\", "/")


def interactor_binary(problem_root: Path) -> str | None:
    """Declared interactor binary, as a posix path relative to the problem root."""
    root = load_problem_xml(problem_root)
    if root is None:
        return None
    node = root.find("./assets/interactor")
    if node is None:
        return None
    return _existing_binary(node, problem_root, default="files/interactor.exe")


def main_solution_binary(problem_root: Path) -> str | None:
    """The solution used to produce reference answers.

    Polygon lists every solution, including deliberately wrong ones. ``main`` is
    the model solution; ``accepted`` is a safe second choice; anything tagged as
    a wrong answer is never used unless it is all the package has.
    """
    root = load_problem_xml(problem_root)
    if root is None:
        return None

    ranked: list[tuple[int, int, str]] = []
    for index, solution in enumerate(root.findall("./assets/solutions/solution")):
        declared = declared_path(solution)
        if not declared:
            continue
        binary = _with_exe_suffix(declared)
        if not (problem_root / binary).exists():
            continue
        tag = (solution.attrib.get("tag") or "").strip()
        ranked.append((_solution_rank(binary, tag), index, binary))

    if not ranked:
        return None
    ranked.sort()
    return ranked[0][2]


def _solution_rank(binary: str, tag: str) -> int:
    if tag in _PREFERRED_TAGS:
        return _PREFERRED_TAGS.index(tag)
    # A binary named ``should_wa``/``should_re`` is proof the solution is wrong.
    if Path(binary).stem.startswith("should_") or tag in _MISBEHAVING_TAGS:
        return 100
    return len(_PREFERRED_TAGS)


def checker_binary(problem_root: Path) -> str | None:
    """Declared checker binary, or ``None``.

    Used for self-checks only: judging never needs it, because the generated
    Hydro interactor carries the checker source inside itself.
    """
    root = load_problem_xml(problem_root)
    if root is None:
        return None
    node = root.find("./assets/checker")
    if node is None:
        return None
    return _existing_binary(node, problem_root, default=None)


def _existing_binary(node: ET.Element, problem_root: Path, *, default: str | None) -> str | None:
    candidates: list[str] = []
    declared = declared_path(node)
    if declared:
        candidates.append(_with_exe_suffix(declared))
    if default:
        candidates.append(default)
    for candidate in candidates:
        if (problem_root / candidate).exists():
            return candidate
    return None


def test_inputs(problem_root: Path) -> list[Path]:
    """Every test input file, in Polygon's ordering (zero-padded names)."""
    tests_dir = problem_root / "tests"
    if not tests_dir.exists():
        return []
    return sorted(
        (path for path in tests_dir.iterdir() if path.is_file() and not _is_answer(path)),
        key=lambda path: path.name,
    )


def pending_inputs(problem_root: Path) -> list[Path]:
    """Only the inputs that still have no answer file."""
    return [path for path in test_inputs(problem_root) if not _has_answer(path)]


def _is_answer(path: Path) -> bool:
    # ``.a`` and ``.out`` are both answer spellings; either one is enough.
    return path.name.endswith((".a", ".out"))


def _has_answer(test_file: Path) -> bool:
    return test_file.with_name(test_file.name + ".a").exists() or test_file.with_name(
        test_file.name + ".out"
    ).exists()
