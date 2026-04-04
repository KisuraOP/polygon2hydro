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
    def test_extract_title_respects_statement_language(self) -> None:
        root = pr.ET.fromstring(
            """
            <problem>
              <names>
                <name language="chinese" value="中文标题"/>
                <name language="english" value="English Title"/>
              </names>
            </problem>
            """
        )
        self.assertEqual(pr._extract_title(root, statement_language="chinese"), "中文标题")
        self.assertEqual(pr._extract_title(root, statement_language="english"), "English Title")
        self.assertEqual(pr._extract_title(root, statement_language=None), "中文标题")

    def test_extract_statement_markdown_uses_english_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            zh = base / "statement-sections" / "chinese"
            en = base / "statement-sections" / "english"
            zh.mkdir(parents=True)
            en.mkdir(parents=True)
            (zh / "legend.tex").write_text("中文题面", encoding="utf-8")
            (zh / "input.tex").write_text("中文输入", encoding="utf-8")
            (zh / "output.tex").write_text("中文输出", encoding="utf-8")
            (en / "legend.tex").write_text("English description", encoding="utf-8")
            (en / "input.tex").write_text("Input format", encoding="utf-8")
            (en / "output.tex").write_text("Output format", encoding="utf-8")

            md, used_dir = pr._extract_statement_markdown(
                base,
                pr.ET.fromstring("<problem></problem>"),
                is_interactive=False,
                statement_language="english",
            )
            self.assertIn("English description", md)
            self.assertNotIn("中文题面", md)
            self.assertEqual(used_dir, en)

    def test_extract_statement_markdown_falls_back_when_selected_language_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            zh = base / "statement-sections" / "chinese"
            zh.mkdir(parents=True)
            (zh / "legend.tex").write_text("中文题面", encoding="utf-8")
            (zh / "input.tex").write_text("中文输入", encoding="utf-8")
            (zh / "output.tex").write_text("中文输出", encoding="utf-8")

            md, used_dir = pr._extract_statement_markdown(
                base,
                pr.ET.fromstring("<problem></problem>"),
                is_interactive=False,
                statement_language="english",
            )
            self.assertIn("中文题面", md)
            self.assertEqual(used_dir, zh)

    def test_extract_statement_markdown_uses_english_xml_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            zh_html = base / "statements" / "zh.html"
            en_html = base / "statements" / "en.html"
            zh_html.parent.mkdir(parents=True)
            zh_html.write_text("<p>中文题面</p>", encoding="utf-8")
            en_html.write_text("<p>English statement</p>", encoding="utf-8")

            root = pr.ET.fromstring(
                """
                <problem>
                  <statements>
                    <statement language="chinese" type="text/html" path="statements/zh.html" />
                    <statement language="english" type="text/html" path="statements/en.html" />
                  </statements>
                </problem>
                """
            )

            md, used_dir = pr._extract_statement_markdown(
                base,
                root,
                is_interactive=False,
                statement_language="english",
            )
            self.assertIn("English statement", md)
            self.assertNotIn("中文题面", md)
            self.assertEqual(used_dir, en_html.parent)

    def test_read_problem_respects_statement_language_for_title(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "lang-pref"
            base = root / "problems" / slug
            (base / "statement-sections" / "chinese").mkdir(parents=True)
            (base / "statement-sections" / "english").mkdir(parents=True)
            (base / "tests").mkdir(parents=True)
            (base / "files").mkdir(parents=True)

            (base / "problem.xml").write_text(
                """
                <problem>
                  <names>
                    <name language="chinese" value="中文标题"/>
                    <name language="english" value="English Title"/>
                  </names>
                  <assets>
                    <checker type="testlib">
                      <source path="files/check.cpp"/>
                    </checker>
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
            (base / "tests" / "1").write_bytes(b"1\n")
            (base / "tests" / "1.a").write_bytes(b"2\n")
            (base / "files" / "check.cpp").write_text("// checker", encoding="utf-8")

            problem = pr.read_problem(root, slug, statement_language="english")
            self.assertEqual(problem.title, "English Title")
            self.assertIn("English statement", problem.statement_md)

            problem_zh = pr.read_problem(root, slug, statement_language="chinese")
            self.assertEqual(problem_zh.title, "中文标题")
            self.assertIn("中文题面", problem_zh.statement_md)

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
                  <assets>
                    <checker type=\"testlib\">
                      <source path=\"files/check.cpp\"/>
                    </checker>
                  </assets>
                </problem>
                """,
                encoding="utf-8",
            )
            (base / "files").mkdir(parents=True)
            (base / "files" / "check.cpp").write_text("// checker", encoding="utf-8")
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

            md, _ = pr._extract_statement_markdown(
                base,
                pr.ET.fromstring("<problem></problem>"),
                is_interactive=True,
                statement_language=None,
            )
            self.assertIn("# Interaction", md)
            self.assertNotIn("# Format", md)

    def test_extract_statement_markdown_fallback_to_english_sections(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sections = base / "statement-sections" / "english"
            sections.mkdir(parents=True)
            (sections / "legend.tex").write_text("English description", encoding="utf-8")
            (sections / "input.tex").write_text("Input format", encoding="utf-8")
            (sections / "output.tex").write_text("Output format", encoding="utf-8")

            md, used_dir = pr._extract_statement_markdown(
                base,
                pr.ET.fromstring("<problem></problem>"),
                is_interactive=False,
                statement_language=None,
            )
            self.assertIn("English description", md)
            self.assertIn("# Format", md)
            self.assertEqual(used_dir, sections)

    def test_extract_statement_markdown_prefers_chinese_over_english_sections(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            zh = base / "statement-sections" / "chinese"
            en = base / "statement-sections" / "english"
            zh.mkdir(parents=True)
            en.mkdir(parents=True)
            (zh / "legend.tex").write_text("中文题面", encoding="utf-8")
            (zh / "input.tex").write_text("中文输入", encoding="utf-8")
            (zh / "output.tex").write_text("中文输出", encoding="utf-8")
            (en / "legend.tex").write_text("English description", encoding="utf-8")
            (en / "input.tex").write_text("Input format", encoding="utf-8")
            (en / "output.tex").write_text("Output format", encoding="utf-8")

            md, used_dir = pr._extract_statement_markdown(
                base,
                pr.ET.fromstring("<problem></problem>"),
                is_interactive=False,
                statement_language=None,
            )
            self.assertIn("中文题面", md)
            self.assertNotIn("English description", md)
            self.assertEqual(used_dir, zh)

    def test_extract_statement_markdown_fallback_to_english_xml_html(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            html_path = base / "statements" / "english.html"
            html_path.parent.mkdir(parents=True)
            html_path.write_text("<p>English only statement</p>", encoding="utf-8")

            root = pr.ET.fromstring(
                """
                <problem>
                  <statements>
                    <statement language="english" type="text/html" path="statements/english.html" />
                  </statements>
                </problem>
                """
            )
            md, used_dir = pr._extract_statement_markdown(
                base,
                root,
                is_interactive=False,
                statement_language=None,
            )
            self.assertIn("English only statement", md)
            self.assertEqual(used_dir, html_path.parent)

    def test_extract_additional_files_from_selected_english_statement_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            en = base / "statement-sections" / "english"
            en.mkdir(parents=True)
            (en / "legend.tex").write_text("English statement", encoding="utf-8")
            (en / "figure.png").write_bytes(b"img")

            md, used_dir = pr._extract_statement_markdown(
                base,
                pr.ET.fromstring("<problem></problem>"),
                is_interactive=False,
                statement_language=None,
            )
            files = pr._extract_additional_files(base, used_dir)
            names = [n for n, _ in files]
            self.assertIn("English statement", md)
            self.assertEqual(used_dir, en)
            self.assertIn("figure.png", names)
            self.assertIn("legend.tex", names)

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

            files = pr._extract_testdata_files(base, root, "blackorwhite", is_interactive=False)
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
                pr._extract_testdata_files(base, root, "dup", is_interactive=False)
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

            files = pr._extract_testdata_files(base, root, "mixed", is_interactive=False)
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
                pr._extract_testdata_files(base, root, "blackorwhite", is_interactive=False)
            self.assertIn("declared testdata file not found", str(cm.exception))

    def test_extract_checker_name_from_source(self) -> None:
        root = pr.ET.fromstring(
            """
            <problem>
              <assets>
                <checker type="testlib">
                  <source path="files/checker123.cpp" />
                </checker>
              </assets>
            </problem>
            """
        )
        self.assertEqual(pr._extract_checker_name(root), "checker123.cpp")

    def test_extract_checker_name_from_direct_path(self) -> None:
        root = pr.ET.fromstring(
            """
            <problem>
              <assets>
                <checker path="files/check.cpp" type="testlib" />
              </assets>
            </problem>
            """
        )
        self.assertEqual(pr._extract_checker_name(root), "check.cpp")

    def test_read_problem_traditional_requires_checker(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "normal-no-checker"
            base = root / "problems" / slug
            (base / "statement-sections" / "chinese").mkdir(parents=True)
            (base / "tests").mkdir(parents=True)

            (base / "problem.xml").write_text(
                """
                <problem>
                  <names><name language="chinese" value="普通题"/></names>
                </problem>
                """,
                encoding="utf-8",
            )
            (base / "statement-sections" / "chinese" / "legend.tex").write_text("题面", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "input.tex").write_text("输入", encoding="utf-8")
            (base / "statement-sections" / "chinese" / "output.tex").write_text("输出", encoding="utf-8")
            (base / "tests" / "1").write_bytes(b"1\n")
            (base / "tests" / "1.a").write_bytes(b"2\n")

            with self.assertRaises(ValueError) as cm:
                pr.read_problem(root, slug)
            self.assertIn("missing checker source", str(cm.exception))

    def test_extract_testdata_files_includes_checker_and_default_check_cpp(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "files").mkdir(parents=True)
            (base / "files" / "checker123.cpp").write_bytes(b"checker")
            (base / "files" / "check.cpp").write_bytes(b"default-checker")

            root = pr.ET.fromstring(
                """
                <problem>
                  <assets>
                    <checker type="testlib">
                      <source path="files/checker123.cpp" />
                    </checker>
                  </assets>
                </problem>
                """
            )

            files = pr._extract_testdata_files(base, root, "spj", is_interactive=False)
            names = [n for n, _ in files]
            self.assertEqual(names, ["check.cpp", "checker123.cpp"])

    def test_extract_testdata_files_allows_same_name_same_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "files").mkdir(parents=True)
            (base / "files" / "checker.cpp").write_bytes(b"same")

            root = pr.ET.fromstring(
                """
                <problem>
                  <files>
                    <executables>
                      <executable>
                        <source path="files/checker.cpp" />
                      </executable>
                    </executables>
                  </files>
                  <assets>
                    <checker type="testlib">
                      <source path="files/checker.cpp" />
                    </checker>
                  </assets>
                </problem>
                """
            )

            files = pr._extract_testdata_files(base, root, "same-source", is_interactive=False)
            names = [n for n, _ in files]
            self.assertEqual(names, ["checker.cpp"])

    def test_extract_testdata_files_same_name_different_source_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "files").mkdir(parents=True)
            (base / "solutions").mkdir(parents=True)
            (base / "files" / "checker.cpp").write_bytes(b"a")
            (base / "solutions" / "checker.cpp").write_bytes(b"b")

            root = pr.ET.fromstring(
                """
                <problem>
                  <files>
                    <executables>
                      <executable>
                        <source path="files/checker.cpp" />
                      </executable>
                    </executables>
                  </files>
                  <assets>
                    <checker type="testlib">
                      <source path="solutions/checker.cpp" />
                    </checker>
                  </assets>
                </problem>
                """
            )

            with self.assertRaises(ValueError) as cm:
                pr._extract_testdata_files(base, root, "diff-source", is_interactive=False)
            self.assertIn("testdata filename collision after flatten", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
