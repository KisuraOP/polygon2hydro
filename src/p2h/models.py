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

    @property
    def is_interactive(self) -> bool:
        """Convenience predicate; prefer reading ``kind`` flags directly."""
        return self.kind.answer_source == "interactor"
