from __future__ import annotations

import contextlib
import io
import sys
import tempfile
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
    def test_statement_md_stdout_auto_html(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "statement.html"
            inp.write_text("<p>Hello</p>", encoding="utf-8")

            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["statement-md", str(inp)])

        self.assertEqual(code, 0)
        self.assertIn("p2h version:", out.getvalue())
        self.assertIn("# Description", out.getvalue())
        self.assertIn("Hello", out.getvalue())

    def test_statement_md_write_output_tex_block(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "legend.txt"
            outp = Path(td) / "out.md"
            inp.write_text(r"\\begin{itemize}\\item A\\item B\\end{itemize}", encoding="utf-8")

            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["statement-md", str(inp), "--type", "tex-block", "-o", str(outp)])

            self.assertTrue(outp.exists())
            rendered = outp.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("p2h version:", out.getvalue())
        self.assertIn("- A", rendered)
        self.assertIn("- B", rendered)

    def test_statement_md_auto_infer_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "statement.unknown"
            inp.write_text("x", encoding="utf-8")

            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    cli.main(["statement-md", str(inp)])

        self.assertEqual(cm.exception.code, 2)
        self.assertIn("cannot infer --type", err.getvalue())

    def test_statement_md_problem_dir_default_writes_problem_zh(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "problems" / "a"
            (root / "statements" / "english").mkdir(parents=True)
            (base / "statement-sections" / "chinese").mkdir(parents=True)
            (base / "statement-sections" / "english").mkdir(parents=True)
            (base / "problem.xml").write_text(
                """
                <problem>
                  <assets>
                    <checker type=\"testlib\"><source path=\"files/check.cpp\"/></checker>
                  </assets>
                </problem>
                """,
                encoding="utf-8",
            )
            (base / "statement-sections" / "chinese" / "legend.tex").write_text("中文题面", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "input.tex").write_text("中文输入", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "output.tex").write_text("中文输出", encoding="utf-8")
            (base / "statement-sections" / "english" / "legend.tex").write_text("English statement", encoding="utf-8")
            (base / "statement-sections" / "english" / "input.tex").write_text("Input format", encoding="utf-8")
            (base / "statement-sections" / "english" / "output.tex").write_text("Output format", encoding="utf-8")

            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["statement-md", str(base)])

            output_file = base / "problem_zh.md"
            self.assertTrue(output_file.exists())
            rendered = output_file.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("English statement", rendered)
        self.assertIn("# Format", rendered)

    def test_statement_md_problem_dir_lang_override(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "problems" / "a"
            (root / "statements" / "english").mkdir(parents=True)
            (base / "statement-sections" / "chinese").mkdir(parents=True)
            (base / "statement-sections" / "english").mkdir(parents=True)
            (base / "problem.xml").write_text("<problem></problem>", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "legend.tex").write_text("中文题面", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "input.tex").write_text("中文输入", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "output.tex").write_text("中文输出", encoding="utf-8")
            (base / "statement-sections" / "english" / "legend.tex").write_text("English statement", encoding="utf-8")
            (base / "statement-sections" / "english" / "input.tex").write_text("Input format", encoding="utf-8")
            (base / "statement-sections" / "english" / "output.tex").write_text("Output format", encoding="utf-8")

            code = cli.main(["statement-md", str(base), "--lang", "chinese"])
            rendered = (base / "problem_zh.md").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("中文题面", rendered)
        self.assertNotIn("English statement", rendered)

    def test_statement_md_problem_dir_with_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "problems" / "a"
            outp = root / "custom.md"
            (base / "statement-sections" / "chinese").mkdir(parents=True)
            (base / "problem.xml").write_text("<problem></problem>", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "legend.tex").write_text("中文题面", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "input.tex").write_text("中文输入", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "output.tex").write_text("中文输出", encoding="utf-8")

            code = cli.main(["statement-md", str(base), "-o", str(outp)])
            self.assertEqual(code, 0)
            self.assertTrue(outp.exists())
            self.assertIn("中文题面", outp.read_text(encoding="utf-8"))

    def test_statement_md_directory_without_problem_xml_errors(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    cli.main(["statement-md", str(d)])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("must contain problem.xml", err.getvalue())

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
        self.assertEqual(captured["missing_env_policy"], "warn")
        self.assertIn("p2h version:", out.getvalue())
        self.assertIn("done: total=1 success=1 failed=0", out.getvalue())

    def test_main_passes_missing_env_choice(self) -> None:
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
                        "--missing-env",
                        "ask",
                    ]
                )

        self.assertEqual(code, 0)
        self.assertEqual(captured["missing_env_policy"], "ask")

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
        self.assertIn("p2h version:", out.getvalue())
        self.assertIn("done: total=1 success=0 failed=1", err.getvalue())
        self.assertIn("- x: bad", err.getvalue())


if __name__ == "__main__":
    unittest.main()
