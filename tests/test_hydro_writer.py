from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.hydro_writer import write_problem_zip
from p2h.models import ProblemData, TestCase


class TestHydroWriter(unittest.TestCase):
    def test_write_problem_zip_layout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            problem = ProblemData(
                slug="demo",
                title="题目A",
                time_ms=2000,
                memory_mb=256,
                statement_md="# Description\nhello\n",
                tests=[
                    TestCase(index=1, input_data=b"1 2\n", output_data=b"3\n"),
                    TestCase(index=2, input_data=b"2 3\n", output_data=b"5\n"),
                ],
                additional_files=[("a.png", b"png"), ("dir/b.txt", b"b")],
                testdata_files=[("gen.cpp", b"gen"), ("std.cpp", b"std")],
            )

            zip_path = write_problem_zip(
                problem=problem,
                output_dir=out_dir,
                local_id=1,
                pid="P1000",
                owner=1,
                tags=["tag1"],
            )

            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                self.assertIn("1/problem.yaml", names)
                self.assertIn("1/problem_zh.md", names)
                self.assertIn("1/testdata/config.yaml", names)
                self.assertIn("1/testdata/tests01.in", names)
                self.assertIn("1/testdata/tests01.out", names)
                self.assertIn("1/testdata/tests02.in", names)
                self.assertIn("1/testdata/tests02.out", names)
                self.assertIn("1/testdata/gen.cpp", names)
                self.assertIn("1/testdata/std.cpp", names)
                self.assertIn("1/additional_file/a.png", names)
                self.assertIn("1/additional_file/dir/b.txt", names)

                problem_yaml = zf.read("1/problem.yaml").decode()
                self.assertIn("pid: P1000", problem_yaml)
                self.assertIn("owner: 1", problem_yaml)
                self.assertIn("title: 题目A", problem_yaml)
                self.assertIn("  - 'tag1'", problem_yaml)
                self.assertIn("nSubmit: 0", problem_yaml)
                self.assertIn("nAccept: 0", problem_yaml)

                config_yaml = zf.read("1/testdata/config.yaml").decode()
                self.assertIn("type: default", config_yaml)
                self.assertIn("time: 2000ms", config_yaml)
                self.assertIn("memory: 256MB", config_yaml)
                self.assertIn("subtasks:", config_yaml)
                self.assertIn("  - score: 100", config_yaml)
                self.assertIn("    if: []", config_yaml)
                self.assertIn("    id: 1", config_yaml)
                self.assertIn("    type: min", config_yaml)
                self.assertIn("    cases:", config_yaml)
                self.assertIn("      - input: tests01.in", config_yaml)
                self.assertIn("        output: tests01.out", config_yaml)
                self.assertIn("      - input: tests02.in", config_yaml)
                self.assertIn("        output: tests02.out", config_yaml)

    def test_write_problem_zip_interactive_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            problem = ProblemData(
                slug="guess-the-number",
                title="猜数字",
                time_ms=1000,
                memory_mb=256,
                statement_md="# Description\n\n# Interaction\n\n# Samples\n",
                tests=[TestCase(index=1, input_data=b"1\n", output_data=b"2\n")],
                is_interactive=True,
                interactor_name="inter.cc",
            )

            zip_path = write_problem_zip(
                problem=problem,
                output_dir=out_dir,
                local_id=1,
                pid="P1001",
                owner=1,
                tags=[],
            )

            with zipfile.ZipFile(zip_path) as zf:
                config_yaml = zf.read("1/testdata/config.yaml").decode()
                self.assertIn("type: interactive", config_yaml)
                self.assertIn("interactor: inter.cc", config_yaml)
                self.assertIn("time: 1000ms", config_yaml)
                self.assertIn("memory: 256MB", config_yaml)
                self.assertIn("subtasks:", config_yaml)
                self.assertIn("  - score: 100", config_yaml)
                self.assertIn("    if: []", config_yaml)
                self.assertIn("    id: 1", config_yaml)
                self.assertIn("    type: min", config_yaml)
                self.assertIn("    cases:", config_yaml)
                self.assertIn("      - input: tests01.in", config_yaml)
                self.assertIn("        output: tests01.out", config_yaml)

    def test_write_problem_zip_interactive_missing_interactor_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            problem = ProblemData(
                slug="guess-the-number",
                title="猜数字",
                time_ms=1000,
                memory_mb=256,
                statement_md="# Description\n",
                tests=[TestCase(index=1, input_data=b"1\n", output_data=b"2\n")],
                is_interactive=True,
                interactor_name=None,
            )

            with self.assertRaises(ValueError) as cm:
                write_problem_zip(
                    problem=problem,
                    output_dir=out_dir,
                    local_id=1,
                    pid="P1001",
                    owner=1,
                    tags=[],
                )
            self.assertIn("interactive problem missing interactor source filename", str(cm.exception))

    def test_write_problem_zip_avoids_overwrite_when_same_title(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            problem = ProblemData(
                slug="demo",
                title="同名题目",
                time_ms=1000,
                memory_mb=256,
                statement_md="# Description\n",
                tests=[TestCase(index=1, input_data=b"1\n", output_data=b"1\n")],
            )

            first = write_problem_zip(
                problem=problem,
                output_dir=out_dir,
                local_id=1,
                pid="P1000",
                owner=1,
                tags=[],
            )
            second = write_problem_zip(
                problem=problem,
                output_dir=out_dir,
                local_id=2,
                pid="P1001",
                owner=1,
                tags=[],
            )

            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertNotEqual(first, second)
            self.assertEqual(first.name, "同名题目.zip")
            self.assertEqual(second.name, "同名题目 (2).zip")


if __name__ == "__main__":
    unittest.main()
