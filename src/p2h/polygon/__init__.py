"""Reading the input side of a Polygon contest package.

``archive``  unpacking a contest zip and listing its problems
``problem``  turning one problem directory into :class:`p2h.models.ProblemData`
``statement`` contest-level statement language detection
``markup``   TeX / HTML statement fragments to markdown
"""

from __future__ import annotations
