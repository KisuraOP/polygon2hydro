"""Answers for run-twice ("communication") problems.

Polygon judges a run-twice problem by executing the participant's program once
per run, in a fresh sandbox each time.  ``problem.xml`` says how the runs are
connected:

``<judging run-count="N">``
    The participant is executed ``N`` times.

``<interactor><runs><run>k</run>...</runs></interactor>``
    The runs whose interface is interactive, i.e. where the interaction program
    runs next to the participant and both talk over pipes.  Runs without an
    interactor are plain: the participant reads a file and its output becomes the
    next run's input.  ``<runs>`` is omitted for the common single-run
    interactive problem, which means "run 1 only".

So for runs ``1..N``::

    run 1 input   = the test input
    run k input   = run k-1's output channel
    output channel = interactor's tout, if run k is interactive
                     participant's stdout, otherwise
    verdict       = every run's interactor verdict, then the checker over
                    (test input, last run's output channel, model's answer)

This module replays that protocol locally to produce the answer file (the model
solution's last output channel).  ``CrossRun.jar`` cannot do it: it hosts a
single dialogue and its output file is the interactor's ``tout`` alone.

Both programming models are hosted here with :mod:`subprocess` and one pump
thread, so it works on Windows and POSIX alike and only needs the binaries the
package already ships.  On POSIX the binaries run through ``wine``.
"""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from p2h.build import binaries
from p2h.build.platform import IS_WINDOWS


#: A single run must never hang the conversion.
PER_PASS_TIMEOUT_S = 120

#: How much participant output we are willing to buffer for an answer.
MAX_CAPTURED_BYTES = 64 * 1024 * 1024

_PUMP_CHUNK = 64 * 1024


@dataclass(slots=True)
class PassResult:
    """One run of the participant."""

    ok: bool
    detail: str
    output: bytes
    timed_out: bool = False


def is_applicable(problem_root: Path) -> bool:
    """True when this problem's binaries are present on this host."""
    if binaries.interactor_binary(problem_root) is None:
        return False
    return binaries.main_solution_binary(problem_root) is not None


def generate_answers(
    problem_root: Path,
    *,
    run_count: int,
    interactor_runs: frozenset[int] | set[int],
    verbose: bool = False,
) -> dict[str, str] | None:
    """(Re)create every answer file for a run-twice problem.

    Returns ``{test: error}`` for failures, an empty dict on success, and
    ``None`` when the package does not carry the binaries needed to do this.
    A failing test loses its answer file, so a later packaging step fails
    loudly instead of shipping the answer the package's own build script
    produced with the wrong semantics.
    """
    if not is_applicable(problem_root):
        return None
    interactor = binaries.interactor_binary(problem_root)
    participant = binaries.main_solution_binary(problem_root)
    assert interactor is not None and participant is not None
    checker = binaries.checker_binary(problem_root)

    interactor_command = _program_command(problem_root, interactor)
    participant_command = _program_command(problem_root, participant)
    checker_command = _program_command(problem_root, checker) if checker else None
    runs = frozenset(interactor_runs)

    inputs = binaries.test_inputs(problem_root)
    if not inputs:
        return {}

    failures: dict[str, str] = {}
    for test_file in inputs:
        answer_path = test_file.with_name(test_file.name + ".a")
        scratch: list[Path] = []
        try:
            error = _answer_one(
                problem_root,
                test_file,
                run_count=run_count,
                runs=runs,
                interactor=interactor_command,
                participant=participant_command,
                checker=checker_command,
                scratch=scratch,
                verbose=verbose,
            )
        finally:
            for path in scratch:
                _unlink_quietly(path)
        if error is not None:
            failures[test_file.name] = error
            _unlink_quietly(answer_path)
            continue
        if verbose:
            print(f"[twopass] {test_file.name}: {answer_path.stat().st_size} answer byte(s)")

    return failures


