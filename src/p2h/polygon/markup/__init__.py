"""TeX / HTML statement markup to Hydro-flavoured markdown.

The conversion is a pipeline of small, independent stages:

``text``
    Line endings, TeX comments, HTML tags.
``math``
    Arrow aliases, ``matrix`` → ``array``, display-math normalisation.
``blocks``
    ``itemize`` / ``enumerate`` / ``center`` / verbatim / ``\\epigraph``.
``inline``
    Images, legacy font switches (``\\tt``, ``\\bf``, …), ``\\texttt``, emphasis.
``pipeline``
    Two entry points that compose the stages:

    * :func:`tex_block_to_markdown` – one section file (``legend.tex`` …)
    * :func:`tex_to_markdown` – a whole statement (``problem.tex``)
    * :func:`html_to_markdown` – an HTML statement

Stage order matters: block environments are rewritten before the inline pass,
and display math is normalised after environments so the ``$$`` form the
renderer understands ends up in the final markdown.
"""

from __future__ import annotations

from p2h.polygon.markup.pipeline import html_to_markdown, tex_block_to_markdown, tex_to_markdown

__all__ = ["html_to_markdown", "tex_block_to_markdown", "tex_to_markdown"]
