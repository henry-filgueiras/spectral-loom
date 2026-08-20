"""The ``spectral-loom`` command line: infrastructure only.

Three commands, none of which downloads, generates, infers, or renders anything::

    spectral-loom doctor [--json]
    spectral-loom validate-spec PATH [--json]
    spectral-loom validate-timeline PATH [--json]

Exit codes are stable and are part of the interface:

===  ==========================================================================
0    success; the document is valid, or ``doctor`` found no blocking problem
1    a blocking problem: a prerequisite that must hold and does not
2    the document was read but is not valid against its contract
3    the input could not be read at all
===  ==========================================================================

``doctor`` deliberately separates two questions that are easy to conflate:
whether this checkout is healthy, and whether it is ready to run inference. A
missing model dependency answers the second and is reported as information. It
never changes the exit code.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from spectral_loom import __version__
from spectral_loom.contracts import SongSpec, SongTimeline

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INVALID = 2
EXIT_UNREADABLE = 3

#: Packages a future round will need. Absent is the expected state today, and
#: `archaeology/decisions/0005` is why they are not in the default environment.
FUTURE_MODEL_PACKAGES: tuple[tuple[str, str], ...] = (
    ("torch", "tensor runtime for the model cabinet"),
    ("demucs", "source separation (stage 3)"),
    ("basic_pitch", "note inference (stage 5)"),
    ("acestep", "music generation (stage 2)"),
)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


class Check(BaseModel):
    """One reported observation about the local environment."""

    name: str
    status: str  # "ok" | "info" | "warn" | "fail"
    detail: str


def _sysctl(key: str) -> str | None:
    """Read one sysctl value, or None where it is unavailable."""
    if platform.system() != "Darwin" or shutil.which("sysctl") is None:
        return None
    try:
        result = subprocess.run(
            ["sysctl", "-n", key], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _tool_version(executable: str, *args: str) -> str | None:
    """First line of a tool's version output, or None if it cannot be run."""
    path = shutil.which(executable)
    if path is None:
        return None
    try:
        result = subprocess.run(
            [path, *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    line = (result.stdout or result.stderr).strip().splitlines()
    return line[0] if line else path


def _repository_root(start: Path) -> Path:
    """Nearest ancestor holding a `.git`, else the starting directory."""
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return start


def _writable(path: Path) -> tuple[bool, Path]:
    """Whether `path` could be written, judged at its nearest existing ancestor.

    Deliberately does not create anything: `doctor` reports on the world, it does
    not change it.
    """
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return os.access(probe, os.W_OK), probe


def collect_checks(root: Path | None = None) -> list[Check]:
    """Gather every environment observation `doctor` reports."""
    repo = _repository_root(root or Path.cwd())
    checks: list[Check] = []

    checks.append(
        Check(
            name="os",
            status="ok",
            detail=f"{platform.system()} {platform.release()} ({platform.machine()})",
        )
    )
    if platform.system() == "Darwin":
        macos = platform.mac_ver()[0]
        if macos:
            checks.append(Check(name="macos", status="ok", detail=macos))
        chip = _sysctl("machdep.cpu.brand_string")
        if chip:
            cores = _sysctl("hw.ncpu")
            checks.append(
                Check(
                    name="chip", status="ok", detail=f"{chip}{f' ({cores} cores)' if cores else ''}"
                )
            )
        memsize = _sysctl("hw.memsize")
        if memsize and memsize.isdigit():
            checks.append(
                Check(
                    name="unified-memory",
                    status="ok",
                    detail=f"{int(memsize) / (1024**3):.0f} GiB",
                )
            )

    running = platform.python_version()
    expected_major_minor = (3, 11)
    on_expected = sys.version_info[:2] == expected_major_minor
    checks.append(
        Check(
            name="python",
            status="ok" if on_expected else "fail",
            detail=(
                f"{running} at {sys.executable}"
                if on_expected
                else f"{running} at {sys.executable}; this project requires 3.11"
            ),
        )
    )

    uv = _tool_version("uv", "--version")
    checks.append(
        Check(
            name="uv",
            status="ok" if uv else "warn",
            detail=uv or "not found; uv owns this project's environment and lockfile",
        )
    )

    ffmpeg = _tool_version("ffmpeg", "-version")
    checks.append(
        Check(
            name="ffmpeg",
            status="ok" if ffmpeg else "warn",
            detail=ffmpeg or "not found; audio stages will need it",
        )
    )

    checks.append(Check(name="repository", status="ok", detail=str(repo)))

    for relative in (".work", ".cache", "outputs"):
        target = repo / relative
        writable, probe = _writable(target)
        checks.append(
            Check(
                name=f"writable:{relative}",
                status="ok" if writable else "fail",
                detail=(
                    f"{target} ({'exists' if target.exists() else f'creatable under {probe}'})"
                    if writable
                    else f"{probe} is not writable"
                ),
            )
        )

    for package, purpose in FUTURE_MODEL_PACKAGES:
        present = importlib.util.find_spec(package) is not None
        checks.append(
            Check(
                name=f"model-dep:{package}",
                status="ok" if present else "info",
                detail=(
                    f"importable — {purpose}"
                    if present
                    else f"absent (expected at this stage) — {purpose}"
                ),
            )
        )

    return checks


def doctor(as_json: bool, root: Path | None = None) -> int:
    checks = collect_checks(root)
    blocked = [c for c in checks if c.status == "fail"]

    if as_json:
        payload = {
            "spectral_loom_version": __version__,
            "ok": not blocked,
            "checks": [c.model_dump() for c in checks],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        marks = {"ok": "ok  ", "info": "info", "warn": "warn", "fail": "FAIL"}
        width = max(len(c.name) for c in checks)
        print(f"spectral-loom {__version__}")
        for check in checks:
            print(f"  [{marks[check.status]}] {check.name.ljust(width)}  {check.detail}")
        print()
        if blocked:
            print(f"blocked by {len(blocked)} check(s): {', '.join(c.name for c in blocked)}")
        else:
            print("no blocking problems. 'info' lines are future work, not failures.")

    return EXIT_BLOCKED if blocked else EXIT_OK


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


class _ParseError(Exception):
    """A document that was read but could not be turned into data."""


def _parse(raw: str, path: Path) -> Any:
    """Parse a contract document.

    Specifications are hand-authored and may be YAML; timelines are machine-written
    JSON. YAML is a superset of JSON, so one loader covers both, but JSON files are
    parsed as JSON so their errors carry line and column numbers.
    """
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            return yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            return _raise_yaml(exc)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _ParseError(
            f"not valid JSON: line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc


def _raise_yaml(exc: yaml.YAMLError) -> Any:
    mark = getattr(exc, "problem_mark", None)
    where = f"line {mark.line + 1} column {mark.column + 1}: " if mark is not None else ""
    raise _ParseError(f"not valid YAML: {where}{getattr(exc, 'problem', exc)}") from exc


def _format_errors(error: ValidationError) -> list[str]:
    """Render pydantic errors so each names the offending field and its path."""
    lines: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "<document>"
        lines.append(f"  {location}: {item['msg']}")
    return lines


def validate(
    path: Path,
    model: type[SongSpec] | type[SongTimeline],
    label: str,
    as_json: bool,
) -> int:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _report_failure(
            as_json, EXIT_UNREADABLE, str(path), [f"cannot read {path}: {exc.strerror or exc}"]
        )

    try:
        document = _parse(raw, path)
    except _ParseError as exc:
        return _report_failure(as_json, EXIT_INVALID, str(path), [str(exc)])

    if not isinstance(document, dict):
        return _report_failure(
            as_json,
            EXIT_INVALID,
            str(path),
            [f"expected a mapping at the top level, found {type(document).__name__}"],
        )

    try:
        parsed = model.model_validate(document)
    except ValidationError as exc:
        return _report_failure(as_json, EXIT_INVALID, str(path), _format_errors(exc))

    summary = _summarize(parsed)
    if as_json:
        print(
            json.dumps(
                {"path": str(path), "valid": True, "summary": summary}, indent=2, sort_keys=True
            )
        )
    else:
        print(f"{path}: valid {label}")
        for key, value in summary.items():
            print(f"  {key}: {value}")
    return EXIT_OK


def _summarize(parsed: SongSpec | SongTimeline) -> dict[str, Any]:
    """A short, honest description of what was just validated."""
    if isinstance(parsed, SongSpec):
        return {
            "specimen_id": parsed.specimen_id,
            "generator": f"{parsed.generator.adapter} / {parsed.generator.model_id}",
            "revision": parsed.generator.revision or "UNPINNED — cannot be generated reproducibly",
            "requested_duration_s": parsed.requested_duration_s,
            "note": "every musical field here is requested, not observed",
        }
    return {
        "specimen_id": parsed.specimen_id,
        "schema": f"{parsed.schema_id} {parsed.schema_version}",
        "source_audio_duration_s": parsed.source_audio.duration_s,
        "time_unit": parsed.time_unit,
        "stages": [p.stage for p in parsed.provenance],
        "tracks": {t.id: len(t.events) for t in parsed.tracks},
    }


def _report_failure(as_json: bool, code: int, path: str, messages: list[str]) -> int:
    if as_json:
        print(
            json.dumps(
                {"path": path, "valid": False, "exit_code": code, "errors": messages},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"{path}: invalid", file=sys.stderr)
        for message in messages:
            print(message if message.startswith("  ") else f"  {message}", file=sys.stderr)
    return code


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spectral-loom",
        description=(
            "Infrastructure for the Spectral Loom music compiler. "
            "These commands inspect and validate; none of them downloads a model, "
            "generates audio, infers a timeline, or renders anything."
        ),
        epilog="exit codes: 0 ok, 1 blocked, 2 invalid document, 3 unreadable input",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"spectral-loom {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="report local prerequisites; changes nothing and downloads nothing"
    )
    doctor_parser.add_argument("--json", action="store_true", help="machine-readable output")

    spec_parser = subparsers.add_parser(
        "validate-spec", help="validate a song specification against the SongSpec contract"
    )
    spec_parser.add_argument("path", type=Path)
    spec_parser.add_argument("--json", action="store_true", help="machine-readable output")

    timeline_parser = subparsers.add_parser(
        "validate-timeline", help="validate a timeline against the SongTimeline contract"
    )
    timeline_parser.add_argument("path", type=Path)
    timeline_parser.add_argument("--json", action="store_true", help="machine-readable output")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "doctor":
        return doctor(as_json=args.json)
    if args.command == "validate-spec":
        return validate(args.path, SongSpec, "song specification", as_json=args.json)
    if args.command == "validate-timeline":
        return validate(args.path, SongTimeline, "song timeline", as_json=args.json)

    raise AssertionError(f"unreachable: unhandled command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
