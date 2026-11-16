"""Generate the Hydro interactor that judges a Polygon run-twice problem.

Hydro has no first-class "run the participant twice" problem type.  What it has
is ``multi_pass``: for ``type: interactive`` problems the interactor is restarted
for every pass, and it can hand the next pass's input back through a file called
``nextpass.in``.  One pass corresponds to one *run* of a Polygon run-twice
problem, so a converted problem is:

    type: interactive
    multi_pass: <run-count>
    interactor: p2h_interactor.cpp

The generated program reproduces Polygon's judging model.  Every run has one
input file; runs listed in the problem's ``<interactor><runs>`` are
*interactive*: the participant's process talks to the original interactor over
pipes, and the interactor's ``tout`` becomes the next run's input.  Runs not
listed there are *plain*: the participant reads the input file and its stdout
becomes the next run's input.  After the last run the original checker judges
``<test input> <last run's output channel> <expected answer>``.

Three things Hydro's interactive judging does not give us, and this program adds:

1. **A file input for plain runs.**  Hydro always connects the participant's
   stdin to the interactor's stdout, so the program writes the run's input there
   itself and closes its stdout to signal the end of the data.
2. **The original test input on the last pass.**  The checker needs it.  Hydro
   only forwards ``nextpass.in``, so every intermediate pass writes a bundle:
   a header, the original input, then the run's output channel.
3. **The checker.**  Hydro's interactive judge never runs a ``checker``, so the
   checker source is compiled into this program and executed as a child process.

Interactive runs go through a buffered relay rather than a direct pipe.  Real
solutions write output while they are still reading later test cases, so both
sides can be blocked writing at the same time; a direct pipe deadlocks there
(observed: after the fifth test of a real problem the model solution was killed
with "returned 9").  The relay buffers whatever the participant writes, so the
interactor always makes progress.

Both the original interactor and the original checker are embedded verbatim,
with their ``main`` renamed, so their behaviour stays Polygon's.
"""

from __future__ import annotations

import re


ADAPTER_FILENAME = "p2h_interactor.cpp"

INTERACTOR_ENTRY = "p2h_polygon_interactor_entry"
CHECKER_ENTRY = "p2h_polygon_checker_entry"

_BUNDLE_MAGIC = "P2H1"

_INCLUDE_RE = re.compile(r"^\s*#\s*include\b")


def build_adapter_source(
    *,
    interactor_source: str,
    checker_source: str,
    run_count: int,
    interactor_runs: frozenset[int] | set[int],
) -> str:
    """Compose the single C++ file Hydro will compile as the interactor."""
    if run_count < 2:
        raise ValueError(f"run-twice adapter needs at least 2 runs, got {run_count}")
    runs = sorted(set(interactor_runs))
    if not runs:
        raise ValueError("run-twice adapter needs at least one interactive run")
    if runs[0] < 1 or runs[-1] > run_count:
        raise ValueError(f"interactive runs {runs} do not fit into {run_count} run(s)")

    mask = 0
    for run in runs:
        mask |= 1 << (run - 1)

    interactor_includes, interactor_body = _split_source(interactor_source)
    checker_includes, checker_body = _split_source(checker_source)

    parts: list[str] = [
        _HEADER,
        '#include "testlib.h"',
        *_unique(interactor_includes + checker_includes),
        "",
        "namespace p2h_interactor_impl {",
        f"#define main {INTERACTOR_ENTRY}",
        interactor_body,
        "#undef main",
        "}  // namespace p2h_interactor_impl",
        "",
        "namespace p2h_checker_impl {",
        f"#define main {CHECKER_ENTRY}",
        checker_body,
        "#undef main",
        "}  // namespace p2h_checker_impl",
        "",
        f"using p2h_interactor_impl::{INTERACTOR_ENTRY};",
        f"using p2h_checker_impl::{CHECKER_ENTRY};",
        "",
    ]
    adapter = (
        _ADAPTER.replace("P2H_RUN_COUNT", str(run_count))
        .replace("P2H_INTERACTIVE_MASK", f"{mask}u")
        .replace("P2H_INTERACTOR_ENTRY", INTERACTOR_ENTRY)
        .replace("P2H_CHECKER_ENTRY", CHECKER_ENTRY)
        .replace("P2H_BUNDLE_MAGIC", f'"{_BUNDLE_MAGIC}"')
    )
    parts.append(adapter)
    return "\n".join(parts).rstrip() + "\n"


