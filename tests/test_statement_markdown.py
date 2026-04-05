from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.statement_markdown import html_to_markdown, tex_block_to_markdown, tex_to_markdown


class TestStatementMarkdown(unittest.TestCase):
    def test_html_to_markdown_heading_list_and_image(self) -> None:
        text = """
        <html><body>
        <h2>Title</h2>
        <p>Hello<br>World</p>
        <ul><li>A</li><li>B</li></ul>
        <img src="a.png" width="80%" />
        </body></html>
        """
        md = html_to_markdown(text)
        self.assertIn("## Title", md)
        self.assertIn("Hello\nWorld", md)
        self.assertIn("- A", md)
        self.assertIn("- B", md)
        self.assertIn('<img src="a.png" width="80%" />', md)

    def test_html_to_markdown_empty_fallback(self) -> None:
        md = html_to_markdown("<style>.x{}</style><script>1</script>")
        self.assertEqual(md, "# Description\n\n(Empty statement)\n")

    def test_tex_to_markdown_sections_and_fallback(self) -> None:
        tex = """
        \\section{Description}
        Some text
        \\begin{itemize}
        \\item one
        \\item two
        \\end{itemize}
        """
        md = tex_to_markdown(tex)
        self.assertIn("# Description", md)
        self.assertIn("Some text", md)
        self.assertIn("- one", md)
        self.assertIn("- two", md)

        fallback = tex_to_markdown("% comment only")
        self.assertEqual(fallback, "# Description\n\n(Statement conversion fallback from TeX)\n")

    def test_tex_block_to_markdown_image_and_list(self) -> None:
        tex = """
        \\begin{center}
        \\includegraphics[width=60\\%]{fig.png}
        \\end{center}
        \\begin{enumerate}
        \\item alpha
        \\item beta
        \\end{enumerate}
        """
        md = tex_block_to_markdown(tex)
        self.assertIn('<img src="file://fig.png" width="60%" />', md)
        self.assertIn("1. alpha", md)
        self.assertIn("2. beta", md)

    def test_tex_texttt_and_t_are_unified_to_math_texttt(self) -> None:
        tex = r"""
        \\t{Yes}
        \\texttt{Yes}
        $\\t{Yes}$
        $\\texttt{Yes}$
        """
        md = tex_to_markdown(tex)
        self.assertIn("$\\texttt{Yes}$", md)
        self.assertNotIn("\\t{Yes}", md)
        self.assertEqual(md.count("$\\texttt{Yes}$"), 4)

    def test_tex_block_texttt_and_t_are_unified_to_math_texttt(self) -> None:
        tex = r"""
        \\t{No}
        \\texttt{No}
        $\\t{No}$
        $\\texttt{No}$
        """
        md = tex_block_to_markdown(tex)
        self.assertIn("$\\texttt{No}$", md)
        self.assertNotIn("\\t{No}", md)
        self.assertEqual(md.count("$\\texttt{No}$"), 4)

    def test_tex_block_matrix_is_normalized_to_array(self) -> None:
        tex = r"""
        $$
        \begin{matrix}
        00 \to \square & cnt=1

        01 \to 00 \to \square & cnt=2

        10 \to 11 \to 01 \to 00 \to \square & cnt=4

        11 \to 01 \to 00 \to \square & cnt=3
        \end{matrix}
        $$
        """
        md = tex_block_to_markdown(tex)
        self.assertIn(r"\begin{array}{ll}", md)
        self.assertIn(r"\end{array}", md)
        self.assertNotIn(r"\begin{matrix}", md)
        self.assertNotIn(r"\end{matrix}", md)
        self.assertNotIn(" arrow ", md)
        self.assertIn(r"\to", md)
        self.assertGreaterEqual(md.count(r"\\"), 3)

    def test_tex_to_markdown_matrix_is_normalized_to_array(self) -> None:
        tex = r"""
        \section{Note}
        $$
        \begin{matrix}
        a & b
        c & d
        \end{matrix}
        $$
        """
        md = tex_to_markdown(tex)
        self.assertIn(r"\begin{array}{ll}", md)
        self.assertIn(r"\end{array}", md)
        self.assertNotIn(r"\begin{matrix}", md)
        self.assertNotIn(r"\end{matrix}", md)
        self.assertIn("a & b", md)
        self.assertIn(r"\\", md)
        self.assertIn("c & d", md)
        self.assertIn("$$", md)
        self.assertIn("# Note", md)

    def test_tex_block_to_markdown_inline_math_arrow_is_normalized(self) -> None:
        tex = r"""
        \begin{enumerate}
        \item 接着 $(9,9,9,3,3,8,7,2,2,1)\rightarrow (9,9,9,3,3,1,1,1,1,1)$；
        \end{enumerate}
        """
        md = tex_block_to_markdown(tex)
        self.assertIn(r"\to", md)
        self.assertNotIn(r"\rightarrow", md)
        self.assertNotIn("arrow", md)

    def test_tex_to_markdown_inline_math_arrow_is_normalized(self) -> None:
        tex = r"""
        \section{Note}
        接着 $(9,9,9,3,3,8,7,2,2,1)\rightarrow (9,9,9,3,3,1,1,1,1,1)$；
        """
        md = tex_to_markdown(tex)
        self.assertIn(r"\to", md)
        self.assertNotIn(r"\rightarrow", md)
        self.assertNotIn("arrow", md)
        self.assertIn("# Note", md)

    def test_tex_block_epigraph_is_converted_to_blockquote(self) -> None:
        tex = r"""
        \epigraph{
        不要再 Ultra了

        Ultra 是加拿大人研制的新型**

        加拿大人往你的电脑里安装大炮

        当你 Ultra 时大炮就会被点燃

        真是细思极恐

        加拿大人研发的机器人会自动生成 Ultra 图

        无需任何人力就能让你的孩子上瘾
        }{------ 节选自 Ultra 圣经}
        """
        md = tex_block_to_markdown(tex)
        self.assertIn("> 不要再 Ultra了  ", md)
        self.assertIn("> 无需任何人力就能让你的孩子上瘾  ", md)
        self.assertIn("> ——节选自 Ultra 圣经", md)
        self.assertNotIn(r"\epigraph", md)

    def test_tex_to_markdown_epigraph_is_converted_to_blockquote(self) -> None:
        tex = r"""
        \section{Note}
        \epigraph{A line

B line}{--- Source}
        """
        md = tex_to_markdown(tex)
        self.assertIn("# Note", md)
        self.assertIn("> A line  ", md)
        self.assertIn("> B line  ", md)
        self.assertIn("> ——Source", md)
        self.assertNotIn(r"\epigraph", md)

    def test_tex_block_bverbatim_is_converted_to_code_block(self) -> None:
        tex = r"""
        \begin{BVerbatim}
        line 1
          line 2
        \end{BVerbatim}
        """
        md = tex_block_to_markdown(tex)
        self.assertIn("```text", md)
        self.assertIn("line 1", md)
        self.assertIn("  line 2", md)
        self.assertNotIn(r"\begin{BVerbatim}", md)

    def test_tex_to_markdown_bverbatim_with_options_is_converted_to_code_block(self) -> None:
        tex = r"""
        \section{Code}
        \begin{BVerbatim}[fontsize=\small]
        print(1)
        \end{BVerbatim}
        """
        md = tex_to_markdown(tex)
        self.assertIn("# Code", md)
        self.assertIn("```text", md)
        self.assertIn("print(1)", md)
        self.assertNotIn(r"\begin{BVerbatim}", md)
        self.assertNotIn(r"\end{BVerbatim}", md)


if __name__ == "__main__":
    unittest.main()
