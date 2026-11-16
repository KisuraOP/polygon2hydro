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

from p2h.hydro import run_twice
from p2h.hydro.package import write_problem_zip
from p2h.models import ProblemData, TestCase
from p2h.kinds import COMMUNICATION, INTERACTIVE, TRADITIONAL


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
                checker_name="check.cpp",
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
                self.assertIn("checker_type: testlib", config_yaml)
                self.assertIn("checker:", config_yaml)
                self.assertIn("  file: check.cpp", config_yaml)
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
                kind=INTERACTIVE,
                interactor_name="inter.cc",
                checker_name=None,
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
                self.assertNotIn("checker_type:", config_yaml)
                self.assertNotIn("checker:", config_yaml)
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
                kind=INTERACTIVE,
                interactor_name=None,
                checker_name=None,
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
                checker_name="check.cpp",
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

    def test_generated_text_uses_lf_on_every_platform(self) -> None:
        # Windows write_text() would otherwise emit CRLF, making the package
        # differ byte-for-byte between hosts.
        with tempfile.TemporaryDirectory() as td:
            problem = ProblemData(
                slug="demo",
                title="题目A",
                time_ms=1000,
                memory_mb=256,
                statement_md="# Description\n\nhello\n",
                tests=[TestCase(index=1, input_data=b"1\n", output_data=b"2\n")],
                checker_name="check.cpp",
            )
            zip_path = write_problem_zip(
                problem=problem, output_dir=Path(td) / "out", local_id=1,
                pid="P1000", owner=1, tags=["t"],
            )
            with zipfile.ZipFile(zip_path) as zf:
                for name in ("1/problem.yaml", "1/problem_zh.md", "1/testdata/config.yaml"):
                    data = zf.read(name)
                    self.assertNotIn(b"\r\n", data, name)
                    self.assertIn(b"\n", data, name)

    def test_write_problem_zip_traditional_missing_checker_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            problem = ProblemData(
                slug="normal",
                title="普通题",
                time_ms=1000,
                memory_mb=256,
                statement_md="# Description\n",
                tests=[TestCase(index=1, input_data=b"1\n", output_data=b"2\n")],
                kind=TRADITIONAL,
                checker_name=None,
            )

            with self.assertRaises(ValueError) as cm:
                write_problem_zip(
                    problem=problem,
                    output_dir=out_dir,
                    local_id=1,
                    pid="P1002",
                    owner=1,
                    tags=[],
                )
            self.assertIn("traditional problem missing checker source filename", str(cm.exception))


class TestRunTwicePackage(unittest.TestCase):
    def _problem(self, **overrides) -> ProblemData:
        fields = dict(
            slug="interval-sum",
            title="区间和",
            time_ms=1000,
            memory_mb=1024,
            statement_md="# Description\n\n# Format\n",
            tests=[TestCase(index=1, input_data=b"cat 1\n", output_data=b"5\n")],
            kind=COMMUNICATION,
            interactor_name="inter.cpp",
            checker_name="check.cpp",
            run_count=2,
            interactor_runs=frozenset({1}),
            interactor_source="#include \"testlib.h\"\nint main() { return 0; }\n",
            checker_source="#include \"testlib.h\"\nint main() { return 0; }\n",
        )
        fields.update(overrides)
        return ProblemData(**fields)

    def _write(self, problem: ProblemData) -> Path:
        td = tempfile.mkdtemp()
        return write_problem_zip(
            problem=problem,
            output_dir=Path(td) / "out",
            local_id=1,
            pid="P4000",
            owner=1,
            tags=[],
        )

    def test_config_runs_the_generated_interactor_multiple_times(self) -> None:
        zip_path = self._write(self._problem())
        with zipfile.ZipFile(zip_path) as zf:
            config = zf.read("1/testdata/config.yaml").decode()
            self.assertIn("type: interactive", config)
            self.assertIn("multi_pass: 2", config)
            self.assertIn("interactor: p2h_interactor.cpp", config)
            # Hydro's interactive judge never reads a ``checker`` entry: the
            # checker source is embedded into the generated interactor instead.
            self.assertNotIn("checker_type:", config)
            self.assertNotIn("checker:", config)

            names = set(zf.namelist())
            self.assertIn("1/testdata/p2h_interactor.cpp", names)
            adapter = zf.read("1/testdata/p2h_interactor.cpp").decode()
            self.assertIn("constexpr int kRunCount = 2;", adapter)
            self.assertIn("constexpr unsigned kInteractiveMask = 1u;", adapter)
            self.assertIn("nextpass.in", adapter)

    def test_adapter_is_deterministic(self) -> None:
        first = self._write(self._problem())
        second = self._write(self._problem())
        with zipfile.ZipFile(first) as a, zipfile.ZipFile(second) as b:
            self.assertEqual(
                a.read("1/testdata/p2h_interactor.cpp"),
                b.read("1/testdata/p2h_interactor.cpp"),
            )

    def test_missing_sources_are_reported(self) -> None:
        zip_dir = tempfile.mkdtemp()
        with self.assertRaises(ValueError) as cm:
            write_problem_zip(
                problem=self._problem(interactor_source=None),
                output_dir=Path(zip_dir) / "out",
                local_id=1,
                pid="P4000",
                owner=1,
                tags=[],
            )
        self.assertIn("missing its interactor/checker source", str(cm.exception))

    def test_adapter_filename_collision_is_reported(self) -> None:
        zip_dir = tempfile.mkdtemp()
        problem = self._problem(testdata_files=[(run_twice.ADAPTER_FILENAME, b"taken")])
        with self.assertRaises(ValueError) as cm:
            write_problem_zip(
                problem=problem,
                output_dir=Path(zip_dir) / "out",
                local_id=1,
                pid="P4000",
                owner=1,
                tags=[],
            )
        self.assertIn("testdata file collision", str(cm.exception))

    def test_too_few_runs_are_reported(self) -> None:
        zip_dir = tempfile.mkdtemp()
        with self.assertRaises(ValueError) as cm:
            write_problem_zip(
                problem=self._problem(run_count=1),
                output_dir=Path(zip_dir) / "out",
                local_id=1,
                pid="P4000",
                owner=1,
                tags=[],
            )
        self.assertIn("at least 2 runs", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
