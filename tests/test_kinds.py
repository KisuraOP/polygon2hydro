from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h import kinds
from p2h.hydro.package import _build_config_yaml
from p2h.polygon import problem as pr


def _xml(body: str):
    return pr.ET.fromstring(f"<problem>{body}</problem>")


INTERACTOR = '<assets><interactor><source path="files/interactor.cpp"/></interactor></assets>'
CHECKER = '<assets><checker type="testlib"><source path="files/check.cpp"/></checker></assets>'


class TestDetection(unittest.TestCase):
    def test_interactive_marker(self) -> None:
        self.assertIs(kinds.detect(_xml(INTERACTOR)), kinds.INTERACTIVE)

    def test_traditional_marker(self) -> None:
        self.assertIs(kinds.detect(_xml(CHECKER)), kinds.TRADITIONAL)

    def test_interactive_wins_when_both_are_present(self) -> None:
        # Real interactive problems often declare a checker as well; the
        # interactor must win, otherwise judging metadata would be wrong.
        both = '<assets><checker type="testlib"><source path="files/ck.cpp"/></checker>' \
               '<interactor><source path="files/interactor.cpp"/></interactor></assets>'
        self.assertIs(kinds.detect(_xml(both)), kinds.INTERACTIVE)

    def test_missing_assets_falls_back(self) -> None:
        self.assertIs(kinds.detect(_xml("")), kinds.FALLBACK)

    def test_detect_from_dir_without_problem_xml(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertIs(kinds.detect_from_dir(Path(td)), kinds.FALLBACK)

    def test_by_key(self) -> None:
        self.assertIs(kinds.by_key("interactive"), kinds.INTERACTIVE)
        self.assertIsNone(kinds.by_key("nope"))


class TestFutureKindNeedsNoCodeChange(unittest.TestCase):
    """A new kind is data. The writer and the reader must follow the flags."""

    SUBMIT_ANSWER = kinds.ProblemKind(
        key="submit-answer",
        hydro_type="submit_answer",
        uses_interaction_section=False,
        needs_checker=False,
        needs_interactor=False,
        answer_source="provided",
        marker="./assets/submit-answer",
    )

    def test_config_yaml_is_driven_by_flags(self) -> None:
        config = _build_config_yaml(
            1000,
            256,
            [("01.in", "01.out")],
            kind=self.SUBMIT_ANSWER,
            interactor_name=None,
            checker_name=None,
        )
        self.assertIn("type: submit_answer", config)
        self.assertNotIn("checker", config)
        self.assertNotIn("interactor", config)
        self.assertIn("      - input: 01.in", config)

    def test_statement_layout_is_driven_by_flags(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sections = Path(td)
            (sections / "legend.tex").write_text("legend", encoding="utf-8")
            (sections / "input.tex").write_text("input", encoding="utf-8")
            (sections / "output.tex").write_text("output", encoding="utf-8")

            md = pr._sections_to_markdown(sections, kind=self.SUBMIT_ANSWER)
            self.assertIn("# Format", md)
            self.assertNotIn("# Interaction", md)

    def test_config_yaml_reports_missing_required_source(self) -> None:
        with self.assertRaises(ValueError) as cm:
            _build_config_yaml(
                1000, 256, [], kind=kinds.TRADITIONAL, interactor_name=None, checker_name=None
            )
        self.assertIn("traditional problem missing checker source filename", str(cm.exception))

        with self.assertRaises(ValueError) as cm:
            _build_config_yaml(
                1000, 256, [], kind=kinds.INTERACTIVE, interactor_name=None, checker_name=None
            )
        self.assertIn("interactive problem missing interactor source filename", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
