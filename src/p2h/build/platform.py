"""Every platform-dependent decision lives here.

Polygon ships two equivalent build entry points per problem:

``doall.bat``
    Runs the bundled Windows ``.exe`` files (validator, generator, checker,
    interactor) natively. Needs no external tool at all.

``doall.sh``
    Drives the very same ``.exe`` files through ``wine``, so it needs ``wine``
    (and occasionally ``java``) to be installed.

Wine is a POSIX compatibility layer: it runs Windows binaries on Linux/macOS
and has no Windows build of its own. That is why the choice is driven by the
host, not by a flag:

=================  ======================  ============================
host               entry point             external tools
=================  ======================  ============================
Windows            ``cmd /c doall.bat``    none
Linux / macOS      ``bash doall.sh``       ``wine`` (+ ``java``)
=================  ======================  ============================

Packaging itself (``problem.yaml``, ``config.yaml``, testdata, attachments) is
identical on both hosts; only the build step differs.
"""

from __future__ import annotations

import os
from pathlib import Path


IS_WINDOWS: bool = os.name == "nt"

DOALL_BAT = "doall.bat"
DOALL_SH = "doall.sh"

#: Command used to run a ``.bat`` file (no shell involved, so arguments cannot
#: be re-interpreted by a second shell expansion).
CMD_RUNNER = "cmd"
#: Command used to run a ``.sh`` file.
SH_RUNNER = "bash"


def doall_script_kind(problem_root: Path) -> str | None:
    """Return ``".bat"`` or ``".sh"`` for the script this host should run."""
    bat = problem_root / DOALL_BAT
    sh = problem_root / DOALL_SH
    if IS_WINDOWS:
        if bat.exists():
            return ".bat"
        if sh.exists():
            return ".sh"
        return None
    if sh.exists():
        return ".sh"
    if bat.exists():
        return ".bat"
    return None


def doall_command(problem_root: Path) -> list[str] | None:
    """Return the argv that runs this problem's build script, or ``None``.

    Windows prefers ``doall.bat``: running ``doall.sh`` there would start a
    POSIX shell that then looks for ``wine`` and blocks forever on the first
    ``read``/``pause``. POSIX has the mirror-image preference.
    """
    kind = doall_script_kind(problem_root)
    if kind is None:
        return None
    script = DOALL_BAT if kind == ".bat" else DOALL_SH
    runner = CMD_RUNNER if kind == ".bat" else SH_RUNNER
    arguments = ["/c", script] if runner == CMD_RUNNER else [script]
    return [runner, *arguments]


def host_label() -> str:
    """One-line description of how this host will run doall, for ``--verbose``."""
    if IS_WINDOWS:
        return "windows -> doall.bat (native .exe, no wine)"
    return "posix -> doall.sh (bundled .exe via wine)"