def run_interactive_pass(
    *,
    interactor: list[str],
    participant: list[str],
    input_file: str,
    tout_file: str,
    cwd: Path,
    timeout_s: int = PER_PASS_TIMEOUT_S,
) -> PassResult:
    """One interactive run: the interactor talks to the participant over pipes.

    The interactor gets ``input_file`` as testlib's ``inf``, writes to the
    participant over stdout, reads the participant's stdout as ``ouf`` and puts
    the next run's input into ``tout_file``.

    Both directions go through a buffered relay instead of a direct pipe.  A
    direct pipe deadlocks as soon as both sides write more than a pipe buffer
    before reading (real case: ``tree`` test 04, where the interactor sends
    256 KiB while the solution already writes its answer; even Polygon's own
    ``CrossRun.jar`` hangs on it).  Buffering lets the reader keep draining one
    side while the other side is not reading yet.
    """
    interactor_err = cwd / f".p2h-{Path(tout_file).name}.intr.err"
    participant_err = cwd / f".p2h-{Path(tout_file).name}.sol.err"
    _unlink_quietly(interactor_err)
    _unlink_quietly(participant_err)

    with interactor_err.open("wb") as interactor_stderr, participant_err.open("wb") as participant_stderr:
        interactor_proc = subprocess.Popen(
            [*interactor, input_file, tout_file],
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=interactor_stderr,
            **_no_window_kwargs(),
        )
        assert interactor_proc.stdin is not None and interactor_proc.stdout is not None
        try:
            participant_proc = subprocess.Popen(
                participant,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=participant_stderr,
                **_no_window_kwargs(),
            )
        except OSError:
            _kill_tree(interactor_proc)
            raise
        assert participant_proc.stdin is not None and participant_proc.stdout is not None

        to_participant = _Relay(interactor_proc.stdout, participant_proc.stdin, "interactor->participant")
        to_interactor = _Relay(participant_proc.stdout, interactor_proc.stdin, "participant->interactor")
        to_participant.start()
        to_interactor.start()

        timed_out = False
        try:
            returncode = interactor_proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = -1
            _kill_tree(interactor_proc)

        if participant_proc.poll() is None:
            _kill_tree(participant_proc)
        try:
            participant_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        to_participant.join(timeout=15)
        to_interactor.join(timeout=15)

        overflow = to_participant.overflow or to_interactor.overflow

    stderr_text = _read_stderr(interactor_err)
    _unlink_quietly(participant_err)
    if overflow:
        timed_out = True
        stderr_text = f"{stderr_text}; participant output exceeded {MAX_CAPTURED_BYTES} bytes".strip("; ")
    return PassResult(
        ok=returncode == 0,
        detail=stderr_text,
        output=_read_optional(cwd / tout_file),
        timed_out=timed_out,
    )


def run_plain_pass(
    *,
    participant: list[str],
    input_file: str,
    cwd: Path,
    timeout_s: int = PER_PASS_TIMEOUT_S,
) -> PassResult:
    """One plain run: the participant reads a file and its stdout is the output."""
    stderr_path = cwd / f".p2h-{Path(input_file).name}.plain.err"
    _unlink_quietly(stderr_path)
    with (cwd / input_file).open("rb") as input_stream, stderr_path.open("wb") as stderr_file:
        try:
            result = subprocess.run(
                participant,
                cwd=str(cwd),
                stdin=input_stream,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                timeout=timeout_s,
                **_no_window_kwargs(),
            )
        except subprocess.TimeoutExpired:
            _unlink_quietly(stderr_path)
            return PassResult(ok=False, detail="", output=b"", timed_out=True)
    stderr_text = _read_stderr(stderr_path)
    if result.returncode != 0:
        detail = stderr_text or f"exit code {result.returncode}"
        return PassResult(ok=False, detail=f"model solution exited with {detail}", output=b"")
    if len(result.stdout) > MAX_CAPTURED_BYTES:
        return PassResult(
            ok=False,
            detail=f"model solution printed more than {MAX_CAPTURED_BYTES} bytes",
            output=b"",
        )
    return PassResult(ok=True, detail="", output=result.stdout)


def _answer_one(
    problem_root: Path,
    test_file: Path,
    *,
    run_count: int,
    runs: frozenset[int],
    interactor: list[str],
    participant: list[str],
    checker: list[str] | None,
    scratch: list[Path],
    verbose: bool,
) -> str | None:
    """Drive all runs for one test; return an error string or ``None``."""
    test_relative = _relative(problem_root, test_file)
    current_input = test_relative
    answer: bytes | None = None

    for run in range(1, run_count + 1):
        interactive = run in runs
        final = run == run_count
        if verbose:
            mode = "interactive" if interactive else "plain"
            print(f"[twopass] {test_file.name}: run {run}/{run_count} ({mode})")

        if interactive:
            tout_name = f".p2h-{test_file.name}.tout{run}"
            scratch.append(problem_root / tout_name)
            result = run_interactive_pass(
                interactor=interactor,
                participant=participant,
                input_file=current_input,
                tout_file=tout_name,
                cwd=problem_root,
            )
            output = result.output
        else:
            result = run_plain_pass(
                participant=participant,
                input_file=current_input,
                cwd=problem_root,
            )
            output = result.output

        if result.timed_out:
            return f"run {run}/{run_count} timed out after {PER_PASS_TIMEOUT_S}s"
        if not result.ok:
            return f"run {run}/{run_count}: {result.detail or 'run failed'}"

        if final:
            answer = output
            break

        next_input_name = f".p2h-{test_file.name}.next{run}"
        scratch.append(problem_root / next_input_name)
        (problem_root / next_input_name).write_bytes(output)
        current_input = next_input_name

    if answer is None:
        return "internal error: no answer was produced"
    if not answer:
        # An empty answer would make the checker compare against nothing and
        # silently accept anything; every real problem produces some output.
        return "the last run produced no output for the checker"

    if checker:
        error = _check_answer(problem_root, test_file, answer, checker=checker, scratch=scratch)
        if error is not None:
            return error
    test_file.with_name(test_file.name + ".a").write_bytes(answer)
    return None


