"""The ``spectral-loom`` command line.

Four commands. Three of them inspect and validate; one of them runs a model::

    spectral-loom doctor [--json] [--verify]
    spectral-loom validate-spec PATH [--json]
    spectral-loom validate-timeline PATH [--json]
    spectral-loom generate PATH [--json] [--force]
    spectral-loom accept SPECIMEN --reviewer NAME --reviewed-on DATE ...

``generate`` is expensive and needs the cabinet environment. It never downloads:
weights are a precondition a human establishes with
``scripts/bootstrap_cabinet.py``, and generation that quietly fetches eleven
gigabytes is not a pipeline stage, it is a surprise.

``accept`` is the opposite kind of command: it runs no model and produces no
audio. It writes down what a person decided after listening, bound to the exact
bytes they heard, because that judgement is the only part of gate 2 that a
program cannot supply and the only part that has to survive a clean clone.

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
from datetime import date
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
from spectral_loom.contracts import (
    CriterionResponse,
    GenerationManifest,
    SongSpec,
    SongTimeline,
)
from spectral_loom.generate import (
    AUDIO_FILENAME,
    GENERATED_DIRNAME,
    MANIFEST_FILENAME,
    GenerationError,
    load_manifest,
    plan,
)
from spectral_loom.generate import generate as run_generation
from spectral_loom.hashing import hash_file
from spectral_loom.review import (
    GATE_2_CRITERIA,
    ReviewError,
    build_review,
    review_path,
    write_review,
)

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
# accept
# ---------------------------------------------------------------------------


def _criterion_dest(identifier: str) -> str:
    """argparse destination for a criterion's flag."""
    return identifier.replace("-", "_")


