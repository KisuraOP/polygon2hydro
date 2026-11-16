"""Run-twice judging metadata from ``problem.xml``.

Two attributes describe how Polygon judges a problem, and both change what the
converter has to emit:

``<judging run-count="N">``
    How many times the participant's program is executed.

``<interactor><runs><run>k</run>...</runs></interactor>``
    Which runs are interactive, i.e. where the interactor runs next to the
    participant and talks over pipes.  Runs that are not listed are plain:
    the participant reads the run's input file and its stdout becomes the next
    run's input.  The element is omitted for ordinary interactive problems,
    which means "run 1".
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class JudgingInfo:
    run_count: int = 1
    #: Runs whose interface is interactive.  Always ``{1}`` for a plain
    #: interactive problem and empty for a traditional one.
    interactor_runs: frozenset[int] = frozenset()

    @property
    def is_run_twice(self) -> bool:
        return self.run_count > 1


def load_problem_xml(problem_root: Path) -> ET.Element | None:
    """Parse ``problem.xml``; ``None`` when it is missing or unreadable."""
    xml_path = problem_root / "problem.xml"
    if not xml_path.exists():
        return None
    try:
        return ET.fromstring(xml_path.read_bytes())
    except ET.ParseError:
        return None


def read_judging_info(problem_root: Path) -> JudgingInfo:
    root = load_problem_xml(problem_root)
    if root is None:
        return JudgingInfo()
    return parse_judging(root)


def parse_judging(root: ET.Element) -> JudgingInfo:
    run_count = _parse_run_count(root)
    return JudgingInfo(run_count=run_count, interactor_runs=_parse_interactor_runs(root, run_count))


def _parse_run_count(root: ET.Element) -> int:
    judging = root.find("./judging")
    if judging is None:
        return 1
    raw = (judging.attrib.get("run-count") or "").strip()
    if not raw.isdigit():
        return 1
    return max(1, int(raw))


def _parse_interactor_runs(root: ET.Element, run_count: int) -> frozenset[int]:
    interactor = root.find("./assets/interactor")
    if interactor is None:
        return frozenset()
    runs_node = interactor.find("runs")
    if runs_node is None:
        # A plain interactive problem: one run, one interactor invocation.
        return frozenset({1})

    runs: set[int] = set()
    for node in runs_node.findall("run"):
        text = (node.text or "").strip()
        if not text.isdigit():
            continue
        run = int(text)
        if 1 <= run <= run_count:
            runs.add(run)
    return frozenset(runs)
