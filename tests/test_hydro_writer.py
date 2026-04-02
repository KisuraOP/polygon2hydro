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
                self.assertIn("subtasks: []", config_yaml)


if __name__ == "__main__":
    unittest.main()