def _split_source(source: str) -> tuple[list[str], str]:
    """Hoist ``#include`` lines so the rest can live inside a namespace.

    A ``#include`` inside a namespace would put the whole standard library into
    that namespace, so the directives are collected first and emitted at the top
    of the generated file.  Polygon's interactors and checkers only include
    headers at the top of the file, unconditionally.
    """
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    includes: list[str] = []
    body: list[str] = []
    for line in text.split("\n"):
        if _INCLUDE_RE.match(line):
            includes.append(line.strip())
        else:
            body.append(line)
    return includes, "\n".join(body).strip()


def _unique(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        result.append(line)
    return result


_HEADER = """\
// Generated by polygon2hydro. Do not edit.
//
// This file is the Hydro interactor for a Polygon run-twice ("communication")
// problem. It carries the problem's own interactor and checker and emulates
// Polygon's judging protocol on top of Hydro's multi_pass protocol. See
// src/p2h/hydro/run_twice.py for the full description."""


_ADAPTER = r"""
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

namespace p2h_adapter {

constexpr int kRunCount = P2H_RUN_COUNT;
constexpr unsigned kInteractiveMask = P2H_INTERACTIVE_MASK;

constexpr const char* kPassInput = ".p2h_pass.in";
constexpr const char* kOriginalInput = ".p2h_original.in";
constexpr const char* kTout = ".p2h_tout";
constexpr const char* kUserOutput = ".p2h_user.out";
constexpr const char* kInteractorStderr = ".p2h_interactor.err";
constexpr const char* kCheckerStderr = ".p2h_checker.err";
constexpr const char* kNextPass = "nextpass.in";

[[noreturn]] void system_fail(const std::string& message) {
    std::fprintf(stderr, "status(8) p2h adapter: %s\n", message.c_str());
    std::fflush(stderr);
    std::_Exit(3);
}

bool read_file(const char* path, std::string* out) {
    std::FILE* file = std::fopen(path, "rb");
    if (file == nullptr) return false;
    std::string data;
    char buffer[65536];
    size_t count = 0;
    while ((count = std::fread(buffer, 1, sizeof buffer, file)) > 0) {
        data.append(buffer, count);
    }
    bool ok = std::ferror(file) == 0;
    std::fclose(file);
    if (ok) *out = std::move(data);
    return ok;
}

bool read_optional_file(const char* path, std::string* out) {
    out->clear();
    std::FILE* file = std::fopen(path, "rb");
    if (file == nullptr) return true;
    char buffer[65536];
    size_t count = 0;
    while ((count = std::fread(buffer, 1, sizeof buffer, file)) > 0) {
        out->append(buffer, count);
    }
    bool ok = std::ferror(file) == 0;
    std::fclose(file);
    return ok;
}

bool write_file(const char* path, const std::string& data) {
    std::FILE* file = std::fopen(path, "wb");
    if (file == nullptr) return false;
    bool ok = std::fwrite(data.data(), 1, data.size(), file) == data.size();
    ok = std::fclose(file) == 0 && ok;
    return ok;
}

std::string make_bundle(const std::string& original, const std::string& payload) {
    char header[64];
    std::snprintf(header, sizeof header, "%s %zu\n", P2H_BUNDLE_MAGIC, original.size());
    return std::string(header) + original + payload;
}

bool parse_bundle(const std::string& data, std::string* original, std::string* payload) {
    const std::size_t magic_len = std::strlen(P2H_BUNDLE_MAGIC);
    if (data.size() < magic_len + 2) return false;
    if (data.compare(0, magic_len, P2H_BUNDLE_MAGIC) != 0) return false;
    std::size_t pos = magic_len;
    if (data[pos] != ' ') return false;
    ++pos;
    std::size_t length = 0;
    std::size_t digits = 0;
    while (pos < data.size() && data[pos] >= '0' && data[pos] <= '9') {
        if (length > (data.size() >> 1) + 1) return false;
        length = length * 10 + static_cast<std::size_t>(data[pos] - '0');
        ++pos;
        ++digits;
    }
    if (digits == 0 || pos >= data.size() || data[pos] != '\n') return false;
    ++pos;
    if (length > data.size() - pos) return false;
    original->assign(data, pos, length);
    payload->assign(data, pos + length, std::string::npos);
    return true;
}

std::string last_nonempty_line(const std::string& text) {
    std::size_t end = text.size();
    while (end > 0) {
        std::size_t begin = text.rfind('\n', end - 1);
        if (begin == std::string::npos) begin = 0;
        else ++begin;
        std::size_t stop = end;
        while (stop > begin && (text[stop - 1] == '\r' || text[stop - 1] == ' ' || text[stop - 1] == '\t')) {
            --stop;
        }
        if (stop > begin) return text.substr(begin, stop - begin);
        if (begin == 0) break;
        end = begin - 1;
    }
    return std::string();
}

bool is_testlib_verdict(const std::string& text) {
    static const char* prefixes[] = {
        "ok ",
        "wrong answer ",
        "wrong output format ",
        "presentation error ",
        "partially correct ",
        "points ",
        "FAIL ",
    };
    for (const char* prefix : prefixes) {
        if (text.compare(0, std::strlen(prefix), prefix) == 0) return true;
    }
    return false;
}

// Relay one child's verdict to Hydro, which parses testlib's stderr prefixes.
int relay_verdict(const std::string& stderr_text, int code) {
    if (is_testlib_verdict(stderr_text)) {
        std::fwrite(stderr_text.data(), 1, stderr_text.size(), stderr);
        if (stderr_text.empty() || stderr_text[stderr_text.size() - 1] != '\n') std::fputc('\n', stderr);
        std::fflush(stderr);
        return code;
    }
    std::string line = last_nonempty_line(stderr_text);
    if (is_testlib_verdict(line)) {
        std::fprintf(stderr, "%s\n", line.c_str());
        std::fflush(stderr);
        return code;
    }
    if (code == 0) {
        std::fprintf(stderr, "ok p2h adapter: %s\n", line.empty() ? "run finished" : line.c_str());
        std::fflush(stderr);
        return 0;
    }
    std::fprintf(
        stderr,
        "wrong answer p2h adapter: %s\n",
        line.empty() ? "interactor failed without a message" : line.c_str()
    );
    std::fflush(stderr);
    return code;
}

int announce_ok(const char* what) {
    std::fprintf(stderr, "ok p2h adapter: %s\n", what);
    std::fflush(stderr);
    return 0;
}

struct ChildResult {
    int code;
    bool signalled;
};

ChildResult wait_child(pid_t pid) {
    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) return {-1, false};
    }
    if (WIFEXITED(status)) return {WEXITSTATUS(status), false};
    if (WIFSIGNALED(status)) return {128 + WTERMSIG(status), true};
    return {-1, false};
}

void redirect(int old_fd, int new_fd) {
    if (old_fd < 0) return;
    if (dup2(old_fd, new_fd) < 0) std::_Exit(101);
    close(old_fd);
}

void redirect_stderr_to(const char* path) {
    redirect(open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644), 2);
}

void fail_if_signalled(const ChildResult& result, const char* who) {
    if (!result.signalled) return;
    system_fail(std::string(who) + " crashed with signal " + std::to_string(result.code - 128));
}

// Write a run's input to the participant (Hydro made our stdout the
// participant's stdin) and then let it see end of file.
pid_t start_input_writer(const std::string& input) {
    pid_t pid = fork();
    if (pid != 0) return pid;
    signal(SIGPIPE, SIG_IGN);
    close(0);
    std::size_t offset = 0;
    while (offset < input.size()) {
        ssize_t written = write(1, input.data() + offset, input.size() - offset);
        if (written < 0) {
            if (errno == EINTR) continue;
            std::_Exit(0);
        }
        offset += static_cast<std::size_t>(written);
    }
    std::_Exit(0);
}

void reap_writer(pid_t writer_pid) {
    if (writer_pid <= 0) return;
    int status = 0;
    if (waitpid(writer_pid, &status, WNOHANG) == 0) {
        // The participant stopped reading; do not let the writer outlive us.
        kill(writer_pid, SIGKILL);
        waitpid(writer_pid, &status, 0);
    }
}

// Forward the participant's stdout to the interactor.  Returns 0 at end of
// file, 1 when the interactor stopped reading and -1 on a local error.
//
// The unread part is buffered: a plain read-then-write loop stops draining the
// participant while the interactor is not reading yet, and two processes that
// both write more than a pipe buffer before reading then deadlock (real case:
// solutions that print the answer for one test case while still reading the
// next one; a direct pipe kills the model solution on the fifth test).
int relay_to_fd(int to_fd) {
    constexpr std::size_t kMaxRelayBuffer = 256u * 1024u * 1024u;
    std::string pending;
    bool user_eof = false;
    char buffer[65536];
    while (!user_eof || !pending.empty()) {
        struct pollfd fds[2];
        int count = 0;
        int in_slot = -1;
        int out_slot = -1;
        if (!user_eof) {
            fds[count].fd = 0;
            fds[count].events = POLLIN;
            fds[count].revents = 0;
            in_slot = count++;
        }
        if (!pending.empty()) {
            fds[count].fd = to_fd;
            fds[count].events = POLLOUT;
            fds[count].revents = 0;
            out_slot = count++;
        }
        int rc = poll(fds, static_cast<nfds_t>(count), -1);
        if (rc < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (in_slot >= 0 && (fds[in_slot].revents & (POLLIN | POLLHUP | POLLERR))) {
            ssize_t got = read(0, buffer, sizeof buffer);
            if (got < 0) {
                if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) continue;
                return -1;
            } else if (got == 0) {
                user_eof = true;
            } else {
                pending.append(buffer, static_cast<std::size_t>(got));
                if (pending.size() > kMaxRelayBuffer) return -1;
            }
        }
        if (out_slot >= 0 && (fds[out_slot].revents & (POLLOUT | POLLHUP | POLLERR))) {
            ssize_t written = write(to_fd, pending.data(), pending.size());
            if (written < 0) {
                if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) continue;
                return 1;
            }
            pending.erase(0, static_cast<std::size_t>(written));
        }
    }
    return 0;
}

// Capture the participant's stdout into a file (plain runs).
bool pump_to_file(const char* path) {
    std::FILE* capture = std::fopen(path, "wb");
    if (capture == nullptr) return false;
    char buffer[65536];
    bool ok = true;
    for (;;) {
        ssize_t count = read(0, buffer, sizeof buffer);
        if (count < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) continue;
            ok = false;
            break;
        }
        if (count == 0) break;
        if (std::fwrite(buffer, 1, static_cast<std::size_t>(count), capture) != static_cast<std::size_t>(count)) {
            ok = false;
            break;
        }
    }
    ok = std::fclose(capture) == 0 && ok;
    return ok;
}

int run_checker(const char* self, const std::string& answer_path, const char* output_channel) {
    pid_t pid = fork();
    if (pid < 0) system_fail("fork() failed for the checker");
    if (pid == 0) {
        redirect(open("/dev/null", O_RDONLY), 0);
        redirect(open("/dev/null", O_WRONLY), 1);
        redirect_stderr_to(kCheckerStderr);
        testlibFinalizeGuard.alive = true;
        char* args[] = {
            const_cast<char*>(self),
            const_cast<char*>(kOriginalInput),
            const_cast<char*>(output_channel),
            const_cast<char*>(answer_path.c_str()),
            nullptr,
        };
        int code = p2h_polygon_checker_entry(4, args);
        std::exit(code);
    }
    ChildResult result = wait_child(pid);
    fail_if_signalled(result, "checker");
    std::string stderr_text;
    read_optional_file(kCheckerStderr, &stderr_text);
    return relay_verdict(stderr_text, result.code);
}

int write_next_pass(const std::string& original_input, const char* payload_path) {
    std::string payload;
    read_optional_file(payload_path, &payload);
    if (!write_file(kNextPass, make_bundle(original_input, payload))) {
        system_fail("cannot write nextpass.in");
    }
    return 0;
}

int run_interactive_pass(
    const char* self,
    const std::string& original_input,
    const std::string& answer_path,
    bool final_pass
) {
    int pipe_fds[2];
    if (pipe(pipe_fds) != 0) system_fail("pipe() failed");
    std::fflush(stdout);
    std::fflush(stderr);
    pid_t interactor_pid = fork();
    if (interactor_pid < 0) system_fail("fork() failed for the interactor");
    if (interactor_pid == 0) {
        redirect(pipe_fds[0], 0);  // the participant's stdout
        close(pipe_fds[1]);
        redirect_stderr_to(kInteractorStderr);
        testlibFinalizeGuard.alive = true;
        char* args[] = {
            const_cast<char*>(self),
            const_cast<char*>(kPassInput),
            const_cast<char*>(kTout),
            const_cast<char*>(answer_path.c_str()),
            nullptr,
        };
        int code = p2h_polygon_interactor_entry(4, args);
        std::exit(code);
    }
    close(pipe_fds[0]);
    // Non-blocking: poll() only promises that a write will not block for the
    // first PIPE_BUF bytes while this relay may have megabytes buffered.
    int pipe_flags = fcntl(pipe_fds[1], F_GETFL, 0);
    if (pipe_flags >= 0) fcntl(pipe_fds[1], F_SETFL, pipe_flags | O_NONBLOCK);
    int relay_status = relay_to_fd(pipe_fds[1]);
    close(pipe_fds[1]);
    close(1);
    if (relay_status < 0) system_fail("cannot relay the participant output");
    ChildResult result = wait_child(interactor_pid);
    fail_if_signalled(result, "interactor");
    std::string stderr_text;
    read_optional_file(kInteractorStderr, &stderr_text);
    if (result.code != 0) return relay_verdict(stderr_text, result.code);
    if (final_pass) return run_checker(self, answer_path, kTout);
    relay_verdict(stderr_text, 0);
    return write_next_pass(original_input, kTout);
}

int run_plain_pass(
    const char* self,
    const std::string& pass_input,
    const std::string& original_input,
    const std::string& answer_path,
    bool final_pass
) {
    std::fflush(stdout);
    std::fflush(stderr);
    pid_t writer_pid = start_input_writer(pass_input);
    if (writer_pid < 0) system_fail("fork() failed for the input writer");
    close(1);
    if (!pump_to_file(kUserOutput)) system_fail("cannot capture the participant output");
    reap_writer(writer_pid);
    if (final_pass) return run_checker(self, answer_path, kUserOutput);
    announce_ok("plain run finished");
    return write_next_pass(original_input, kUserOutput);
}

int run(int argc, char** argv) {
    // This process is not itself a testlib program; only the children register.
    // Without this the guard would append "Call register-function ..." to every
    // verdict on exit.  Children re-enable it before calling their entry point.
    disableFinalizeGuard();
    signal(SIGPIPE, SIG_IGN);

    std::string input_path = argc > 1 ? argv[1] : "in";
    std::string answer_path = argc > 3 ? argv[3] : "out";

    const char* pass_env = std::getenv("HYDRO_MULTI_PASS");
    int pass = (pass_env != nullptr && *pass_env != '\0') ? std::atoi(pass_env) : 1;
    if (pass < 1) pass = 1;
    const bool final_pass = pass >= kRunCount;
    const bool interactive = ((kInteractiveMask >> (pass - 1)) & 1u) != 0;

    std::string raw;
    if (!read_file(input_path.c_str(), &raw)) {
        system_fail("cannot read the pass input " + input_path);
    }

    std::string original_input;
    std::string pass_input;
    if (pass <= 1) {
        original_input = raw;
        pass_input = raw;
    } else if (!parse_bundle(raw, &original_input, &pass_input)) {
        system_fail("malformed run-twice bundle in " + input_path);
    }

    if (!write_file(kPassInput, pass_input)) system_fail("cannot write the pass input copy");
    if (!write_file(kOriginalInput, original_input)) system_fail("cannot write the original input copy");
    std::remove(kTout);
    std::remove(kUserOutput);
    std::remove(kInteractorStderr);
    std::remove(kCheckerStderr);

    return interactive
        ? run_interactive_pass(argv[0], original_input, answer_path, final_pass)
        : run_plain_pass(argv[0], pass_input, original_input, answer_path, final_pass);
}

}  // namespace p2h_adapter

int main(int argc, char** argv) {
    return p2h_adapter::run(argc, argv);
}
"""
