#!/usr/bin/env python3
"""Establish the pinned model cabinet on this machine. Human-invoked, never automatic.

    uv run scripts/bootstrap_cabinet.py env       # build the pinned environment
    uv run scripts/bootstrap_cabinet.py assets    # fetch the pinned weights
    uv run scripts/bootstrap_cabinet.py status    # report, change nothing

Two subcommands rather than two scripts because the two halves are one act with
one manifest: ``model-cabinet.toml`` pins an implementation *and* the weights it
loads, and a machine with one of those and not the other cannot run anything.

Read `scripts/README.md` first. Every rule there is load-bearing here:

1. **Exact revisions.** Every identity comes from ``model-cabinet.toml``, whose
   contract rejects anything that is not forty hex digits. Nothing in this file
   names a branch, and there is no flag that lets you pass one.
2. **Idempotent.** The second run does nothing. Prove it rather than believe it:
   see ``--offline`` below.
3. **Verify before fetching.** Every pinned file is checked against the size and
   the sha256 upstream published *before* the hub client is imported, and an
   asset that verifies is skipped without a network call being made at all.
   Partial downloads are resumed by ``huggingface_hub``, not restarted.
4. **License and provenance recorded** in a tracked manifest — that manifest is
   ``model-cabinet.toml`` itself, which is why this script writes no tracked
   file. It leaves an untracked receipt beside the weights for `doctor`.
5. **No arbitrary remote model code.** ``trust_remote_code`` appears nowhere,
   and the cabinet pins only repositories that contain no ``.py`` at all.
6. **Ignored paths only.** Everything written lands under ``models/`` or the
   cabinet environment directory, both of which are in ``.gitignore``.
7. **Never invoked by a test or by CI.** The hermetic suite tests the decisions
   this script makes — in ``spectral_loom.cabinet`` — and never runs the script.

Exit codes match the CLI's: 0 ok, 1 blocked, 3 unreadable input.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:  # running from a checkout without an editable install
    sys.path.insert(0, str(_SRC))

from spectral_loom.cabinet import (  # noqa: E402
    Asset,
    AssetStatus,
    Cabinet,
    CabinetError,
    asset_directory,
    check_asset,
    find_repository_root,
    iter_assets,
    load_repository_cabinet,
    models_root,
    needs_fetch,
)

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_UNREADABLE = 3

#: Written beside the weights, untracked. Not the provenance record — that is
#: `model-cabinet.toml`, which is tracked. This is a local receipt saying when
#: this machine last proved these bytes were the pinned ones.
RECEIPT_NAME = ".spectral-loom-fetched.json"


def _say(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------------------
# env
# ---------------------------------------------------------------------------


def build_environment(root: Path, cabinet: Cabinet, *, dry_run: bool) -> int:
    """Materialize the cabinet extra into its own environment.

    Deliberately not `.venv`. Syncing eleven gigabytes of torch into the
    environment that also runs ruff and pytest means the next plain `uv sync`
    tears it out again, and the fast feedback loop should not be a casualty of
    stocking the cabinet. Both environments come from the same committed
    lockfile, so this adds a directory and not a second resolution.
    """
    runtime = cabinet.runtime
    target = root / runtime.environment_path
    command = [
        "uv",
        "sync",
        "--locked",
        "--extra",
        runtime.uv_extra,
        "--no-dev",
        "--project",
        str(root),
    ]
    _say(f"environment: {target}")
    _say(f"  extra '{runtime.uv_extra}' from the committed lockfile, python {runtime.python}")
    _say(f"  $ UV_PROJECT_ENVIRONMENT={runtime.environment_path} {' '.join(command)}")
    if dry_run:
        _say("  (dry run; nothing executed)")
        return EXIT_OK

    environment = dict(os.environ, UV_PROJECT_ENVIRONMENT=str(target))
    result = subprocess.run(command, env=environment, check=False)
    if result.returncode != 0:
        _say(f"  FAILED: uv exited {result.returncode}")
        return EXIT_BLOCKED
    _say("  ok")
    return EXIT_OK


# ---------------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------------


def _read_receipt(directory: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads((directory / RECEIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _write_receipt(directory: Path, entry_name: str, asset: Asset, *, seconds: float) -> None:
    receipt = {
        "entry": entry_name,
        "repo_id": asset.repo_id,
        "revision": asset.revision,
        "license": asset.license,
        "variant": asset.variant,
        "files": len(asset.files),
        "total_bytes": asset.total_bytes,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "verification": (
            "sha256 published by upstream, where upstream publishes one; size otherwise"
        ),
        "seconds": round(seconds, 1),
        "note": (
            "Local receipt, untracked and not authoritative. The provenance record "
            "is model-cabinet.toml, which is tracked."
        ),
    }
    (directory / RECEIPT_NAME).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _fetch(directory: Path, asset: Asset) -> None:
    """Download exactly the pinned files at exactly the pinned revision.

    Imported here rather than at module scope on purpose: `status` must work in
    the default environment, where `huggingface_hub` is not installed, and a
    bootstrap that cannot report what is missing until you have installed the
    thing that fetches it is not much of a bootstrap.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - depends on the cabinet env
        raise CabinetError(
            "huggingface_hub is not importable. Fetching weights needs the cabinet "
            "environment: run `uv run scripts/bootstrap_cabinet.py env` first, then "
            "re-run this from it, e.g. "
            "`.venv-cabinet/bin/python scripts/bootstrap_cabinet.py assets`."
        ) from exc

    snapshot_download(
        repo_id=asset.repo_id,
        revision=asset.revision,
        local_dir=str(directory),
        allow_patterns=[f.path for f in asset.files],
        # Every pinned repository is weights and JSON. Nothing here executes
        # remote code, and this script has no way to ask for a repository that
        # would: see scripts/README.md rule 5.
    )


