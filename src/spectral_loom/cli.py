"""The ``spectral-loom`` command line.

Four commands. Three of them inspect and validate; one of them runs a model::

    spectral-loom doctor [--json] [--verify]
    spectral-loom validate-spec PATH [--json]
    spectral-loom validate-timeline PATH [--json]
    spectral-loom generate PATH [--json] [--force]

``generate`` is the only one that is expensive, and it is the only one that
needs the cabinet environment. It never downloads: weights are a precondition a
human establishes with ``scripts/bootstrap_cabinet.py``, and generation that
quietly fetches eleven gigabytes is not a pipeline stage, it is a surprise.

Nothing here infers a timeline or renders anything. Those are later gates.

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
from spectral_loom.cabinet import (
    CABINET_FILENAME,
    AssetStatus,
    CabinetError,
    check_asset,
    check_code,
    environment_site_packages,
    find_repository_root,
    installed_versions,
    load_repository_cabinet,
)
from spectral_loom.contracts import GenerationManifest, SongSpec, SongTimeline
from spectral_loom.generate import GenerationError, plan
from spectral_loom.generate import generate as run_generation

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INVALID = 2
EXIT_UNREADABLE = 3

#: Model packages that must NOT be in the default environment. `doctor` reports
#: their absence as the healthy state, because `archaeology/decisions/0005` puts
#: the cabinet in its own environment and a torch that leaked into `.venv` means
#: something installed it there by accident.
CABINET_PACKAGES_KEPT_OUT: tuple[str, ...] = ("torch", "diffusers", "demucs", "basic_pitch")


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


def collect_checks(root: Path | None = None, *, verify: bool = False) -> list[Check]:
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

    leaked = [p for p in CABINET_PACKAGES_KEPT_OUT if importlib.util.find_spec(p) is not None]
    checks.append(
        Check(
            name="default-env",
            status="ok" if not leaked else "warn",
            detail=(
                "light: no cabinet package in the default environment, as intended"
                if not leaked
                else f"{', '.join(leaked)} importable here; the cabinet belongs in its own "
                "environment (decision 5)"
            ),
        )
    )

    checks.extend(collect_cabinet_checks(repo, verify=verify))
    return checks


# ---------------------------------------------------------------------------
# doctor: the model cabinet
# ---------------------------------------------------------------------------


def collect_cabinet_checks(repo: Path, *, verify: bool = False) -> list[Check]:
    """Report the cabinet without stocking it.

    Three questions that are easy to conflate and are answered separately here:
    is this entry *pinned*, is its *implementation installed*, and are its
    *weights on disk*. A cabinet can be fully pinned and entirely empty, which is
    the state of a fresh clone and is not a problem with the clone.

    Nothing in here downloads, writes, or imports a model. `doctor` observes.
    """
    checks: list[Check] = []
    try:
        cabinet = load_repository_cabinet(repo)
    except CabinetError as exc:
        return [
            Check(
                name="cabinet",
                status="fail",
                detail=f"{exc}",
            )
        ]

    checks.append(
        Check(
            name="cabinet",
            status="ok",
            detail=(
                f"{repo / CABINET_FILENAME}: {len(cabinet.entry)} entries pinned "
                f"({', '.join(sorted(cabinet.entry))})"
            ),
        )
    )

    site_packages = environment_site_packages(repo, cabinet)
    installed = installed_versions(site_packages)
    environment_path = repo / cabinet.runtime.environment_path
    checks.append(
        Check(
            name="cabinet-env",
            status="ok" if installed else "info",
            detail=(
                f"{environment_path}: {len(installed)} distributions"
                if installed
                else (
                    f"{environment_path} not built — "
                    f"`uv run scripts/bootstrap_cabinet.py env` creates it from the lockfile"
                )
            ),
        )
    )

    for name, entry in sorted(cabinet.entry.items()):
        code = check_code(cabinet, installed, entry)
        if not code.present:
            status, detail = (
                "info",
                (f"{code.distribution}=={code.pinned_version} pinned, not installed"),
            )
        elif code.matches:
            status, detail = (
                "ok",
                (f"{code.distribution}=={code.installed_version} installed as pinned"),
            )
        else:
            status, detail = (
                "fail",
                (
                    f"{code.distribution}=={code.installed_version} installed, but "
                    f"{code.pinned_version} is pinned; the environment does not match the manifest"
                ),
            )
        checks.append(Check(name=f"cabinet-code:{name}", status=status, detail=detail))

        if not entry.assets:
            bundled = entry.code.bundled_weights
            checks.append(
                Check(
                    name=f"cabinet-assets:{name}",
                    status="ok",
                    detail=(
                        f"none to fetch — weights ship inside {entry.code.distribution} at "
                        f"{bundled}"
                        if bundled
                        else "none to fetch"
                    ),
                )
            )
            continue

        for asset in entry.assets:
            report = check_asset(repo, name, asset, verify_hashes=verify)
            status = {
                AssetStatus.VERIFIED: "ok",
                AssetStatus.PRESENT: "ok",
                AssetStatus.ABSENT: "info",
                AssetStatus.INCOMPLETE: "warn",
                AssetStatus.CORRUPT: "fail",
            }[report.status]
            checks.append(
                Check(
                    name=f"cabinet-assets:{name}",
                    status=status,
                    detail=(
                        f"{asset.repo_id}@{asset.revision[:12]} [{asset.license}] "
                        f"{report.status}: {report.summary()}"
                    ),
                )
            )

    checks.append(
        Check(
            name="accelerator",
            status="info",
            detail=(
                f"manifest records '{cabinet.runtime.accelerator}' with torch "
                f"{cabinet.runtime.torch}; not measured here — `doctor` does not import torch"
            ),
        )
    )
    return checks


def doctor(as_json: bool, root: Path | None = None, *, verify: bool = False) -> int:
    checks = collect_checks(root, verify=verify)
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
        print(f"{path}: {'blocked' if code == EXIT_BLOCKED else 'invalid'}", file=sys.stderr)
        for message in messages:
            print(message if message.startswith("  ") else f"  {message}", file=sys.stderr)
    return code


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def generate_command(path: Path, *, as_json: bool, force: bool) -> int:
    """Generate one specimen from one specification, and stop.

    Stopping is the feature. Gate 2 of `docs/roadmap.md` is passed by a human
    listening to the result, so this prints the file and how to hear it and does
    not go on to separate it, analyse it, or decide it is any good.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return _report_failure(
            as_json, EXIT_UNREADABLE, str(path), [f"cannot read {path}: {exc.strerror or exc}"]
        )

    try:
        document = _parse(raw.decode("utf-8"), path)
    except (_ParseError, UnicodeDecodeError) as exc:
        return _report_failure(as_json, EXIT_INVALID, str(path), [str(exc)])
    if not isinstance(document, dict):
        return _report_failure(
            as_json,
            EXIT_INVALID,
            str(path),
            [f"expected a mapping at the top level, found {type(document).__name__}"],
        )
    try:
        spec = SongSpec.model_validate(document)
    except ValidationError as exc:
        return _report_failure(as_json, EXIT_INVALID, str(path), _format_errors(exc))

    # Anchored on the manifest rather than on `.git`, because everything this
    # command needs — the cabinet, the weights under `models/`, the output tree —
    # hangs off the manifest. `doctor` anchors on `.git` because it reports on a
    # checkout; this reports on a cabinet.
    repo = find_repository_root(path.resolve().parent)
    try:
        cabinet = load_repository_cabinet(repo)
        prepared = plan(spec, path, raw, cabinet, repo)
    except (CabinetError, GenerationError) as exc:
        return _report_failure(as_json, EXIT_BLOCKED, str(path), [str(exc)])

    if not as_json:
        print(f"{path}: {prepared.specimen_id}")
        print(f"  generator   {prepared.tool}")
        print(f"  revision    {prepared.tool_revision}")
        print(f"  weights     {prepared.weights_dir}")
        print(f"  output      {prepared.output_dir}")
        print()

    try:
        manifest, produced = run_generation(prepared, force=force)
    except GenerationError as exc:
        return _report_failure(as_json, EXIT_BLOCKED, str(path), [str(exc)])

    if as_json:
        print(
            json.dumps(
                {
                    "path": str(path),
                    "generated": produced,
                    "audio": str(prepared.audio_path),
                    "manifest": str(prepared.manifest_path),
                    "observed": manifest.source_audio.model_dump(mode="json"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_OK

    _print_result(prepared.audio_path, prepared.manifest_path, manifest, produced=produced)
    return EXIT_OK


def _print_result(
    audio: Path, manifest_path: Path, manifest: GenerationManifest, *, produced: bool
) -> None:
    """Report the artifact, its observed properties, and how to hear it.

    Only observations appear here. The prompt asked for a tempo and a key and an
    exposed bass; whether any of that is in the file is a question for a human's
    ears and later for a timeline, and printing the request next to the
    measurements is how the two stop being distinguishable.
    """
    observed = manifest.source_audio
    stage = manifest.provenance[0]
    print("generated" if produced else "reused an existing specimen for an unchanged request")
    print(f"  audio       {audio}")
    print(f"  manifest    {manifest_path}")
    print("  observed:")
    print(f"    duration    {observed.duration_s:.2f} s")
    print(f"    sample rate {observed.sample_rate_hz} Hz")
    print(f"    channels    {observed.channels}")
    print(f"    sha256      {observed.hash}")
    print(f"  runtime     {stage.runtime}")
    if stage.duration_ms is not None:
        print(f"  took        {stage.duration_ms / 1000:.1f} s")
    print()
    print("Nothing has been inferred from this audio. Listen to it:")
    print(f"  afplay {audio}")
    print()
    print("Then decide: is the bass audible and exposed? is there silence between phrases?")
    print("are the parts separable by ear? is there vocal bleed or another generator failure?")


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
        "doctor", help="report local prerequisites and cabinet state; changes nothing"
    )
    doctor_parser.add_argument("--json", action="store_true", help="machine-readable output")
    doctor_parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "hash every pinned model file rather than checking its size. Slow — it reads the "
            "whole cabinet — and still downloads nothing."
        ),
    )

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

    generate_parser = subparsers.add_parser(
        "generate",
        help="generate one specimen from a specification using the pinned generator",
        description=(
            "Runs the pinned generator once and writes the audio and its manifest. Needs the "
            "cabinet environment and the weights already on disk; it never downloads. An "
            "unchanged request against an unchanged revision reuses the existing specimen."
        ),
    )
    generate_parser.add_argument("path", type=Path)
    generate_parser.add_argument("--json", action="store_true", help="machine-readable output")
    generate_parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate even when an existing specimen matches this exact request",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "doctor":
        return doctor(as_json=args.json, verify=args.verify)
    if args.command == "validate-spec":
        return validate(args.path, SongSpec, "song specification", as_json=args.json)
    if args.command == "validate-timeline":
        return validate(args.path, SongTimeline, "song timeline", as_json=args.json)
    if args.command == "generate":
        return generate_command(args.path, as_json=args.json, force=args.force)

    raise AssertionError(f"unreachable: unhandled command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
