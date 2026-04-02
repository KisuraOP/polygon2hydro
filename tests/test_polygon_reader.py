from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h import polygon_reader as pr


class TestPolygonReader(unittest.TestCase):
    def test_list_problem_slugs(self) -> None:
        names = [
            "problems/a/problem.xml",
            "problems/b/tests/1",
            "problems/a/tests/1",
            "x/y",
        ]
        self.assertEqual(pr.list_problem_slugs_from_names(names), ["a", "b"])

    def test_sections_to_markdown_template(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "legend.tex").write_text(
                "题面\\n\\begin{center}\\includegraphics[width=80\\%]{1.png}\\end{center}",
                encoding="utf-8",
            )
            (d / "input.tex").write_text("输入格式", encoding="utf-8")
            (d / "output.tex").write_text("输出格式", encoding="utf-8")
            (d / "notes.tex").write_text("说明", encoding="utf-8")
            (d / "example.1").write_text("1 2\n", encoding="utf-8")
            (d / "example.1.a").write_text("3\n", encoding="utf-8")
            (d / "example.2").write_text("4\n", encoding="utf-8")
            (d / "example.2.a").write_text("5\n", encoding="utf-8")

            md = pr._sections_to_markdown(d)

            self.assertIn("# Description", md)
            self.assertIn("# Format", md)
            self.assertIn("## Input", md)
            self.assertIn("## Output", md)
            self.assertIn("# Samples", md)
            self.assertIn("```input1", md)
            self.assertIn("```output1", md)
            self.assertIn("```input2", md)
            self.assertIn("```output2", md)
            self.assertIn("# Note", md)
            self.assertIn('<img src="file://1.png" width="80%" />', md)

    def test_extract_tests_reindex_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            t = base / "tests"
            t.mkdir()
            (t / "3").write_bytes(b"in3\n")
            (t / "3.a").write_bytes(b"out3\n")
            (t / "10").write_bytes(b"in10\n")
            (t / "10.a").write_bytes(b"out10\n")

            cases = pr._extract_tests(base, "s")
            self.assertEqual([c.index for c in cases], [1, 2])
            self.assertEqual(cases[0].input_data, b"in3\n")
            self.assertEqual(cases[1].output_data, b"out10\n")

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            t = base / "tests"
            t.mkdir()
            (t / "1").write_bytes(b"in\n")
            with self.assertRaises(ValueError) as cm:
                pr._extract_tests(base, "s")
            self.assertIn("run with --run-doall", str(cm.exception))

    def test_extract_additional_files_merge(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            statement = base / "statement-sections" / "chinese"
            statement.mkdir(parents=True)
            (statement / "problem.tex").write_text("x", encoding="utf-8")
            (statement / "a.png").write_bytes(b"a")

            attach = base / "attachments" / "dir"
            attach.mkdir(parents=True)
            (attach / "b.txt").write_bytes(b"b")

            files = pr._extract_additional_files(base, statement)
            names = [n for n, _ in files]
            self.assertIn("a.png", names)
            self.assertIn("dir/b.txt", names)
            self.assertNotIn("problem.tex", names)


if __name__ == "__main__":
    unittest.main()
