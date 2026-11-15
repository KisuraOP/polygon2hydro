"""Problem kinds: everything that differs between traditional / interactive / ...

Polygon's ``problem.xml`` says what it takes to judge a problem. Today the
project meets two kinds, but output-only ("submit answer") and communication
problems are expected next. Instead of growing ``if is_interactive`` branches in
the reader, the writer and the build code, every difference is described once,
here, as data:

==========================  ============  ===========  =============
kind                        hydro type    checker      interactor
==========================  ============  ===========  =============
``traditional``             default       required     absent
``interactive``             interactive   absent       required
==========================  ============  ===========  =============

Adding a kind means adding one :class:`ProblemKind` instance with the right
flags (and, if its answers cannot come from a single solution, a new answer
source). The reader, the writer and the pipeline read the flags; they never
match on the kind's name.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


#: How the expected-answer files are produced during conversion.
#: ``solution``   run one solution per test (traditional)
#: ``interactor`` host a dialogue between interactor and solution (interactive)
#: ``provided``   the package already ships them (output-only problems)
AnswerSource = Literal["solution", "interactor", "provided"]


@dataclass(frozen=True, slots=True)
class ProblemKind:
    key: str
    hydro_type: str
    uses_interaction_section: bool
    needs_checker: bool
    needs_interactor: bool
    answer_source: AnswerSource
    #: XML path whose presence selects this kind; ``None`` marks the fallback.
    marker: str | None = None


TRADITIONAL = ProblemKind(
    key="traditional",
    hydro_type="default",
    uses_interaction_section=False,
    needs_checker=True,
    needs_interactor=False,
    answer_source="solution",
    marker="./assets/checker",
)

INTERACTIVE = ProblemKind(
    key="interactive",
    hydro_type="interactive",
    uses_interaction_section=True,
    needs_checker=False,
    needs_interactor=True,
    answer_source="interactor",
    marker="./assets/interactor",
)

#: Detection order: the first kind whose marker is present wins.
KINDS: tuple[ProblemKind, ...] = (INTERACTIVE, TRADITIONAL)

#: Used when no marker matches (a package without any assets).
FALLBACK: ProblemKind = TRADITIONAL


def detect(root: ET.Element) -> ProblemKind:
    """Classify a parsed ``problem.xml``."""
    for kind in KINDS:
        if kind.marker and root.find(kind.marker) is not None:
            return kind
    return FALLBACK


def detect_from_dir(problem_dir: Path) -> ProblemKind:
    """Classify a problem directory, falling back when ``problem.xml`` is absent."""
    xml_path = problem_dir / "problem.xml"
    if not xml_path.exists():
        return FALLBACK
    try:
        root = ET.fromstring(xml_path.read_bytes())
    except ET.ParseError:
        return FALLBACK
    return detect(root)


def by_key(key: str) -> ProblemKind | None:
    for kind in KINDS:
        if kind.key == key:
            return kind
    return None
