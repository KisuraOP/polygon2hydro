"""Contest-level statement language selection.

Polygon writes all languages side by side under ``statements/<language>``. The
whole contest is expected to read in one language, so the first choice is made
once per contest and then handed to every problem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

StatementLanguage = Literal["chinese", "english"]

#: Preference order when the contest does not pin a language.
DEFAULT_PRIORITY: tuple[StatementLanguage, ...] = ("chinese", "english")


def detect_contest_language(work_root: Path) -> StatementLanguage | None:
    """Return the contest's statement language, or ``None`` to use the default."""
    statements_root = work_root / "statements"
    if not statements_root.exists() or not statements_root.is_dir():
        return None

    if (statements_root / "chinese").exists():
        return "chinese"
    if (statements_root / "english").exists():
        return "english"
    return None
