from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from p2h.hydro import run_twice
from p2h.kinds import ProblemKind
from p2h.models import ProblemData


#: Hydro's problem config schema allows ``multi_pass`` between 2 and 20.
_MAX_MULTI_PASS = 20

#: Source suffix -> Hydro language id, used by the ``lang`` field that Hydro's
#: problem config schema requires next to ``file``.
_LANG_BY_SUFFIX = {
    ".cpp": "cc",
    ".cc": "cc",
    ".cxx": "cc",
    ".c": "cc",
    ".java": "java",
    ".pas": "pas",
    ".py": "py3",
    ".php": "php",
    ".js": "js",
    ".go": "go",
    ".rs": "rs",
}


def source_lang(filename: str) -> str:
    """Hydro language id for a source filename (falling back to ``cc``)."""
    suffix = PurePosixPath(filename).suffix.lower()
    return _LANG_BY_SUFFIX.get(suffix, "cc")


def write_problem_zip(
    *,
    problem: ProblemData,
    output_dir: Path,
    local_id: int,
    pid: str,
    owner: int,
    tags: list[str],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = _next_available_zip_path(output_dir, _safe_filename(problem.title or problem.slug))

    with tempfile.TemporaryDirectory(prefix="p2h-") as td:
        root = Path(td) / str(local_id)
        (root / "testdata").mkdir(parents=True, exist_ok=True)
        testdata_files = list(problem.testdata_files)
        adapter_name: str | None = None

        if problem.kind.needs_multi_pass:
            adapter_name = _build_adapter_file(problem, testdata_files)
        elif problem.kind.needs_interactor and problem.interactor_name:
            _ensure_interactor_file(problem, testdata_files)

        # newline="\n" keeps the package byte-identical on Windows and POSIX:
        # without it write_text() would translate \n to \r\n on Windows.
        (root / "problem.yaml").write_text(
            _build_problem_yaml(pid, owner, problem.title, tags), encoding="utf-8", newline="\n"
        )
        (root / "problem_zh.md").write_text(problem.statement_md, encoding="utf-8", newline="\n")
        (root / "testdata" / "config.yaml").write_text(
            _build_config_yaml(
                problem.time_ms,
                problem.memory_mb,
                test_files=[
                    (case.input_name or f"tests{case.index:02d}.in", case.output_name or f"tests{case.index:02d}.out")
                    for case in problem.tests
                ],
                kind=problem.kind,
                interactor_name=adapter_name if problem.kind.needs_multi_pass else problem.interactor_name,
                checker_name=problem.checker_name,
                run_count=problem.run_count,
            ),
            encoding="utf-8",
            newline="\n",
        )

        for case in problem.tests:
            input_name = case.input_name or f"tests{case.index:02d}.in"
            output_name = case.output_name or f"tests{case.index:02d}.out"
            (root / "testdata" / input_name).write_bytes(case.input_data)
            (root / "testdata" / output_name).write_bytes(case.output_data)

        for name, data in testdata_files:
            target = root / "testdata" / name
            if target.exists():
                raise ValueError(f"{problem.slug}: testdata file collision: {name}")
            target.write_bytes(data)

        if problem.additional_files:
            add_dir = root / "additional_file"
            add_dir.mkdir(parents=True, exist_ok=True)
            for name, data in problem.additional_files:
                target = add_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in root.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(root.parent).as_posix())

    return zip_path


def _build_adapter_file(problem: ProblemData, testdata_files: list[tuple[str, bytes]]) -> str:
    """Add the generated multi_pass interactor source to ``testdata``.

    The adapter embeds the problem's own interactor and checker.  Its filename
    carries the compile language (e.g. ``p2h_interactor.cc.cc17o2``): Hydro's
    ``compileLocalFile`` derives the language from the suffix chain, which also
    lets us force an optimised C++ variant without depending on judge settings.
    """
    if problem.interactor_source is None or problem.checker_source is None:
        raise ValueError(
            f"{problem.slug}: run-twice problem is missing its interactor/checker source"
        )
    lang = run_twice.adapter_lang(
        problem.interactor_source_type,
        problem.checker_source_type,
    )
    name = run_twice.adapter_filename(lang)
    if any(existing == name for existing, _ in testdata_files):
        raise ValueError(f"{problem.slug}: testdata file collision: {name}")
    source = run_twice.build_adapter_source(
        interactor_source=problem.interactor_source,
        checker_source=problem.checker_source,
        run_count=problem.run_count,
        interactor_runs=problem.interactor_runs,
    )
    testdata_files.append((name, source.encode("utf-8")))
    return name


def _ensure_interactor_file(problem: ProblemData, testdata_files: list[tuple[str, bytes]]) -> None:
    """Make sure the interactor source is shipped as testdata.

    Polygon declares the interactor under ``assets/interactor``; most packages
    also list it under ``files/executables`` (which the reader ships), but not
    all do.  Hydro compiles the file named by ``interactor`` from the testdata
    directory, so it has to be there in every case.
    """
    assert problem.interactor_name is not None
    if any(name == problem.interactor_name for name, _ in testdata_files):
        return
    if problem.interactor_source is None:
        raise ValueError(
            f"{problem.slug}: interactive problem is missing its interactor source"
        )
    testdata_files.append((problem.interactor_name, problem.interactor_source.encode("utf-8")))


def _build_problem_yaml(pid: str, owner: int, title: str, tags: list[str]) -> str:
    lines = [
        f"pid: {pid}",
        f"owner: {owner}",
        f"title: {title}",
        "tag:",
    ]
    if tags:
        lines.extend([f"  - '{t}'" for t in tags])
    lines.extend(["nSubmit: 0", "nAccept: 0", ""])
    return "\n".join(lines)


