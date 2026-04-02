from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TestCase:
    index: int
    input_data: bytes
    output_data: bytes


@dataclass(slots=True)
class ProblemData:
    slug: str
    title: str
    time_ms: int | None
    memory_mb: int | None
    statement_md: str
    tests: list[TestCase] = field(default_factory=list)
    additional_files: list[tuple[str, bytes]] = field(default_factory=list)
