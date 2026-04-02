from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h import cli
from p2h.convert import ConvertSummary


class TestCliHelpers(unittest.TestCase):
    def test_parse_pid_start_valid(self) -> None:
        self.assertEqual(cli._parse_pid_start("P1145"), ("P", 1145, 4))
        self.assertEqual(cli._parse_pid_start("ABC001"), ("ABC", 1, 3))

    def test_parse_pid_start_invalid(self) -> None:
        with self.assertRaises(Exception):
            cli._parse_pid_start("1145")
        with self.assertRaises(Exception):
            cli._parse_pid_start("P")

    def test_flatten_only(self) -> None:
        values = ["a,b", "b", "c , d", "a"]
        self.assertEqual(cli._flatten_only(values), ["a", "b", "c", "d"])


class TestCliMain(unittest.TestCase):
    def test_main_passes_arguments_to_convert(self) -> None:
        captured: dict[str, object] = {}

        def fake_convert(**kwargs: object) -> ConvertSummary:
            captured.update(kwargs)
            return ConvertSummary(total=1, success=1, failed=0)

        with mock.patch("p2h.cli.convert_contest", side_effect=fake_convert):
            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(
                    [
                        "convert",
                        "contest.zip",
                        "-o",
                        "out",
                        "--pid-start",
                        "P1000",
                        "--owner",
                        "7",
                        "--tag",
                        "x",
                        "--tag",
                        "y",
                        "--only",
                        "a,b",
                        "--only",
                        "c",
                        "--no-run-doall",
                        "--verbose",
                    ]
                )

        self.assertEqual(code, 0)
        self.assertEqual(captured["pid_prefix"], "P")
        self.assertEqual(captured["pid_start_num"], 1000)
        self.assertEqual(captured["pid_width"], 4)
        self.assertEqual(captured["owner"], 7)
        self.assertEqual(captured["tags"], ["x", "y"])
        self.assertEqual(captured["only_slugs"], ["a", "b", "c"])
        self.assertEqual(captured["run_doall"], False)
        self.assertEqual(captured["verbose"], True)
        self.assertIn("done: total=1 success=1 failed=0", out.getvalue())

    def test_main_returns_error_code_when_failed(self) -> None:
        with mock.patch(
            "p2h.cli.convert_contest",
            return_value=ConvertSummary(total=1, success=0, failed=1, errors=["x: bad"]),
        ):
            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["convert", "contest.zip", "-o", "out", "--pid-start", "P1000"])

        self.assertEqual(code, 1)
        self.assertIn("done: total=1 success=0 failed=1", err.getvalue())
        self.assertIn("- x: bad", err.getvalue())


if __name__ == "__main__":
    unittest.main()
