from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.build import crossrun


PROBLEM_XML = """<problem>
  <assets>
    <interactor type="cpp"><source path="files/interactor.cpp"/></interactor>
    <solutions>
      <solution tag="wa"><source path="solutions/should_wa.cpp"/></solution>
      <solution tag="main"><source path="solutions/foo.cpp"/></solution>
    </solutions>
  </assets>
</problem>"""


def _problem(td: str, *, jar: bool = True, exe: bool = True, solutions: bool = True) -> Path:
    root = Path(td)
    (root / "files").mkdir(parents=True, exist_ok=True)
    (root / "solutions").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "problem.xml").write_text(PROBLEM_XML, encoding="utf-8")
    if jar:
        (root / "files" / "CrossRun.jar").write_bytes(b"jar")
    if exe:
        (root / "files" / "interactor.exe").write_bytes(b"exe")
    if solutions:
        (root / "solutions" / "foo.exe").write_bytes(b"exe")
        (root / "solutions" / "should_wa.exe").write_bytes(b"exe")
    return root


class TestApplicability(unittest.TestCase):
    def test_true_when_everything_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            with mock.patch("shutil.which", return_value="/usr/bin/java"):
                self.assertTrue(crossrun.is_applicable(root))

    def test_false_without_jar(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td, jar=False)
            with mock.patch("shutil.which", return_value="/usr/bin/java"):
                self.assertFalse(crossrun.is_applicable(root))

    def test_false_without_java(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            with mock.patch("shutil.which", return_value=None):
                self.assertFalse(crossrun.is_applicable(root))

    def test_false_for_traditional_problem(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "problem.xml").write_text("<problem><assets/></problem>", encoding="utf-8")
            (root / "files").mkdir()
            (root / "files" / "CrossRun.jar").write_bytes(b"jar")
            with mock.patch("shutil.which", return_value="/usr/bin/java"):
                self.assertFalse(crossrun.is_applicable(root))


class TestBinarySelection(unittest.TestCase):
    def test_picks_interactor_and_skips_deliberately_wrong_solutions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            self.assertEqual(
                crossrun._binaries(root),
                ("files/interactor.exe", "solutions/foo.exe"),
            )

    def test_none_when_interactor_binary_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td, exe=False)
            self.assertIsNone(crossrun._binaries(root))


class TestPendingInputs(unittest.TestCase):
    def test_only_inputs_without_answers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            tests = root / "tests"
            (tests / "01").write_text("1\n", encoding="utf-8")
            (tests / "01.a").write_text("", encoding="utf-8")
            (tests / "02").write_text("2\n", encoding="utf-8")
            (tests / "02.out").write_text("2\n", encoding="utf-8")
            (tests / "03").write_text("3\n", encoding="utf-8")

            names = [p.name for p in crossrun._pending_inputs(root)]
            self.assertEqual(names, ["03"])


class TestCommand(unittest.TestCase):
    def test_no_wine_prefix_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            with mock.patch.object(crossrun, "IS_WINDOWS", True):
                cmd = crossrun._crossrun_command(
                    root, "files/interactor.exe", "solutions/foo.exe",
                    root / "tests" / "01", root / ".p2h-01.out",
                )
            interactor_cmd, solution_cmd = cmd[-2], cmd[-1]
            self.assertFalse(interactor_cmd.startswith("wine "))
            self.assertEqual(interactor_cmd, "files/interactor.exe tests/01 .p2h-01.out")
            self.assertEqual(solution_cmd, "solutions/foo.exe")

    def test_wine_prefix_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            with mock.patch.object(crossrun, "IS_WINDOWS", False):
                cmd = crossrun._crossrun_command(
                    root, "files/interactor.exe", "solutions/foo.exe",
                    root / "tests" / "01", root / ".p2h-01.out",
                )
            self.assertTrue(cmd[-2].startswith("wine files/interactor.exe "))
            self.assertEqual(cmd[-1], "wine solutions/foo.exe")


class TestGenerateAnswers(unittest.TestCase):
    def test_returns_none_when_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td, jar=False)
            with mock.patch("shutil.which", return_value="/usr/bin/java"):
                self.assertIsNone(crossrun.generate_answers(root))

    def test_no_pending_inputs_is_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            with mock.patch("shutil.which", return_value="/usr/bin/java"):
                self.assertEqual(crossrun.generate_answers(root), {})

    def test_writes_answer_from_scratch_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            test_file = root / "tests" / "01"
            test_file.write_text("12\n", encoding="utf-8")

            def fake_run(command, **kwargs):
                (root / ".p2h-01.out").write_bytes(b"")
                return mock.Mock(returncode=0, stdout="Completed", stderr="")

            with mock.patch("shutil.which", return_value="/usr/bin/java"), \
                    mock.patch.object(crossrun.subprocess, "run", side_effect=fake_run):
                self.assertEqual(crossrun.generate_answers(root), {})

            self.assertTrue((root / "tests" / "01.a").exists())
            self.assertFalse((root / ".p2h-01.out").exists())

    def test_failure_is_reported_and_scratch_removed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(td)
            (root / "tests" / "01").write_text("12\n", encoding="utf-8")

            def fake_run(command, **kwargs):
                return mock.Mock(returncode=1, stdout="", stderr="boom\n")

            with mock.patch("shutil.which", return_value="/usr/bin/java"), \
                    mock.patch.object(crossrun.subprocess, "run", side_effect=fake_run):
                failures = crossrun.generate_answers(root)

            self.assertIn("01", failures)
            self.assertIn("boom", failures["01"])
            self.assertFalse((root / "tests" / "01.a").exists())


if __name__ == "__main__":
    unittest.main()
