from __future__ import annotations

import contextlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.build import doall


def _problem(
    work: Path,
    slug: str,
    script: str = "doall.sh",
    body: str = "#!/bin/bash\n",
    *,
    interactive: bool = False,
) -> Path:
    root = work / "problems" / slug
    root.mkdir(parents=True, exist_ok=True)
    (root / script).write_text(body, encoding="utf-8")
    if interactive:
        (root / "problem.xml").write_text(
            '<problem><assets><interactor><source path="files/interactor.cpp"/>'
            "</interactor></assets></problem>",
            encoding="utf-8",
        )
    return root


class TestPrecheck(unittest.TestCase):
    def test_no_missing_tools_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a")
            with mock.patch("shutil.which", return_value="/usr/bin/fake"):
                self.assertIsNone(doall.precheck_doall(work, ["a"], "error"))

    def test_error_policy_aborts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", body="#!/bin/bash\nwine files/gen.exe\n")
            with mock.patch("shutil.which", return_value=None):
                reason = doall.precheck_doall(work, ["a"], "error")
            self.assertIn("wine", reason)
            self.assertIn("abort due to --missing-env error", reason)

    def test_warn_policy_warns_but_continues(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", body="#!/bin/bash\nwine files/gen.exe\n")
            err = io.StringIO()
            with mock.patch("shutil.which", return_value=None), contextlib.redirect_stderr(err):
                self.assertIsNone(doall.precheck_doall(work, ["a"], "warn"))
            self.assertIn("missing environment tools for doall", err.getvalue())

    def test_ask_policy_aborts_on_no(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", body="#!/bin/bash\nwine files/gen.exe\n")
            with mock.patch("shutil.which", return_value=None), mock.patch("builtins.input", return_value="n"):
                reason = doall.precheck_doall(work, ["a"], "ask")
            self.assertEqual(reason, "user aborted after missing environment warning")

    def test_ask_policy_continues_on_yes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", body="#!/bin/bash\nwine files/gen.exe\n")
            with mock.patch("shutil.which", return_value=None), mock.patch("builtins.input", return_value="y"):
                self.assertIsNone(doall.precheck_doall(work, ["a"], "ask"))
            with mock.patch("builtins.input", return_value="yes"):
                self.assertTrue(doall.confirm_continue_after_missing_env(["wine"]))
            with mock.patch("builtins.input", return_value="N"):
                self.assertFalse(doall.confirm_continue_after_missing_env(["wine"]))


class TestToolDetection(unittest.TestCase):
    def test_bat_builtins_are_not_tools(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(
                work,
                "a",
                script="doall.bat",
                body='rem tests\ncall scripts\\gen-answer.bat tests\\01 tests\\01.a "tests" ""\nset x=0\necho done\n',
            )
            with mock.patch("p2h.build.platform.IS_WINDOWS", True), mock.patch("shutil.which", return_value=None):
                self.assertEqual(doall.detect_missing_tools(work, ["a"]), [])

    def test_shell_keywords_are_not_tools(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(
                work,
                "a",
                body='#!/usr/bin/env bash\nindices=(1 2)\nfor i in "${indices[@]}"; do\n  scripts/gen-answer.sh "$i"\ndone\n',
            )
            with mock.patch("shutil.which", return_value=None):
                self.assertEqual(doall.detect_missing_tools(work, ["a"]), [])

    def test_wine_is_reported_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", body="#!/usr/bin/env bash\nwine files/gen.exe\n")
            with mock.patch("p2h.build.platform.IS_WINDOWS", False), mock.patch("shutil.which", return_value=None):
                self.assertEqual(doall.detect_missing_tools(work, ["a"]), ["wine"])

    def test_scripts_subdirectory_is_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            root = _problem(work, "a")
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "gen.sh").write_text("#!/bin/bash\njavac Main.java\n", encoding="utf-8")
            with mock.patch("p2h.build.platform.IS_WINDOWS", False), mock.patch("shutil.which", return_value=None):
                self.assertEqual(doall.detect_missing_tools(work, ["a"]), ["javac"])


class TestRunDoall(unittest.TestCase):
    def test_never_inherits_stdin(self) -> None:
        # Polygon's scripts call `read`/`pause` when something fails; inheriting
        # a tty would block the whole conversion forever.
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a")
            with mock.patch("p2h.build.doall.subprocess.run") as run:
                doall.run_doall_for_all(work, ["a"], verbose=False)
            self.assertTrue(run.called)
            self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_failure_is_recorded_and_rest_continue(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            for slug in ("a", "b"):
                _problem(work, slug)

            def fake_run(command, **kwargs):
                failed = kwargs["cwd"].name == "a"
                return mock.Mock(returncode=2 if failed else 0, stdout="", stderr="boom from a\n")

            with mock.patch("p2h.build.doall.subprocess.run", side_effect=fake_run):
                failures = doall.run_doall_for_all(work, ["a", "b"], verbose=False)

            self.assertEqual(list(failures), ["a"])
            self.assertIn("boom from a", failures["a"])

    def test_problem_without_script_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            (work / "problems" / "a").mkdir(parents=True)
            with mock.patch("p2h.build.doall.subprocess.run") as run:
                self.assertEqual(doall.run_doall_for_all(work, ["a"], verbose=False), {})
            run.assert_not_called()

    @unittest.skipIf(os.name == "nt", "Windows has no POSIX executable bit; chmod only toggles the read-only flag")
    def test_make_scripts_executable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files = [
                root / "doall.sh",
                root / "scripts" / "x.sh",
                root / "files" / "gen.exe",
                root / "solutions" / "std",
                root / "check.exe",
                root / "statements" / "a.sh",
                root / "statement-sections" / "b.sh",
            ]
            for p in files:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("echo ok\n", encoding="utf-8")
                p.chmod(0o644)

            doall.make_scripts_executable(root)

            for p in files:
                self.assertTrue(p.stat().st_mode & stat.S_IXUSR, p)


class TestInteractiveFallback(unittest.TestCase):
    """A failed package script may be rescued by CrossRun (auto mode)."""

    def _failing_run(self, work: Path):
        def fake_run(command, **kwargs):
            return mock.Mock(returncode=2, stdout="", stderr="window station denied\n")

        return fake_run

    def test_auto_falls_back_to_crossrun(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", interactive=True)
            with mock.patch("p2h.build.doall.subprocess.run", side_effect=self._failing_run(work)), \
                    mock.patch("p2h.build.crossrun.is_applicable", return_value=True), \
                    mock.patch("p2h.build.crossrun.generate_answers", return_value={}) as gen:
                failures = doall.run_doall_for_all(work, ["a"], verbose=False, interactive_runner="auto")

            self.assertEqual(failures, {})
            gen.assert_called_once()

    def test_package_mode_never_uses_crossrun(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", interactive=True)
            with mock.patch("p2h.build.doall.subprocess.run", side_effect=self._failing_run(work)), \
                    mock.patch("p2h.build.crossrun.is_applicable", return_value=True), \
                    mock.patch("p2h.build.crossrun.generate_answers") as gen:
                failures = doall.run_doall_for_all(work, ["a"], verbose=False, interactive_runner="package")

            self.assertIn("a", failures)
            gen.assert_not_called()

    def test_crossrun_failure_is_appended_to_the_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", interactive=True)
            with mock.patch("p2h.build.doall.subprocess.run", side_effect=self._failing_run(work)), \
                    mock.patch("p2h.build.crossrun.is_applicable", return_value=True), \
                    mock.patch("p2h.build.crossrun.generate_answers", return_value={"01": "boom"}):
                failures = doall.run_doall_for_all(work, ["a"], verbose=False, interactive_runner="auto")

            self.assertIn("window station denied", failures["a"])
            self.assertIn("crossrun failed", failures["a"])

    def test_crossrun_mode_skips_the_package_script(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _problem(work, "a", interactive=True)
            with mock.patch("p2h.build.doall.subprocess.run") as run, \
                    mock.patch("p2h.build.crossrun.is_applicable", return_value=True), \
                    mock.patch("p2h.build.crossrun.generate_answers", return_value={}):
                failures = doall.run_doall_for_all(work, ["a"], verbose=False, interactive_runner="crossrun")

            self.assertEqual(failures, {})
            run.assert_not_called()


RUN_TWICE_XML = """\
<problem>
  <judging run-count="2"/>
  <assets>
    <checker type="testlib"><source path="files/check.cpp"/></checker>
    <interactor><source path="files/interactor.cpp"/><runs><run>1</run></runs></interactor>
  </assets>
</problem>
"""


def _run_twice_problem(work: Path, slug: str = "comm") -> Path:
    root = _problem(work, slug, body="#!/bin/bash\nexit 0\n")
    (root / "problem.xml").write_text(RUN_TWICE_XML, encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "gen-answer.sh").write_text(
        "#!/bin/bash\njava -jar files/CrossRun.jar 'wine files/inter.exe tests/01 out.txt'\n",
        encoding="utf-8",
    )
    (scripts / "gen-answer.bat").write_text(
        "@echo off\r\njava -jar files\\CrossRun.jar ...\r\n", encoding="utf-8"
    )
    return root


class TestAnswerScriptReplacement(unittest.TestCase):
    def test_run_twice_answer_scripts_are_neutralized(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _run_twice_problem(Path(td))
            doall.replace_answer_scripts(root)
            shell = (root / "scripts" / "gen-answer.sh").read_text(encoding="utf-8")
            batch = (root / "scripts" / "gen-answer.bat").read_bytes()
            self.assertTrue(shell.startswith("#!/usr/bin/env bash"))
            self.assertIn("exit 0", shell)
            self.assertNotIn("CrossRun", shell)
            self.assertIn(b"exit /b 0", batch)
            self.assertNotIn(b"CrossRun", batch)

    def test_problem_without_scripts_directory_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _problem(Path(td), "plain")
            doall.replace_answer_scripts(root)  # must not raise


class TestRunTwiceAnswers(unittest.TestCase):
    def _run(self, twopass_result):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            _run_twice_problem(work)
            info = doall.judging.JudgingInfo(run_count=2, interactor_runs=frozenset({1}))
            with mock.patch.object(doall, "_run_scripts_for_slug", return_value=None), \
                    mock.patch.object(doall.judging, "read_judging_info", return_value=info), \
                    mock.patch.object(doall, "replace_answer_scripts") as replace, \
                    mock.patch.object(
                        doall.twopass, "generate_answers", return_value=twopass_result
                    ) as generate:
                failures = doall.run_doall_for_all(work, ["comm"], verbose=False)
            return failures, replace, generate

    def test_successful_generation_clears_the_build(self) -> None:
        failures, replace, generate = self._run({})
        self.assertEqual(failures, {})
        replace.assert_called_once()
        generate.assert_called_once()
        self.assertEqual(generate.call_args.kwargs["run_count"], 2)
        self.assertEqual(generate.call_args.kwargs["interactor_runs"], frozenset({1}))

    def test_failed_generation_is_reported(self) -> None:
        failures, _, _ = self._run({"01": "boom"})
        self.assertIn("run-twice answers failed for 1 test(s), e.g. 01: boom", failures["comm"])

    def test_unusable_binaries_are_reported(self) -> None:
        failures, _, _ = self._run(None)
        self.assertIn("cannot generate run-twice answers", failures["comm"])


if __name__ == "__main__":
    unittest.main()
