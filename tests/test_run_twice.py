from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.hydro import run_twice


INTERACTOR = """\
#include "testlib.h"
#include <vector>
int main(int argc, char* argv[])
{
    registerInteraction(argc, argv);
    tout << inf.readInt() << '\\n';
    quitf(_ok, "interactor done");
}
"""

CHECKER = """\
#include "testlib.h"
#include <string>
int main(int argc, char* argv[])
{
    registerTestlibCmd(argc, argv);
    if (ouf.readInt() != ans.readInt()) quitf(_wa, "different");
    quitf(_ok, "same");
}
"""


def _build(*, run_count: int = 2, runs=frozenset({1})) -> str:
    return run_twice.build_adapter_source(
        interactor_source=INTERACTOR,
        checker_source=CHECKER,
        run_count=run_count,
        interactor_runs=runs,
    )


class TestAdapterSource(unittest.TestCase):
    def test_is_deterministic(self) -> None:
        self.assertEqual(_build(), _build())

    def test_entry_points_are_renamed_and_exported(self) -> None:
        source = _build()
        self.assertIn("namespace p2h_interactor_impl {", source)
        self.assertIn("#define main p2h_polygon_interactor_entry", source)
        self.assertIn("namespace p2h_checker_impl {", source)
        self.assertIn("#define main p2h_polygon_checker_entry", source)
        self.assertIn("using p2h_interactor_impl::p2h_polygon_interactor_entry;", source)
        self.assertIn("using p2h_checker_impl::p2h_polygon_checker_entry;", source)
        # Exactly one program entry point: the adapter dispatches to the renamed
        # originals, which ``#define main`` rewrites at compile time.
        self.assertEqual(source.count("return p2h_adapter::run(argc, argv);"), 1)

    def test_includes_are_hoisted_out_of_the_namespaces(self) -> None:
        source = _build()
        interactor_start = source.index("namespace p2h_interactor_impl {")
        interactor_end = source.index("}  // namespace p2h_interactor_impl")
        checker_start = source.index("namespace p2h_checker_impl {")
        checker_end = source.index("}  // namespace p2h_checker_impl")
        for start, end in ((interactor_start, interactor_end), (checker_start, checker_end)):
            body = source[start:end]
            self.assertNotIn("#include", body)

    def test_first_run_only_by_default(self) -> None:
        self.assertIn("constexpr unsigned kInteractiveMask = 1u;", _build())

    def test_mask_for_second_run(self) -> None:
        self.assertIn(
            "constexpr unsigned kInteractiveMask = 2u;",
            _build(run_count=2, runs=frozenset({2})),
        )

    def test_mask_for_both_runs(self) -> None:
        self.assertIn(
            "constexpr unsigned kInteractiveMask = 3u;",
            _build(run_count=2, runs=frozenset({1, 2})),
        )

    def test_run_count_is_baked_in(self) -> None:
        self.assertIn("constexpr int kRunCount = 3;", _build(run_count=3, runs=frozenset({1})))

    def test_bundle_magic_is_quoted(self) -> None:
        self.assertIn('"P2H1"', _build())

    def test_carries_hydro_protocol_bits(self) -> None:
        source = _build()
        self.assertIn("nextpass.in", source)
        self.assertIn('const char* pass_env = std::getenv("HYDRO_MULTI_PASS");', source)
        # The adapter itself must not trigger testlib's finalize guard.
        self.assertIn("disableFinalizeGuard();", source)
        self.assertEqual(source.count("testlibFinalizeGuard.alive = true;"), 2)

    def test_interactive_runs_use_a_buffered_relay(self) -> None:
        source = _build()
        # A direct pipe deadlocks when both sides write before reading; real
        # solutions print an answer for one test case while still reading the
        # next one.  The relay must buffer and the pipe must be non-blocking.
        self.assertIn("int relay_to_fd(int to_fd)", source)
        self.assertIn("O_NONBLOCK", source)
        self.assertIn("kMaxRelayBuffer", source)

    def test_rejects_too_few_runs(self) -> None:
        with self.assertRaises(ValueError) as cm:
            _build(run_count=1)
        self.assertIn("at least 2 runs", str(cm.exception))

    def test_rejects_empty_interactive_runs(self) -> None:
        with self.assertRaises(ValueError) as cm:
            _build(run_count=2, runs=frozenset())
        self.assertIn("at least one interactive run", str(cm.exception))

    def test_rejects_out_of_range_runs(self) -> None:
        with self.assertRaises(ValueError) as cm:
            _build(run_count=2, runs=frozenset({3}))
        self.assertIn("do not fit", str(cm.exception))

    def test_crlf_source_is_normalized(self) -> None:
        source = run_twice.build_adapter_source(
            interactor_source=INTERACTOR.replace("\n", "\r\n"),
            checker_source=CHECKER.replace("\n", "\r\n"),
            run_count=2,
            interactor_runs=frozenset({1}),
        )
        self.assertNotIn("\r", source)


if __name__ == "__main__":
    unittest.main()
