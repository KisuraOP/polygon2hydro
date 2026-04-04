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


if __name__ == "__main__":
    unittest.main()