def _check_answer(
    problem_root: Path,
    test_file: Path,
    answer: bytes,
    *,
    checker: list[str],
    scratch: list[Path],
) -> str | None:
    """Sanity check: the answer must be readable in the problem's own format.

    The checker runs against the same bytes as both ``ouf`` and ``ans``, so it
    validates the *format* (and the input/answer relation, if the checker reads
    the input) without depending on a second solution.
    """
    answer_path = problem_root / f".p2h-{test_file.name}.answer"
    scratch.append(answer_path)
    answer_path.write_bytes(answer)
    stderr_path = problem_root / f".p2h-{test_file.name}.check.err"
    scratch.append(stderr_path)
    stdout_path = problem_root / f".p2h-{test_file.name}.check.out"
    scratch.append(stdout_path)
    with stderr_path.open("wb") as stderr_file, stdout_path.open("wb") as stdout_file:
        try:
            result = subprocess.run(
                [*checker, _relative(problem_root, test_file), answer_path.name, answer_path.name],
                cwd=str(problem_root),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=PER_PASS_TIMEOUT_S,
                **_no_window_kwargs(),
            )
        except subprocess.TimeoutExpired:
            return "checker timed out while validating the answer"
    if result.returncode != 0:
        detail = _read_stderr(stderr_path)
        return f"model answer rejected by the checker ({detail or f'exit code {result.returncode}'})"
    return None


def _unlink_quietly(path: Path, *, attempts: int = 10, delay: float = 0.05) -> None:
    """Remove a scratch file, tolerating a short handle-release lag on Windows."""
    for attempt in range(attempts):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt + 1 >= attempts:
                return
            time.sleep(delay)


class _Relay:
    """Copy one pipe into another, buffering so that neither side deadlocks.

    A single pump thread that reads and immediately writes stops draining the
    source while the destination is full, so two processes that both write
    before reading can deadlock on pipe capacity even through a relay.  Here a
    reader thread keeps draining the source into memory while a writer thread
    feeds the destination, which breaks that cycle.
    """

    def __init__(self, source, destination, name: str) -> None:
        self._source = source
        self._destination = destination
        self._name = name
        self._chunks: queue.Queue[bytes | None] = queue.Queue()
        self._buffered = 0
        self.overflow = False
        self._reader = threading.Thread(
            target=self._read, name=f"p2h-relay-read-{name}", daemon=True
        )
        self._writer = threading.Thread(
            target=self._write, name=f"p2h-relay-write-{name}", daemon=True
        )

    def start(self) -> None:
        self._reader.start()
        self._writer.start()

    def join(self, timeout: float) -> None:
        self._reader.join(timeout)
        self._writer.join(timeout)

    def _read(self) -> None:
        # ``read1`` returns as soon as anything is available: ``read`` on a pipe
        # would wait for the full chunk and turn every short message into a
        # stall (the interactor writes a little, then waits for an answer).
        read = getattr(self._source, "read1", None) or self._source.read
        while True:
            chunk = read(_PUMP_CHUNK)
            if not chunk:
                self._chunks.put(None)
                return
            self._buffered += len(chunk)
            if self._buffered > MAX_CAPTURED_BYTES:
                self.overflow = True
                self._chunks.put(None)
                return
            self._chunks.put(chunk)

    def _write(self) -> None:
        while True:
            chunk = self._chunks.get()
            if chunk is None:
                break
            self._buffered -= len(chunk)
            try:
                self._destination.write(chunk)
                self._destination.flush()
            except (BrokenPipeError, OSError):
                # The other side is gone. Keep draining so that the process
                # feeding this relay can finish instead of blocking forever.
                while self._chunks.get() is not None:
                    pass
                break
        try:
            self._destination.close()
        except OSError:
            pass


def _read_stderr(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    _unlink_quietly(path)
    return text


def _read_optional(path: Path) -> bytes:
    if not path.exists():
        return b""
    return path.read_bytes()


def _relative(problem_root: Path, path: Path) -> str:
    return path.relative_to(problem_root).as_posix()


def _program_command(problem_root: Path, relative: str) -> list[str]:
    if IS_WINDOWS:
        # CreateProcess resolves a relative executable against the parent's
        # working directory, not the child's ``cwd``, so use an absolute path.
        return [str((problem_root / relative).resolve())]
    return ["wine", relative]


def _no_window_kwargs() -> dict[str, object]:
    """Keep spawned programs isolated so timeouts can kill whole process trees."""
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    """Kill the whole process group, including helpers such as ``winedbg``."""
    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
