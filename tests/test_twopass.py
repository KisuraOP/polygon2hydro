from __future__ import annotations

import io
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.build import twopass


class _Sink:
    """Minimal writable stream for the relay test."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, chunk: bytes) -> int:
        self.data.extend(chunk)
        return len(chunk)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _write_script(directory: Path, name: str, source: str) -> None:
    (directory / name).write_text(textwrap.dedent(source), encoding="utf-8", newline="\n")


SIMPLE_INTERACTOR = """\
import sys

source, tout_path = sys.argv[1], sys.argv[2]
with open(source) as handle:
    first = handle.readline().strip()
print("hello", flush=True)
answer = sys.stdin.readline().strip()
with open(tout_path, "w") as tout:
    tout.write(f"{first}|{answer}\\n")
sys.stderr.write("ok fake interactor\\n")
"""

SIMPLE_PARTICIPANT = """\
import sys

line = sys.stdin.readline().strip()
print("reply-" + line, flush=True)
"""

DEADLOCK_INTERACTOR = """\
import sys

source, tout_path = sys.argv[1], sys.argv[2]
sys.stdout.write("x" * (256 * 1024))
sys.stdout.flush()
received = sys.stdin.buffer.read(200 * 1024)
with open(tout_path, "w") as tout:
    tout.write(str(len(received)))
sys.stderr.write("ok deadlock interactor\\n")
"""

DEADLOCK_PARTICIPANT = """\
import sys

sys.stdout.write("y" * (200 * 1024))
sys.stdout.flush()
sys.stdin.buffer.read(256 * 1024)
"""


def _lf(data: bytes) -> bytes:
    """Normalise CRLF: Windows text-mode children translate newlines."""
    return data.replace(b"\r\n", b"\n")


class TestRelay(unittest.TestCase):
    def test_forwards_data_and_closes_destination(self) -> None:
        source = io.BytesIO(b"chunk-" * 20000)
        sink = _Sink()
        relay = twopass._Relay(source, sink, "test")
        relay.start()
        relay.join(timeout=10)
        self.assertEqual(bytes(sink.data), b"chunk-" * 20000)
        self.assertTrue(sink.closed)
        self.assertFalse(relay.overflow)


class TestPlainPass(unittest.TestCase):
    def test_captures_participant_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            _write_script(
                cwd,
                "solution.py",
                """\
                import sys
                for line in sys.stdin:
                    sys.stdout.write(line.upper())
                """,
            )
            (cwd / "input.txt").write_text("a\nb\n", encoding="utf-8", newline="\n")
            result = twopass.run_plain_pass(
                participant=[sys.executable, "solution.py"],
                input_file="input.txt",
                cwd=cwd,
                timeout_s=30,
            )
            self.assertTrue(result.ok, result.detail)
            self.assertEqual(_lf(result.output), b"A\nB\n")
            self.assertFalse(result.timed_out)

    def test_timeout_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            _write_script(
                cwd,
                "sleep.py",
                """\
                import time
                time.sleep(10)
                """,
            )
            (cwd / "input.txt").write_text("", encoding="utf-8", newline="\n")
            result = twopass.run_plain_pass(
                participant=[sys.executable, "sleep.py"],
                input_file="input.txt",
                cwd=cwd,
                timeout_s=1,
            )
            self.assertTrue(result.timed_out)
            self.assertFalse(result.ok)

    def test_crash_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            _write_script(
                cwd,
                "crash.py",
                """\
                import sys
                sys.stderr.write("boom")
                raise SystemExit(3)
                """,
            )
            (cwd / "input.txt").write_text("", encoding="utf-8", newline="\n")
            result = twopass.run_plain_pass(
                participant=[sys.executable, "crash.py"],
                input_file="input.txt",
                cwd=cwd,
                timeout_s=30,
            )
            self.assertFalse(result.ok)
            self.assertIn("boom", result.detail)


class TestInteractivePass(unittest.TestCase):
    def _problem(self, cwd: Path, interactor: str, participant: str) -> None:
        _write_script(cwd, "interactor.py", interactor)
        _write_script(cwd, "participant.py", participant)
        (cwd / "input.txt").write_text("question\n", encoding="utf-8", newline="\n")

    def test_dialogue_is_hosted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._problem(cwd, SIMPLE_INTERACTOR, SIMPLE_PARTICIPANT)
            result = twopass.run_interactive_pass(
                interactor=[sys.executable, "interactor.py"],
                participant=[sys.executable, "participant.py"],
                input_file="input.txt",
                tout_file="tout.txt",
                cwd=cwd,
                timeout_s=30,
            )
            self.assertTrue(result.ok, result.detail)
            self.assertIn("ok fake interactor", result.detail)
            self.assertEqual(_lf(result.output), b"question|reply-hello\n")

    def test_both_sides_writing_before_reading_does_not_deadlock(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._problem(cwd, DEADLOCK_INTERACTOR, DEADLOCK_PARTICIPANT)
            result = twopass.run_interactive_pass(
                interactor=[sys.executable, "interactor.py"],
                participant=[sys.executable, "participant.py"],
                input_file="input.txt",
                tout_file="tout.txt",
                cwd=cwd,
                timeout_s=30,
            )
            self.assertFalse(result.timed_out, "buffered relay must prevent the pipe deadlock")
            self.assertTrue(result.ok, result.detail)

    def test_timeout_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            self._problem(
                cwd,
                """\
                import time
                time.sleep(30)
                """,
                SIMPLE_PARTICIPANT,
            )
            result = twopass.run_interactive_pass(
                interactor=[sys.executable, "interactor.py"],
                participant=[sys.executable, "participant.py"],
                input_file="input.txt",
                tout_file="tout.txt",
                cwd=cwd,
                timeout_s=1,
            )
            self.assertTrue(result.timed_out)


class TestApplicability(unittest.TestCase):
    def test_not_applicable_without_binaries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(twopass.is_applicable(Path(td)))

    def test_generate_answers_returns_none_when_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(
                twopass.generate_answers(
                    Path(td), run_count=2, interactor_runs=frozenset({1})
                )
            )


class TestProgramCommand(unittest.TestCase):
    def test_windows_uses_an_absolute_executable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(twopass, "IS_WINDOWS", True):
                command = twopass._program_command(root, "solutions/main.exe")
            self.assertEqual(len(command), 1)
            self.assertTrue(Path(command[0]).is_absolute())
            self.assertEqual(Path(command[0]), (root / "solutions" / "main.exe").resolve())

    def test_posix_runs_through_wine(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(twopass, "IS_WINDOWS", False):
                command = twopass._program_command(Path(td), "solutions/main.exe")
            self.assertEqual(command, ["wine", "solutions/main.exe"])


if __name__ == "__main__":
    unittest.main()
