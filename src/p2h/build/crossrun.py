"""Answer generation for interactive problems via the package's own CrossRun.jar.

Traditional problems can be answered by running a single solution per test.
Interactive problems cannot: the interactor and the participant program have to
talk to each other, so someone must host the pipe between them. Polygon ships
two hosts for that:

``files/CrossRun.jar`` (Java)
    Used by the generated ``.sh`` scripts. Runs the interactor and the solution
    with a pipe between them.

``files/runexe.exe`` (Windows only)
    Used by the generated ``.bat`` scripts. Same job, but it creates a window
    station, which sandboxed/service sessions deny.

``CrossRun.jar`` is pure Java and therefore works on both hosts; only the
``wine`` prefix inside its arguments is platform specific. So when a package
carries it, this module can rebuild the answers without ``runexe`` at all. It is
used as a fallback: the package's own build script always gets the first try.
"""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from p2h.build.platform import IS_WINDOWS


CROSSRUN_JAR = "files/CrossRun.jar"

JAVA_OPTIONS = [
    "-Xmx512M",
    "-Xss64M",
    "-DONLINE_JUDGE=true",
    "-Duser.language=en",
    "-Duser.region=US",
    "-Duser.variant=US",
]

#: Tests can be slow to interactive-run, but must never hang the conversion.
PER_TEST_TIMEOUT_S = 120


def is_applicable(problem_root: Path) -> bool:
    """True when this problem can be answered through CrossRun on this host."""
    if not (problem_root / CROSSRUN_JAR).exists():
        return False
    if shutil.which("java") is None:
        return False
    return _binaries(problem_root) is not None


def generate_answers(problem_root: Path, *, verbose: bool = False) -> dict[str, str] | None:
    """Create the missing ``.a`` files; return ``{test: error}`` for failures.

    Returns ``None`` when CrossRun cannot be used for this problem, so callers
    can fall back to whatever they were doing before.
    """
    if not is_applicable(problem_root):
        return None
    binaries = _binaries(problem_root)
    if binaries is None:
        return None
    interactor, solution = binaries

    inputs = _pending_inputs(problem_root)
    if not inputs:
        return {}

    failures: dict[str, str] = {}
    for test_file in inputs:
        answer = test_file.with_name(test_file.name + ".a")
        # Keep scratch outside tests/ so a crashed run can never be mistaken
        # for an extra test input.
        scratch = problem_root / f".p2h-{test_file.name}.out"
        scratch.unlink(missing_ok=True)

        command = _crossrun_command(problem_root, interactor, solution, test_file, scratch)
        if verbose:
            print(f"[crossrun] {test_file.name}")
        try:
            result = subprocess.run(
                command,
                cwd=problem_root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=PER_TEST_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            failures[test_file.name] = f"crossrun timed out after {PER_TEST_TIMEOUT_S}s"
            continue

        if result.returncode != 0 or not scratch.exists():
            detail = [line.strip() for line in (result.stderr or result.stdout or "").splitlines() if line.strip()]
            failures[test_file.name] = "; ".join(detail[-2:]) or f"exit code {result.returncode}"
            scratch.unlink(missing_ok=True)
            continue

        scratch.replace(answer)

    return failures


def _crossrun_command(
    problem_root: Path, interactor: str, solution: str, test_file: Path, scratch: Path
) -> list[str]:
    """Build the ``java -jar CrossRun.jar <interactor> <solution>`` argv."""
    # CrossRun takes both programs as single arguments, so the paths inside must
    # not be quoted again; relative paths keep them free of spaces.
    prefix = "" if IS_WINDOWS else "wine "
    test_rel = test_file.relative_to(problem_root).as_posix()
    scratch_rel = scratch.relative_to(problem_root).as_posix()
    interactor_cmd = f"{prefix}{interactor} {test_rel} {scratch_rel}"
    solution_cmd = f"{prefix}{solution}"
    return ["java", *JAVA_OPTIONS, "-jar", CROSSRUN_JAR, interactor_cmd, solution_cmd]


def _binaries(problem_root: Path) -> tuple[str, str] | None:
    """Locate the interactor and participant binaries, or ``None``."""
    xml_path = problem_root / "problem.xml"
    if not xml_path.exists():
        return None
    try:
        root = ET.fromstring(xml_path.read_bytes())
    except ET.ParseError:
        return None

    if root.find("./assets/interactor") is None:
        return None

    interactor = _declared_binary(root, "./assets/interactor", problem_root, default="files/interactor.exe")
    if interactor is None:
        return None

    solution = _participant_solution(root, problem_root)
    if solution is None:
        return None
    return interactor, solution


def _declared_binary(root: ET.Element, node_path: str, problem_root: Path, *, default: str) -> str | None:
    node = root.find(node_path)
    if node is None:
        return None
    source = node.find("source")
    declared = (source.attrib.get("path") if source is not None else node.attrib.get("path")) or ""
    candidates = []
    if declared:
        candidates.append(str(Path(declared).with_suffix(".exe")).replace("\\", "/"))
    candidates.append(default)
    for candidate in candidates:
        if (problem_root / candidate).exists():
            return candidate
    return None


def _participant_solution(root: ET.Element, problem_root: Path) -> str | None:
    """Pick the solution to drive the interactor.

    Polygon lists every solution, including deliberately wrong ones named
    ``should_wa*``/``should_ile*``; those must never be used to produce answers.
    """
    preferred: list[str] = []
    fallback: list[str] = []
    for solution in root.findall("./assets/solutions/solution"):
        source = solution.find("source")
        declared = (source.attrib.get("path") if source is not None else solution.attrib.get("path")) or ""
        if not declared:
            continue
        binary = str(Path(declared).with_suffix(".exe")).replace("\\", "/")
        if not (problem_root / binary).exists():
            continue
        if Path(binary).stem.startswith("should_"):
            fallback.append(binary)
        else:
            preferred.append(binary)

    for candidate in preferred + fallback:
        return candidate
    return None


def _pending_inputs(problem_root: Path) -> list[Path]:
    """Test inputs that still need an answer file, in Polygon's ordering."""
    tests_dir = problem_root / "tests"
    if not tests_dir.exists():
        return []
    pending = [
        path
        for path in tests_dir.iterdir()
        if path.is_file()
        and not path.name.endswith((".a", ".out"))
        # ``.a`` and ``.out`` are both answer spellings; either one is enough.
        and not path.with_name(path.name + ".a").exists()
        and not path.with_name(path.name + ".out").exists()
    ]
    return sorted(pending, key=lambda p: p.name)