def accept_command(
    specimen_id: str,
    *,
    reviewer: str,
    reviewed_on: date,
    responses: dict[str, CriterionResponse],
    notes: dict[str, str],
    summary: str | None,
    accepted: bool,
    force: bool,
    as_json: bool,
    root: Path | None = None,
) -> int:
    """Write down what a human decided about one exact rendering.

    The command's job is the binding, not the judgement. It finds the audio and
    its manifest, **re-hashes the audio** rather than believing the manifest,
    refuses if the two disagree, and then attaches the person's answers to the
    hash it actually measured. A review that named a file instead of bytes would
    be worth nothing the moment the file was regenerated.
    """
    repo = find_repository_root(root or Path.cwd())
    directory = repo / GENERATED_DIRNAME / specimen_id
    audio_path = directory / AUDIO_FILENAME
    manifest_path = directory / MANIFEST_FILENAME

    if not audio_path.is_file():
        return _report_failure(
            as_json,
            EXIT_BLOCKED,
            specimen_id,
            [
                f"no generated audio at {audio_path}. Nothing can be reviewed that is not on "
                f"this machine; generate the specimen first."
            ],
        )
    if not manifest_path.is_file():
        return _report_failure(
            as_json,
            EXIT_BLOCKED,
            specimen_id,
            [
                f"no generation manifest at {manifest_path}. The audio cannot be attributed "
                f"to a specification or a revision, so accepting it would record a judgement "
                f"about bytes of unknown origin."
            ],
        )

    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = load_manifest(manifest_path)
        cabinet_bytes = (repo / CABINET_FILENAME).read_bytes()
    except (OSError, GenerationError, ValidationError) as exc:
        return _report_failure(as_json, EXIT_UNREADABLE, specimen_id, [str(exc)])

    observed = hash_file(audio_path)
    if observed != manifest.source_audio.hash:
        return _report_failure(
            as_json,
            EXIT_BLOCKED,
            specimen_id,
            [
                f"{audio_path} hashes to {observed}, but {manifest_path.name} describes "
                f"{manifest.source_audio.hash}. The manifest is a claim about a file that has "
                f"since changed; regenerate before reviewing, because a review must be about "
                f"bytes its own record can attribute."
            ],
        )

    try:
        review = build_review(
            manifest,
            manifest_bytes=manifest_bytes,
            cabinet_bytes=cabinet_bytes,
            reviewer=reviewer,
            reviewed_on=reviewed_on,
            responses=responses,
            notes=notes,
            accepted=accepted,
            summary=summary,
        )
    except (ReviewError, ValidationError) as exc:
        return _report_failure(as_json, EXIT_INVALID, specimen_id, [str(exc)])

    target = review_path(repo, specimen_id, observed)
    if target.exists() and not force:
        return _report_failure(
            as_json,
            EXIT_BLOCKED,
            specimen_id,
            [
                f"{target} already records a review of exactly these bytes. Overwriting a "
                f"recorded human judgement is a deliberate act; pass --force if that is what "
                f"you mean."
            ],
        )
    write_review(target, review)

    if as_json:
        print(
            json.dumps(
                {
                    "specimen_id": specimen_id,
                    "accepted": accepted,
                    "review": str(target),
                    "source_audio": review.source_audio.model_dump(mode="json"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_OK

    print(f"{specimen_id}: {'accepted' if accepted else 'REJECTED'} by {reviewer} on {reviewed_on}")
    print(f"  audio       {audio_path}")
    print(f"  sha256      {observed}")
    print(
        f"  observed    {review.source_audio.duration_s:.2f} s, "
        f"{review.source_audio.sample_rate_hz} Hz, {review.source_audio.channels} ch"
    )
    print(f"  review      {target}")
    print()
    for item in review.review.criteria:
        print(f"  {item.response.value:<8} {item.id}")
        if item.notes:
            print(f"           {item.notes}")
    if review.review.notes:
        print(f"  {review.review.notes}")
        print()
    print(review.review.purpose if accepted else "Nothing downstream runs on a rejected specimen.")
    return EXIT_OK


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

    accept_parser = subparsers.add_parser(
        "accept",
        help="record a human's verdict on one generated specimen, bound to its exact hash",
        description=(
            "Writes a tracked review of the exact bytes on disk for one specimen. Runs no "
            "model and reads no audio beyond hashing it. Every gate 2 criterion must be "
            "answered: a review with a blank question is a partially examined assumption. "
            "Use --reject to record a rejection, which is history too."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    accept_parser.add_argument("specimen_id", help="specimen id, e.g. sparse-funk-exposed-bass")
    accept_parser.add_argument("--reviewer", required=True, help="who listened")
    accept_parser.add_argument(
        "--reviewed-on",
        required=True,
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="the day they listened",
    )
    for item in GATE_2_CRITERIA:
        accept_parser.add_argument(
            item.flag,
            required=True,
            dest=_criterion_dest(item.id),
            choices=[r.value for r in CriterionResponse],
            help=item.help,
        )
    accept_parser.add_argument(
        "--note",
        action="append",
        default=[],
        metavar="CRITERION=TEXT",
        help="qualify one criterion's answer; repeatable",
    )
    accept_parser.add_argument(
        "--summary", help="free prose; on a rejection, what was wrong with the candidate"
    )
    accept_parser.add_argument(
        "--reject",
        action="store_true",
        help="record a rejection rather than an acceptance",
    )
    accept_parser.add_argument(
        "--force", action="store_true", help="overwrite an existing review of these exact bytes"
    )
    accept_parser.add_argument("--json", action="store_true", help="machine-readable output")

    return parser


def parse_notes(entries: list[str]) -> dict[str, str]:
    """Split `--note criterion=text` pairs, refusing anything that is not one."""
    notes: dict[str, str] = {}
    for entry in entries:
        name, separator, text = entry.partition("=")
        if not separator or not name.strip() or not text.strip():
            raise ReviewError(f"--note must be CRITERION=TEXT, found {entry!r}")
        notes[name.strip()] = text.strip()
    return notes


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
    if args.command == "accept":
        try:
            notes = parse_notes(args.note)
        except ReviewError as exc:
            return _report_failure(args.json, EXIT_INVALID, args.specimen_id, [str(exc)])
        return accept_command(
            args.specimen_id,
            reviewer=args.reviewer,
            reviewed_on=args.reviewed_on,
            responses={
                item.id: CriterionResponse(getattr(args, _criterion_dest(item.id)))
                for item in GATE_2_CRITERIA
            },
            notes=notes,
            summary=args.summary,
            accepted=not args.reject,
            force=args.force,
            as_json=args.json,
        )

    raise AssertionError(f"unreachable: unhandled command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