def build_config(
    time_ms: int | None,
    memory_mb: int | None,
    test_files: list[tuple[str, str]],
    *,
    kind: ProblemKind,
    interactor_name: str | None,
    checker_name: str | None,
    run_count: int = 1,
) -> dict:
    """The ``testdata/config.yaml`` content as a plain dict.

    Kept separate from the YAML dump so tests can validate it against Hydro's
    problem-config JSON schema without parsing YAML.
    """
    config: dict = {"type": kind.hydro_type}
    if kind.needs_multi_pass:
        if not interactor_name:
            raise ValueError(f"{kind.key} problem missing generated interactor source")
        if run_count < 2 or run_count > _MAX_MULTI_PASS:
            raise ValueError(
                f"{kind.key} problem needs a run count between 2 and "
                f"{_MAX_MULTI_PASS}, got {run_count}"
            )
        # Official style: a plain filename; the language comes from the suffix
        # chain (``p2h_interactor.cc.cc17o2`` -> ``cc.cc17o2``).
        config["multi_pass"] = run_count
        config["interactor"] = interactor_name
    elif kind.needs_interactor:
        if not interactor_name:
            raise ValueError(f"{kind.key} problem missing interactor source filename")
        config["interactor"] = {"file": interactor_name, "lang": source_lang(interactor_name)}
    elif kind.needs_checker:
        if not checker_name:
            raise ValueError(f"{kind.key} problem missing checker source filename")
        config["checker_type"] = "testlib"
        config["checker"] = {"file": checker_name, "lang": source_lang(checker_name)}
    if time_ms is not None:
        config["time"] = f"{time_ms}ms"
    if memory_mb is not None:
        config["memory"] = f"{memory_mb}MB"
    cases = []
    for input_name, output_name in test_files:
        cases.append({"input": input_name, "output": output_name})
    config["subtasks"] = [{"score": 100, "if": [], "id": 1, "type": "min", "cases": cases}]
    return config


def _build_config_yaml(
    time_ms: int | None,
    memory_mb: int | None,
    test_files: list[tuple[str, str]],
    *,
    kind: ProblemKind,
    interactor_name: str | None,
    checker_name: str | None,
    run_count: int = 1,
) -> str:
    return _dump_yaml(
        build_config(
            time_ms,
            memory_mb,
            test_files,
            kind=kind,
            interactor_name=interactor_name,
            checker_name=checker_name,
            run_count=run_count,
        )
    )


def _dump_yaml(value: object, indent: int = 0) -> str:
    """Serialize the small subset of YAML used by ``testdata/config.yaml``.

    Keeping the dump local avoids a PyYAML dependency and keeps the output
    byte-identical across platforms.  Supports mappings, sequences of mappings,
    strings, integers and empty lists.
    """
    lines: list[str] = []
    if not isinstance(value, dict):
        raise TypeError(f"top-level config must be a mapping, got {type(value)!r}")
    _emit_mapping(value, indent, lines)
    return "\n".join(lines) + "\n"


def _emit_mapping(mapping: dict, key_col: int, lines: list[str]) -> None:
    pad = " " * key_col
    for key, item in mapping.items():
        if isinstance(item, dict):
            lines.append(f"{pad}{key}:")
            _emit_mapping(item, key_col + 2, lines)
        elif isinstance(item, list) and item and isinstance(item[0], dict):
            lines.append(f"{pad}{key}:")
            _emit_mapping_sequence(item, key_col + 2, lines)
        elif isinstance(item, list):
            if not item:
                lines.append(f"{pad}{key}: []")
            else:
                lines.append(f"{pad}{key}:")
                for entry in item:
                    lines.append(f" " * (key_col + 2) + f"- {_yaml_scalar(entry)}")
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar(item)}")


def _emit_mapping_sequence(entries: list[dict], dash_col: int, lines: list[str]) -> None:
    for entry in entries:
        first, *rest = list(entry.items())
        key_col = dash_col + 2
        prefix = " " * dash_col + "- "
        key, item = first
        if isinstance(item, dict):
            lines.append(f"{prefix}{key}:")
            _emit_mapping(item, key_col + 2, lines)
        elif isinstance(item, list) and item and isinstance(item[0], dict):
            lines.append(f"{prefix}{key}:")
            _emit_mapping_sequence(item, key_col + 2, lines)
        elif isinstance(item, list) and not item:
            lines.append(f"{prefix}{key}: []")
        elif isinstance(item, list):
            lines.append(f"{prefix}{key}:")
            for value in item:
                lines.append(" " * (key_col + 2) + f"- {_yaml_scalar(value)}")
        else:
            lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        _emit_mapping(dict(rest), key_col, lines)


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "null"
    text = str(value)
    if not text:
        return "''"
    if any(ch in text for ch in ":#[]{}'\"\n") or text != text.strip():
        escaped = text.replace("'", "''")
        return f"'{escaped}'"
    return text


def _next_available_zip_path(output_dir: Path, base_name: str) -> Path:
    first = output_dir / f"{base_name}.zip"
    if not first.exists():
        return first

    i = 2
    while True:
        candidate = output_dir / f"{base_name} ({i}).zip"
        if not candidate.exists():
            return candidate
        i += 1


def _safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*\n\r\t'
    cleaned = "".join("_" if ch in bad else ch for ch in name).strip()
    return cleaned or "problem"
