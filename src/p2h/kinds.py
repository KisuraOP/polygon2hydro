"""Problem kinds: everything that differs between traditional / interactive / ...

Polygon's ``problem.xml`` says what it takes to judge a problem. The project
currently meets three kinds, and output-only ("submit answer") problems are
expected next. Instead of growing ``if is_interactive`` branches in the reader,
the writer and the build code, every difference is described once, here, as
data:

=====================  ===============  =========  ==========  =============
kind                   hydro type       checker    interactor  answer source
=====================  ===============  =========  ==========  =============
``traditional``        default          required   absent      one solution per test
``interactive``        interactive      absent     required    one dialogue per test
``communication``      interactive      embedded   generated   one dialogue per run
=====================  ===============  =========  ==========  =============

``communication`` is Polygon's run-twice problem: ``run-count`` runs per test,
some of them interactive, with a checker that sees the last run (see
:mod:`p2h.polygon.judging`).  Hydro's native representation of sequential
multi-run problems is the ``multi_pass`` option of the ``interactive`` type: the
judge restarts the interactor once per pass, hands the expected answer (the
normal testdata ``output`` file) to it every pass, and forwards ``nextpass.in``
as the next pass's input.  A generated interactor emulates one Polygon run per
pass and embeds the problem's own interactor and checker (see
:mod:`p2h.hydro.run_twice`).  ``needs_checker`` stays true because the checker
source is still required, even though the Hydro config carries no ``checker``.

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

from p2h.polygon.judging import load_problem_xml, parse_judging


#: How the expected-answer files are produced during conversion.
#: ``solution``   run one solution per test (traditional)
#: ``interactor`` host a dialogue between interactor and solution (interactive)
#: ``twopass``    host one dialogue per run of a run-twice problem
#: ``provided``   the package already ships them (output-only problems)
AnswerSource = Literal["solution", "interactor", "twopass", "provided"]


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
    min_run_count: int = 1
    max_run_count: int | None = None
    #: Hydro's native sequential multi-run judging (``multi_pass``): a generated
    #: interactor emulates one Polygon run per pass and the expected answer is
    #: delivered through the normal testdata ``output`` file.
    needs_multi_pass: bool = False

    def accepts(self, run_count: int) -> bool:
        if run_count < self.min_run_count:
            return False
        return self.max_run_count is None or run_count <= self.max_run_count


TRADITIONAL = ProblemKind(
    key="traditional",
    hydro_type="default",
    uses_interaction_section=False,
    needs_checker=True,
    needs_interactor=False,
    answer_source="solution",
    marker="./assets/checker",
    max_run_count=1,
)

INTERACTIVE = ProblemKind(
    key="interactive",
    hydro_type="interactive",
    uses_interaction_section=True,
    needs_checker=False,
    needs_interactor=True,
    answer_source="interactor",
    marker="./assets/interactor",
    max_run_count=1,
)

COMMUNICATION = ProblemKind(
    key="communication",
    hydro_type="interactive",
    uses_interaction_section=False,
    needs_checker=True,
    needs_interactor=True,
    answer_source="twopass",
    marker="./assets/interactor",
    min_run_count=2,
    needs_multi_pass=True,
)

#: Detection order: the first kind whose marker and run count match wins.
KINDS: tuple[ProblemKind, ...] = (COMMUNICATION, INTERACTIVE, TRADITIONAL)

#: Used when no marker matches (a package without any assets).
FALLBACK: ProblemKind = TRADITIONAL


def detect(root: ET.Element) -> ProblemKind:
    """Classify a parsed ``problem.xml``."""
    run_count = parse_judging(root).run_count
    for kind in KINDS:
        if not kind.accepts(run_count):
            continue
        if kind.marker is None or root.find(kind.marker) is not None:
            return kind
    return FALLBACK


def detect_from_dir(problem_dir: Path) -> ProblemKind:
    """Classify a problem directory, falling back when ``problem.xml`` is absent."""
    root = load_problem_xml(problem_dir)
    if root is None:
        return FALLBACK
    return detect(root)


def by_key(key: str) -> ProblemKind | None:
    for kind in KINDS:
        if kind.key == key:
            return kind
    return None
