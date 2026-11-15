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

from p2h.build import platform as env


class TestDoallEntryPoint(unittest.TestCase):
    """The host decides between doall.bat and doall.sh. Nothing else may."""

    def _problem_dir(self, td: str, *names: str) -> Path:
        root = Path(td)
        for name in names:
            (root / name).write_text("rem/echo\n", encoding="utf-8")
        return root

    def test_windows_prefers_bat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = self._problem_dir(td, "doall.sh", "doall.bat")
            with mock.patch.object(env, "IS_WINDOWS", True):
                self.assertEqual(env.doall_command(root), ["cmd", "/c", "doall.bat"])

    def test_posix_prefers_sh(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = self._problem_dir(td, "doall.sh", "doall.bat")
            with mock.patch.object(env, "IS_WINDOWS", False):
                self.assertEqual(env.doall_command(root), ["bash", "doall.sh"])

    def test_windows_falls_back_to_sh_when_bat_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = self._problem_dir(td, "doall.sh")
            with mock.patch.object(env, "IS_WINDOWS", True):
                self.assertEqual(env.doall_command(root), ["bash", "doall.sh"])

    def test_returns_none_when_no_script_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(env, "IS_WINDOWS", True):
                self.assertIsNone(env.doall_command(Path(td)))

    def test_script_kind_matches_the_command(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = self._problem_dir(td, "doall.sh", "doall.bat")
            with mock.patch.object(env, "IS_WINDOWS", True):
                self.assertEqual(env.doall_script_kind(root), ".bat")
                self.assertEqual(env.doall_command(root)[0], env.CMD_RUNNER)
            with mock.patch.object(env, "IS_WINDOWS", False):
                self.assertEqual(env.doall_script_kind(root), ".sh")
                self.assertEqual(env.doall_command(root)[0], env.SH_RUNNER)

    def test_host_label_mentions_the_entry_point(self) -> None:
        with mock.patch.object(env, "IS_WINDOWS", True):
            self.assertIn("doall.bat", env.host_label())
        with mock.patch.object(env, "IS_WINDOWS", False):
            self.assertIn("doall.sh", env.host_label())


if __name__ == "__main__":
    unittest.main()
