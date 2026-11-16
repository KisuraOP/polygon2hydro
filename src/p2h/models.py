from __future__ import annotations

from dataclasses import dataclass, field

from p2h.kinds import TRADITIONAL, ProblemKind


@dataclass(slots=True)
class TestCase:
    index: int
    input_data: bytes
    output_data: bytes
    input_name: str | None = None
    output_name: str | None = None


@dataclass(slots=True)
class ProblemData:
    slug: str
    title: str
    time_ms: int | None
    memory_mb: int | None
    statement_md: str
    tests: list[TestCase] = field(default_factory=list)
    additional_files: list[tuple[str, bytes]] = field(default_factory=list)
    testdata_files: list[tuple[str, bytes]] = field(default_factory=list)
    kind: ProblemKind = TRADITIONAL
    interactor_name: str | None = None
    checker_name: str | None = None
    #: Polygon's ``run-count``: how many times the participant is executed.
    run_count: int = 1
    #: Runs judged interactively (see :mod:`p2h.polygon.judging`).
    interactor_runs: frozenset[int] = frozenset()
    #: Sources of the problem's own interactor/checker, needed to build the
    #: Hydro adapter for a run-twice problem.
    interactor_source: str | None = None
    checker_source: str | None = None

    @property
    def is_interactive(self) -> bool:
        """True when the participant talks to an interactor (any kind)."""
        return self.kind.hydro_type == "interactive"
