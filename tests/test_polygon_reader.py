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

            md = pr._sections_to_markdown(d, is_interactive=False)

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

    def test_sections_to_markdown_interactive_template(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "legend.tex").write_text("题面", encoding="utf-8")
            (d / "interaction.tex").write_text("交互格式说明", encoding="utf-8")
            (d / "example.1").write_text("1\n", encoding="utf-8")
            (d / "example.1.a").write_text("2\n", encoding="utf-8")

            md = pr._sections_to_markdown(d, is_interactive=True)

            self.assertIn("# Description", md)
            self.assertIn("# Interaction", md)
            self.assertNotIn("# Format", md)
            self.assertIn("# Samples", md)
            self.assertIn("```input1", md)
            self.assertIn("```output1", md)

    def test_extract_interactive_meta(self) -> None:
        root = pr.ET.fromstring(
            """
            <problem>
              <assets>
                <interactor>
                  <source path=\"files/inter.cc\" type=\"cpp.gcc14-64-msys2-g++23\"/>
                </interactor>
              </assets>
            </problem>
            """
        )
        is_interactive, interactor_name = pr._extract_interactive_meta(root)
        self.assertTrue(is_interactive)
        self.assertEqual(interactor_name, "inter.cc")

    def test_extract_interactive_meta_none(self) -> None:
        root = pr.ET.fromstring("<problem></problem>")
        is_interactive, interactor_name = pr._extract_interactive_meta(root)
        self.assertFalse(is_interactive)
        self.assertIsNone(interactor_name)

    def test_extract_interactive_meta_without_source(self) -> None:
        root = pr.ET.fromstring(
            """
            <problem>
              <assets>
                <interactor></interactor>
              </assets>
            </problem>
            """
        )
        is_interactive, interactor_name = pr._extract_interactive_meta(root)
        self.assertTrue(is_interactive)
        self.assertIsNone(interactor_name)

    def test_read_problem_interactive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "guess-the-number"
            base = root / "problems" / slug
            (base / "statement-sections" / "chinese").mkdir(parents=True)
            (base / "tests").mkdir(parents=True)

            (base / "problem.xml").write_text(
                """
                <problem>
                  <names><name language=\"chinese\" value=\"猜数字\"/></names>
                  <judging><testset><time-limit>1000</time-limit><memory-limit>268435456</memory-limit></testset></judging>
                  <assets>
                    <interactor>
                      <source path=\"files/inter.cc\" type=\"cpp.gcc14-64-msys2-g++23\"/>
                    </interactor>
                  </assets>
                </problem>
                """,
                encoding="utf-8",
            )
            (base / "statement-sections" / "chinese" / "legend.tex").write_text("题面", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "interaction.tex").write_text("交互说明", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "example.1").write_text("1\n", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "example.1.a").write_text("2\n", encoding="utf-8")
            (base / "tests" / "1").write_bytes(b"1\n")
            (base / "tests" / "1.a").write_bytes(b"2\n")

            problem = pr.read_problem(root, slug)
            self.assertTrue(problem.is_interactive)
            self.assertEqual(problem.interactor_name, "inter.cc")
            self.assertIn("# Interaction", problem.statement_md)
            self.assertNotIn("# Format", problem.statement_md)
            self.assertIn("```input1", problem.statement_md)
            self.assertIn("```output1", problem.statement_md)

    def test_read_problem_interactive_without_interaction_section(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "interactive-no-section"
            base = root / "problems" / slug
            (base / "statement-sections" / "chinese").mkdir(parents=True)
            (base / "tests").mkdir(parents=True)

            (base / "problem.xml").write_text(
                """
                <problem>
                  <names><name language=\"chinese\" value=\"交互题\"/></names>
                  <assets>
                    <interactor>
                      <source path=\"files/interactor.cpp\"/>
                    </interactor>
                  </assets>
                </problem>
                """,
                encoding="utf-8",
            )
            (base / "statement-sections" / "chinese" / "legend.tex").write_text("题面", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "example.1").write_text("1\n", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "example.1.a").write_text("2\n", encoding="utf-8")
            (base / "tests" / "1").write_bytes(b"1\n")
            (base / "tests" / "1.a").write_bytes(b"2\n")

            problem = pr.read_problem(root, slug)
            self.assertTrue(problem.is_interactive)
            self.assertIn("# Interaction", problem.statement_md)
            self.assertIn("(No interaction provided)", problem.statement_md)
            self.assertNotIn("# Format", problem.statement_md)

    def test_read_problem_non_interactive_keeps_format(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "normal"
            base = root / "problems" / slug
            (base / "statement-sections" / "chinese").mkdir(parents=True)
            (base / "tests").mkdir(parents=True)

            (base / "problem.xml").write_text(
                """
                <problem>
                  <names><name language=\"chinese\" value=\"普通题\"/></names>
                </problem>
                """,
                encoding="utf-8",
            )
            (base / "statement-sections" / "chinese" / "legend.tex").write_text("题面", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "input.tex").write_text("输入", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "output.tex").write_text("输出", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "example.1").write_text("1\n", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "example.1.a").write_text("2\n", encoding="utf-8")
            (base / "tests" / "1").write_bytes(b"1\n")
            (base / "tests" / "1.a").write_bytes(b"2\n")

            problem = pr.read_problem(root, slug)
            self.assertFalse(problem.is_interactive)
            self.assertIn("# Format", problem.statement_md)
            self.assertNotIn("# Interaction", problem.statement_md)

    def test_extract_statement_markdown_interactive_flag_without_interaction_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sections = base / "statement-sections" / "chinese"
            sections.mkdir(parents=True)
            (sections / "legend.tex").write_text("题面", encoding="utf-8")
            (sections / "example.1").write_text("1\n", encoding="utf-8")
            (sections / "example.1.a").write_text("2\n", encoding="utf-8")

            md, _ = pr._extract_statement_markdown(base, pr.ET.fromstring("<problem></problem>"), is_interactive=True)
            self.assertIn("# Interaction", md)
            self.assertNotIn("# Format", md)

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
            self.assertEqual(cases[0].input_name, "10.in")
            self.assertEqual(cases[0].output_name, "10.out")
            self.assertEqual(cases[0].input_data, b"in10\n")
            self.assertEqual(cases[1].input_name, "3.in")
            self.assertEqual(cases[1].output_name, "3.out")
            self.assertEqual(cases[1].output_data, b"out3\n")

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

    def test_extract_testdata_files_from_xml_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "files").mkdir(parents=True)
            (base / "solutions").mkdir(parents=True)
            (base / "files" / "gen_maxtime.cpp").write_bytes(b"gen")
            (base / "files" / "val.cpp").write_bytes(b"val")
            (base / "solutions" / "std.cpp").write_bytes(b"std")

            root = pr.ET.fromstring(
                """
                <problem>
                  <files>
                    <executables>
                      <executable>
                        <source path="files/gen_maxtime.cpp" />
                      </executable>
                      <executable>
                        <source path="files/val.cpp" />
                      </executable>
                    </executables>
                  </files>
                  <assets>
                    <solutions>
                      <solution>
                        <source path="solutions/std.cpp" />
                      </solution>
                    </solutions>
                  </assets>
                </problem>
                """
            )

            files = pr._extract_testdata_files(base, root, "blackorwhite")
            names = [n for n, _ in files]
            self.assertEqual(names, ["gen_maxtime.cpp", "std.cpp", "val.cpp"])

    def test_extract_testdata_files_collision_after_flatten(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "files").mkdir(parents=True)
            (base / "solutions").mkdir(parents=True)
            (base / "files" / "std.cpp").write_bytes(b"a")
            (base / "solutions" / "std.cpp").write_bytes(b"b")

            root = pr.ET.fromstring(
                """
                <problem>
                  <files>
                    <executables>
                      <executable>
                        <source path="files/std.cpp" />
                      </executable>
                    </executables>
                  </files>
                  <assets>
                    <solutions>
                      <solution>
                        <source path="solutions/std.cpp" />
                      </solution>
                    </solutions>
                  </assets>
                </problem>
                """
            )

            with self.assertRaises(ValueError) as cm:
                pr._extract_testdata_files(base, root, "dup")
            self.assertIn("testdata filename collision after flatten", str(cm.exception))

    def test_extract_testdata_files_supports_direct_path_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "files").mkdir(parents=True)
            (base / "solutions").mkdir(parents=True)
            (base / "files" / "gen_random.cpp").write_bytes(b"gen")
            (base / "solutions" / "std_ai.cpp").write_bytes(b"std")

            root = pr.ET.fromstring(
                """
                <problem>
                  <files>
                    <executables>
                      <executable path="files/gen_random.cpp" />
                    </executables>
                  </files>
                  <assets>
                    <solutions>
                      <solution path="solutions/std_ai.cpp" />
                    </solutions>
                  </assets>
                </problem>
                """
            )

            files = pr._extract_testdata_files(base, root, "mixed")
            names = [n for n, _ in files]
            self.assertEqual(names, ["gen_random.cpp", "std_ai.cpp"])

    def test_extract_testdata_files_missing_declared_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = pr.ET.fromstring(
                """
                <problem>
                  <files>
                    <executables>
                      <executable path="files/missing.cpp" />
                    </executables>
                  </files>
                </problem>
                """
            )
            with self.assertRaises(ValueError) as cm:
                pr._extract_testdata_files(base, root, "blackorwhite")
            self.assertIn("declared testdata file not found", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
