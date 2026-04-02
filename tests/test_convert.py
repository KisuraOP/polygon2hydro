from __future__ import annotations

import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.convert import _make_scripts_executable, _safe_extract_contest_zip, convert_contest
from p2h.models import ProblemData, TestCase


def _minimal_problem_xml(title: str = "标题") -> str:
    return f"""<problem>
<names><name language=\"chinese\" value=\"{title}\"/></names>
<judging><testset><time-limit>1000</time-limit><memory-limit>268435456</memory-limit></testset></judging>
</problem>"""


def _build_minimal_contest_zip(path: Path, slugs: list[str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for slug in slugs:
            root = f"problems/{slug}/"
            zf.writestr(root + "problem.xml", _minimal_problem_xml(slug))
            zf.writestr(root + "statement-sections/chinese/legend.tex", "描述")
            zf.writestr(root + "statement-sections/chinese/input.tex", "输入")
            zf.writestr(root + "statement-sections/chinese/output.tex", "输出")
            zf.writestr(root + "statement-sections/chinese/example.1", "1\n")
            zf.writestr(root + "statement-sections/chinese/example.1.a", "2\n")
            zf.writestr(root + "tests/1", "1\n")
            zf.writestr(root + "tests/1.a", "2\n")


class TestConvert(unittest.TestCase):
    def test_safe_extract_contest_zip_blocks_parent_escape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bad_zip = Path(td) / "bad.zip"
            with zipfile.ZipFile(bad_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("../evil.txt", "boom")

            with tempfile.TemporaryDirectory() as out_td:
                with self.assertRaises(ValueError) as cm:
                    _safe_extract_contest_zip(bad_zip, Path(out_td))
                self.assertIn("unsafe path", str(cm.exception))

    def test_convert_logs_progress(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            contest_zip = Path(td) / "contest.zip"
            _build_minimal_contest_zip(contest_zip, ["a", "b"])

            fake_problem = ProblemData(
                slug="a",
                title="A",
                time_ms=1000,
                memory_mb=256,
                statement_md="# Description\n",
                tests=[TestCase(index=1, input_data=b"1\n", output_data=b"1\n")],
                additional_files=[],
            )

            with mock.patch("p2h.convert.read_problem", return_value=fake_problem), mock.patch(
                "p2h.convert.write_problem_zip", return_value=Path(td) / "out.zip"
            ):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    convert_contest(
                        contest_zip=contest_zip,
                        output_dir=Path(td) / "out",
                        pid_prefix="P",
                        pid_start_num=1000,
                        pid_width=4,
                        owner=1,
                        tags=[],
                        run_doall=False,
                    )
                text = out.getvalue()

            self.assertIn("start: total=2", text)
            self.assertIn("[1/2] a (pid=P1000)", text)
            self.assertIn("[2/2] b (pid=P1001)", text)
            self.assertIn("[1/2] OK a ->", text)
            self.assertIn("[2/2] OK b ->", text)

    def test_unknown_only_slug_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            contest_zip = Path(td) / "contest.zip"
            _build_minimal_contest_zip(contest_zip, ["a", "b"])

            summary = convert_contest(
                contest_zip=contest_zip,
                output_dir=Path(td) / "out",
                pid_prefix="P",
                pid_start_num=1000,
                pid_width=4,
                owner=1,
                tags=[],
                only_slugs=["x"],
                run_doall=False,
            )

            self.assertEqual(summary.total, 0)
            self.assertEqual(summary.failed, 0)
            self.assertIn("unknown slug(s): x", summary.errors[0])

    def test_run_doall_flag_controls_execution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            contest_zip = Path(td) / "contest.zip"
            _build_minimal_contest_zip(contest_zip, ["a"])

            fake_problem = ProblemData(
                slug="a",
                title="A",
                time_ms=1000,
                memory_mb=256,
                statement_md="# Description\n",
                tests=[TestCase(index=1, input_data=b"1\n", output_data=b"1\n")],
                additional_files=[],
            )

            with mock.patch("p2h.convert.read_problem", return_value=fake_problem), mock.patch(
                "p2h.convert.write_problem_zip", return_value=Path(td) / "out.zip"
            ), mock.patch("p2h.convert._run_doall_for_all") as run_doall:
                convert_contest(
                    contest_zip=contest_zip,
                    output_dir=Path(td) / "out",
                    pid_prefix="P",
                    pid_start_num=1000,
                    pid_width=4,
                    owner=1,
                    tags=[],
                    run_doall=True,
                )
                run_doall.assert_called_once()

            with mock.patch("p2h.convert.read_problem", return_value=fake_problem), mock.patch(
                "p2h.convert.write_problem_zip", return_value=Path(td) / "out.zip"
            ), mock.patch("p2h.convert._run_doall_for_all") as run_doall:
                convert_contest(
                    contest_zip=contest_zip,
                    output_dir=Path(td) / "out2",
                    pid_prefix="P",
                    pid_start_num=1000,
                    pid_width=4,
                    owner=1,
                    tags=[],
                    run_doall=False,
                )
                run_doall.assert_not_called()

    def test_per_problem_failure_does_not_stop_all(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            contest_zip = Path(td) / "contest.zip"
            _build_minimal_contest_zip(contest_zip, ["a", "b"])

            def fake_read(root: Path, slug: str, *, verbose: bool = False) -> ProblemData:
                if slug == "b":
                    raise ValueError("boom")
                return ProblemData(
                    slug="a",
                    title="A",
                    time_ms=1000,
                    memory_mb=256,
                    statement_md="# Description\n",
                    tests=[TestCase(index=1, input_data=b"1\n", output_data=b"1\n")],
                    additional_files=[],
                )

            with mock.patch("p2h.convert.read_problem", side_effect=fake_read), mock.patch(
                "p2h.convert.write_problem_zip", return_value=Path(td) / "out.zip"
            ):
                summary = convert_contest(
                    contest_zip=contest_zip,
                    output_dir=Path(td) / "out",
                    pid_prefix="P",
                    pid_start_num=1000,
                    pid_width=4,
                    owner=1,
                    tags=[],
                    run_doall=False,
                )

            self.assertEqual(summary.total, 2)
            self.assertEqual(summary.success, 1)
            self.assertEqual(summary.failed, 1)
            self.assertTrue(any("b: boom" in e for e in summary.errors))

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

            _make_scripts_executable(root)

            for p in files:
                mode = p.stat().st_mode
                self.assertTrue(mode & stat.S_IXUSR, p)


if __name__ == "__main__":
    unittest.main()
