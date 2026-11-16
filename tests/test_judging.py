from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.polygon import judging


def _xml(body: str):
    return judging.ET.fromstring(f"<problem>{body}</problem>")


INTERACTOR = '<assets><interactor><source path="files/interactor.cpp"/></interactor></assets>'


class TestJudgingInfo(unittest.TestCase):
    def test_defaults_without_judging_element(self) -> None:
        info = judging.parse_judging(_xml(""))
        self.assertEqual(info.run_count, 1)
        self.assertEqual(info.interactor_runs, frozenset())
        self.assertFalse(info.is_run_twice)

    def test_run_twice_reads_run_count(self) -> None:
        info = judging.parse_judging(_xml('<judging run-count="2"><testset/></judging>'))
        self.assertEqual(info.run_count, 2)
        self.assertTrue(info.is_run_twice)

    def test_missing_run_count_defaults_to_one(self) -> None:
        self.assertEqual(judging.parse_judging(_xml("<judging/>")).run_count, 1)

    def test_non_numeric_run_count_defaults_to_one(self) -> None:
        self.assertEqual(judging.parse_judging(_xml('<judging run-count="two"/>')).run_count, 1)

    def test_interactive_problem_without_runs_means_first_run(self) -> None:
        info = judging.parse_judging(_xml('<judging run-count="2"/>' + INTERACTOR))
        self.assertEqual(info.interactor_runs, frozenset({1}))

    def test_explicit_runs_are_read(self) -> None:
        body = (
            '<judging run-count="3"/>'
            '<assets><interactor><runs><run>1</run><run>3</run></runs></interactor></assets>'
        )
        info = judging.parse_judging(_xml(body))
        self.assertEqual(info.interactor_runs, frozenset({1, 3}))

    def test_runs_outside_the_run_count_are_dropped(self) -> None:
        body = (
            '<judging run-count="2"/>'
            '<assets><interactor><runs><run>1</run><run>5</run><run>0</run></runs></interactor>'
            "</assets>"
        )
        self.assertEqual(judging.parse_judging(_xml(body)).interactor_runs, frozenset({1}))

    def test_non_numeric_runs_are_dropped(self) -> None:
        body = (
            '<judging run-count="2"/>'
            '<assets><interactor><runs><run>1</run><run>second</run></runs></interactor></assets>'
        )
        self.assertEqual(judging.parse_judging(_xml(body)).interactor_runs, frozenset({1}))

    def test_traditional_problem_has_no_interactor_runs(self) -> None:
        info = judging.parse_judging(_xml('<judging run-count="2"/><assets><checker/></assets>'))
        self.assertEqual(info.interactor_runs, frozenset())

    def test_read_from_dir_without_problem_xml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(judging.read_judging_info(Path(td)).run_count, 1)

    def test_read_from_dir_with_broken_problem_xml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "problem.xml").write_text("<problem", encoding="utf-8")
            info = judging.read_judging_info(Path(td))
            self.assertEqual(info.run_count, 1)


if __name__ == "__main__":
    unittest.main()