def fetch_assets(root: Path, cabinet: Cabinet, *, offline: bool, dry_run: bool) -> int:
    """Fetch what is missing, verify what is there, and skip what verifies."""
    assets = list(iter_assets(cabinet))
    if not assets:
        _say("no cabinet entry has downloadable assets")
        return EXIT_OK

    _say(f"models root: {models_root(root)}")
    blocked = False

    for entry_name, entry, asset in assets:
        directory = asset_directory(root, entry_name, asset)
        _say("")
        _say(f"{entry_name}: {asset.repo_id}@{asset.revision[:12]} ({entry.purpose})")
        _say(f"  license {asset.license}, variant {asset.variant}, {asset.total_bytes:,} bytes")
        if asset.excluded:
            _say(f"  deliberately not fetched: {', '.join(asset.excluded)}")

        started = time.monotonic()
        report = check_asset(root, entry_name, asset, verify_hashes=True)
        _say(f"  verify before fetch: {report.status} — {report.summary()}")

        if not needs_fetch(report):
            _say(f"  skipped, nothing downloaded ({time.monotonic() - started:.1f}s to verify)")
            if _read_receipt(directory) is None and not dry_run:
                _write_receipt(directory, entry_name, asset, seconds=time.monotonic() - started)
            continue

        if report.status is AssetStatus.CORRUPT:
            # Not deleted automatically. A file that is the wrong bytes is
            # evidence about something, and this script does not get to destroy
            # it on a machine it does not own.
            for bad in report.bad:
                _say(f"  MISMATCH {bad.path}: {bad.problem}")
            _say("  refusing to fetch over files that do not match what is pinned.")
            _say(f"  inspect them, then remove {directory} and run this again.")
            blocked = True
            continue

        if offline:
            _say("  --offline: would need to download, and was told not to.")
            blocked = True
            continue

        if dry_run:
            _say(f"  (dry run; would fetch {len(report.missing)} file(s) into {directory})")
            continue

        _say(f"  fetching {len(report.missing)} of {len(asset.files)} file(s) into {directory}")
        directory.mkdir(parents=True, exist_ok=True)
        try:
            _fetch(directory, asset)
        except CabinetError as exc:
            _say(f"  FAILED: {exc}")
            return EXIT_BLOCKED
        except Exception as exc:  # a partial download is resumable, not fatal
            _say(f"  FAILED: {type(exc).__name__}: {exc}")
            _say("  a partial download is left in place and will be resumed by the next run.")
            blocked = True
            continue

        after = check_asset(root, entry_name, asset, verify_hashes=True)
        _say(f"  after fetch: {after.status} — {after.summary()}")
        if after.status is not AssetStatus.VERIFIED:
            for bad in after.bad:
                _say(f"  MISMATCH {bad.path}: {bad.problem}")
            blocked = True
            continue
        _write_receipt(directory, entry_name, asset, seconds=time.monotonic() - started)
        _say(f"  done in {time.monotonic() - started:.1f}s")

    return EXIT_BLOCKED if blocked else EXIT_OK


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def status(root: Path, cabinet: Cabinet, *, verify: bool, as_json: bool) -> int:
    reports = [
        check_asset(root, name, asset, verify_hashes=verify)
        for name, _entry, asset in iter_assets(cabinet)
    ]
    if as_json:
        print(
            json.dumps(
                {
                    "repository": str(root),
                    "hashes_checked": verify,
                    "assets": [r.model_dump(exclude={"files"}) for r in reports],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for report in reports:
            _say(f"{report.entry:12s} {report.status:11s} {report.summary()}")
            _say(f"             {report.directory}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap_cabinet.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root; defaults to the nearest ancestor holding model-cabinet.toml",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    environment = subparsers.add_parser("env", help="build the pinned cabinet environment")
    environment.add_argument(
        "--dry-run", action="store_true", help="print the command, run nothing"
    )

    assets = subparsers.add_parser("assets", help="fetch and verify the pinned weights")
    assets.add_argument("--dry-run", action="store_true", help="report what would be fetched")
    assets.add_argument(
        "--offline",
        action="store_true",
        help=(
            "verify only, and fail rather than download. This is the idempotency proof: "
            "after a successful run, `--offline` must succeed and report every asset skipped."
        ),
    )

    reported = subparsers.add_parser("status", help="report what is on disk; change nothing")
    reported.add_argument(
        "--verify", action="store_true", help="hash every pinned file rather than checking sizes"
    )
    reported.add_argument("--json", action="store_true", help="machine-readable output")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root or find_repository_root(Path.cwd())

    try:
        cabinet = load_repository_cabinet(root)
    except CabinetError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    if args.command == "env":
        return build_environment(root, cabinet, dry_run=args.dry_run)
    if args.command == "assets":
        return fetch_assets(root, cabinet, offline=args.offline, dry_run=args.dry_run)
    if args.command == "status":
        return status(root, cabinet, verify=args.verify, as_json=args.json)

    raise AssertionError(f"unreachable: unhandled command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
