from __future__ import annotations

import re
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

    def test_carries_hydro_multi_pass_protocol(self) -> None:
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

    def test_plain_runs_stream_input_and_output(self) -> None:
        source = _build()
        # Plain runs write the pass input from a child while capturing the
        # participant output, so a full pipe cannot deadlock.
        self.assertIn("pid_t start_input_writer(const std::string& input)", source)
        self.assertIn("bool pump_to_file(const char* path)", source)

    def test_checker_reads_original_input_and_answer(self) -> None:
        source = _build()
        self.assertIn("int run_checker(const char* self, const std::string& answer_path", source)
        self.assertIn("const_cast<char*>(kOriginalInput)", source)
        self.assertIn("const_cast<char*>(answer_path.c_str())", source)

    def test_rejects_too_few_runs(self) -> None:
        with self.assertRaises(ValueError) as cm:
            _build(run_count=1)
        self.assertIn("at least 2 runs", str(cm.exception))

    def test_rejects_too_many_runs(self) -> None:
        # Hydro's problem config schema caps multi_pass at 20.
        with self.assertRaises(ValueError) as cm:
            _build(run_count=21)
        self.assertIn("at most 20 passes", str(cm.exception))

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

    def test_adapter_template_is_shared_by_all_problems(self) -> None:
        """One fixed template composes every problem; only data changes.

        A problem-specific adapter would make the converter problem-dependent.
        After removing the embedded interactor/checker bodies, the hoisted
        ``#include`` lines and the per-problem constants, adapters for two
        completely different problems must be identical.
        """
        other_interactor = (
            '#include "testlib.h"\n#include <map>\n'
            "int main(int argc, char* argv[]) { registerInteraction(argc, argv); quitf(_ok, \"x\"); }\n"
        )
        other_checker = (
            '#include "testlib.h"\n'
            "int main(int argc, char* argv[]) { registerTestlibCmd(argc, argv); quitf(_ok, \"y\"); }\n"
        )
        first = _build()
        second = run_twice.build_adapter_source(
            interactor_source=other_interactor,
            checker_source=other_checker,
            run_count=3,
            interactor_runs=frozenset({1, 3}),
        )

        def skeleton(source: str, interactor: str, checker: str) -> str:
            _, interactor_body = run_twice._split_source(interactor)
            _, checker_body = run_twice._split_source(checker)
            source = source.replace(interactor_body, "<INTERACTOR>")
            source = source.replace(checker_body, "<CHECKER>")
            source = re.sub(r'^#include (?!\"testlib\.h\").*\n?', "", source, flags=re.M)
            source = re.sub(r"^constexpr int kRunCount = \d+;$", "constexpr int kRunCount = N;", source, flags=re.M)
            source = re.sub(
                r"^constexpr unsigned kInteractiveMask = \d+u;$",
                "constexpr unsigned kInteractiveMask = MASK;",
                source,
                flags=re.M,
            )
            return source

        self.assertEqual(
            skeleton(first, INTERACTOR, CHECKER),
            skeleton(second, other_interactor, other_checker),
        )


class TestAdapterLanguage(unittest.TestCase):
    def test_declared_cpp_standards(self) -> None:
        self.assertEqual(
            run_twice.adapter_lang("cpp.gcc14-64-msys2-g++23", "cpp.g++17"),
            "cc.cc20o2",
        )
        self.assertEqual(run_twice.adapter_lang("cpp.g++17"), "cc.cc17o2")
        self.assertEqual(run_twice.adapter_lang("cpp.g++14"), "cc.cc14o2")
        self.assertEqual(run_twice.adapter_lang("cpp.g++11"), "cc.cc11o2")
        self.assertEqual(run_twice.adapter_lang("cpp.g++98"), "cc.cc98o2")

    def test_unknown_cpp_defaults_to_optimised_cpp14(self) -> None:
        self.assertEqual(run_twice.adapter_lang(None, None), "cc.cc14o2")
        self.assertEqual(run_twice.adapter_lang("cpp"), "cc.cc14o2")

    def test_non_cpp_source_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as cm:
            run_twice.adapter_lang("java.8")
        self.assertIn("non-C++", str(cm.exception))

    def test_filename_encodes_language_for_hydro(self) -> None:
        # compileLocalFile tries suffixes from the right: ``cc17o2`` is unknown,
        # ``cc.cc17o2`` is known -- the same trick as Hydro's official example
        # (``manager.cc.cc17o2``).
        self.assertEqual(run_twice.adapter_filename("cc.cc17o2"), "p2h_interactor.cc.cc17o2")
        self.assertEqual(run_twice.adapter_filename("cc.cc20o2"), "p2h_interactor.cc.cc20o2")
        self.assertEqual(run_twice.adapter_filename("cc"), "p2h_interactor.cc")
        with self.assertRaises(ValueError):
            run_twice.adapter_filename("py3")


if __name__ == "__main__":
    unittest.main()
