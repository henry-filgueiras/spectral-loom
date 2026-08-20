#!/usr/bin/env python3
"""Ask whether every pinned cabinet artifact is still resolvable upstream.

    uv run scripts/check_cabinet_remote.py [--json] [--timeout SECONDS]

**A pin establishes identity, not availability.** `model-cabinet.toml` says
exactly which bytes this project means by "Demucs"; it cannot make anyone keep
serving them. The failure this exists to catch is the quiet one: a repository
goes private, a version is deleted from an index, and nothing in the repository
notices until somebody clones it fresh and watches `bootstrap assets` fail
eleven gigabytes into a task they were trying to start.

So this is deliberately, explicitly networked, and it is the only script here
that is. It reads **metadata only**: no weight is downloaded, no model is loaded,
nothing on disk is touched, and the hermetic suite never runs it. See
`archaeology/decisions/0007` for why that separation is enforced rather than
merely intended.

The honesty rule that shapes the output is that **a provider's silence is not a
death certificate**. Measured against the real hosts while this was written:

- Hugging Face answers a request for a repository that does not exist with
  ``401 Invalid username or password`` — the same answer it gives for a private
  repository you cannot see. It is refusing to distinguish "gone" from "not
  yours", so this script refuses to as well, and reports
  ``authentication-required`` rather than guessing.
- A bad *revision* of a repository that does exist answers ``404``, which is a
  genuinely different fact and gets a genuinely different verdict.
- PyPI answers ``404`` for both an unknown distribution and an unknown version
  of a known one, so the two are separated by asking twice.

Nothing here repairs anything. Choosing a replacement for an artifact that has
become unavailable is an explicit future experiment with its own evidence, not
something a monitor gets to do at three in the morning.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from spectral_loom.cabinet import (  # noqa: E402
    Asset,
    Cabinet,
    CabinetError,
    Entry,
    find_repository_root,
    load_repository_cabinet,
)

#: Exit codes, documented because a scheduled job's exit code is its whole
#: interface. `2` exists so that "we could not check" never masquerades as
#: "everything is fine" and never masquerades as "something is gone" either.
EXIT_OK = 0
EXIT_UNAVAILABLE = 1
EXIT_UNCONFIRMED = 2
EXIT_UNREADABLE = 3

DEFAULT_TIMEOUT = 20.0

PYPI_API = "https://pypi.org/pypi"
HUGGINGFACE_API = "https://huggingface.co/api/models"

USER_AGENT = "spectral-loom-cabinet-sentinel (+https://github.com/henry-filgueiras/spectral-loom)"


class Availability(StrEnum):
    """What was established about one pinned artifact.

    Seven values rather than a boolean, because they call for different
    responses and because collapsing them would require asserting things the
    providers did not say.
    """

    #: Everything pinned was found, and its published metadata still agrees.
    AVAILABLE = "available"
    #: The repository or distribution answered, and the pinned revision or
    #: version did not.
    REVISION_UNRESOLVABLE = "revision-unresolvable"
    #: The revision resolved, and files this project pins are not in it.
    PATHS_MISSING = "paths-missing"
    #: Everything is present and the published size or digest has changed.
    METADATA_MISMATCH = "metadata-mismatch"
    #: The provider demanded credentials. It has NOT said the artifact is gone;
    #: on Hugging Face this is also the answer for a repository that does not
    #: exist, and the two are not distinguishable from outside.
    AUTHENTICATION_REQUIRED = "authentication-required"
    #: The provider or the network failed in a way that says nothing about the
    #: artifact. Retry; do not act.
    TRANSIENT = "transient"
    #: An answer this script does not know how to read. Recorded rather than
    #: forced into one of the above.
    UNKNOWN = "unknown"


#: Which verdicts mean "this artifact is not resolvable" as opposed to "this
#: check did not reach a conclusion". The difference is the exit code.
CONCLUSIVE_FAILURES = frozenset(
    {
        Availability.REVISION_UNRESOLVABLE,
        Availability.PATHS_MISSING,
        Availability.METADATA_MISMATCH,
    }
)
INCONCLUSIVE = frozenset(
    {
        Availability.AUTHENTICATION_REQUIRED,
        Availability.TRANSIENT,
        Availability.UNKNOWN,
    }
)


@dataclass(frozen=True)
class Probe:
    """One HTTP response, recorded before anything interprets it.

    Separated from the verdict on purpose: the classification is then a pure
    function of a recorded answer, which is what lets the hermetic suite test
    the part that is easy to get wrong without going near a socket.
    """

    url: str
    status: int | None = None
    body: bytes | None = None
    error: str | None = None

    @property
    def reached(self) -> bool:
        return self.status is not None

    def json(self) -> Any:
        if self.body is None:
            return None
        try:
            return json.loads(self.body)
        except json.JSONDecodeError:
            return None


@dataclass
class Finding:
    """What was established about one pinned artifact, and on what evidence."""

    entry: str
    kind: str  # "code" | "assets"
    identity: str
    availability: Availability
    summary: str
    details: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.availability is Availability.AVAILABLE

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry,
            "kind": self.kind,
            "identity": self.identity,
            "availability": str(self.availability),
            "summary": self.summary,
            "details": self.details,
            "urls_checked": self.checked,
        }


# ---------------------------------------------------------------------------
# The one impure function.
# ---------------------------------------------------------------------------


def fetch(url: str, timeout: float) -> Probe:
    """GET a URL and record what came back, without deciding what it means.

    Never raises. A refused connection, a DNS failure and a 503 are all facts
    about the attempt, and a monitor that crashed on them would tell nobody
    anything.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Probe(url=url, status=response.status, body=response.read())
    except urllib.error.HTTPError as exc:
        body = b""
        with contextlib.suppress(Exception):  # the body is a nicety; the status is the fact
            body = exc.read()
        return Probe(url=url, status=exc.code, body=body, error=str(exc.reason))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return Probe(url=url, error=f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Classification: pure, and where all the care is.
# ---------------------------------------------------------------------------


def _transport_finding(entry: str, kind: str, identity: str, probe: Probe) -> Finding | None:
    """The verdicts that depend only on whether an answer arrived at all."""
    if not probe.reached:
        return Finding(
            entry=entry,
            kind=kind,
            identity=identity,
            availability=Availability.TRANSIENT,
            summary="the provider could not be reached",
            details=[probe.error or "no response and no error, which should not happen"],
            checked=[probe.url],
        )
    assert probe.status is not None
    if probe.status in {401, 403}:
        return Finding(
            entry=entry,
            kind=kind,
            identity=identity,
            availability=Availability.AUTHENTICATION_REQUIRED,
            summary=f"the provider answered {probe.status} and demanded credentials",
            details=[
                "This is NOT a statement that the artifact is gone. Hugging Face returns 401 "
                "both for a repository that does not exist and for one you cannot see, so from "
                "outside the two are indistinguishable and this check will not guess.",
            ],
            checked=[probe.url],
        )
    if probe.status >= 500:
        return Finding(
            entry=entry,
            kind=kind,
            identity=identity,
            availability=Availability.TRANSIENT,
            summary=f"the provider answered {probe.status}",
            details=["A server-side failure says nothing about the artifact. Retry."],
            checked=[probe.url],
        )
    return None


def classify_pypi(
    entry_name: str, entry: Entry, version_probe: Probe, project_probe: Probe | None
) -> Finding:
    """Judge a pinned distribution from PyPI's answers.

    ``project_probe`` is only fetched when the version request 404s, because
    PyPI answers 404 for an unknown distribution and for an unknown version of a
    known one with the same status, and "this package is gone" and "this version
    was deleted" are different problems.
    """
    code = entry.code
    identity = f"{code.distribution}=={code.version}"

    transport = _transport_finding(entry_name, "code", identity, version_probe)
    if transport is not None:
        return transport

    assert version_probe.status is not None
    if version_probe.status == 404:
        known = project_probe is not None and project_probe.status == 200
        return Finding(
            entry=entry_name,
            kind="code",
            identity=identity,
            availability=Availability.REVISION_UNRESOLVABLE,
            summary=(
                f"{code.distribution} is on the index and {code.version} is not"
                if known
                else f"the index has no record of {code.distribution} at all"
            ),
            details=[
                "PyPI answered 404. It does not distinguish deleted from never-published, so "
                "this reports what could not be resolved rather than what happened to it."
            ],
            checked=[version_probe.url] + ([project_probe.url] if project_probe else []),
        )
    if version_probe.status != 200:
        return Finding(
            entry=entry_name,
            kind="code",
            identity=identity,
            availability=Availability.UNKNOWN,
            summary=f"the index answered {version_probe.status}, which this check cannot read",
            details=[version_probe.error or ""],
            checked=[version_probe.url],
        )

    document = version_probe.json()
    if not isinstance(document, dict):
        return Finding(
            entry=entry_name,
            kind="code",
            identity=identity,
            availability=Availability.UNKNOWN,
            summary="the index answered 200 with something that is not a JSON object",
            checked=[version_probe.url],
        )

    files = {
        str(url.get("filename")): url for url in document.get("urls", []) if isinstance(url, dict)
    }
    artifact = files.get(code.artifact)
    if artifact is None:
        return Finding(
            entry=entry_name,
            kind="code",
            identity=identity,
            availability=Availability.PATHS_MISSING,
            summary=f"{code.artifact} is not among the files published for this version",
            details=[f"published: {', '.join(sorted(files)) or 'nothing'}"],
            checked=[version_probe.url],
        )

    problems: list[str] = []
    published = str(artifact.get("digests", {}).get("sha256", ""))
    if published != code.sha256:
        problems.append(
            f"{code.artifact}: index publishes sha256 {published or 'nothing'}, "
            f"the cabinet pins {code.sha256}"
        )
    if artifact.get("yanked"):
        problems.append(
            f"{code.artifact} is yanked: {artifact.get('yanked_reason') or 'no reason given'}. "
            f"It still installs when pinned exactly, which is how this project installs it."
        )

    if any("sha256" in problem for problem in problems):
        return Finding(
            entry=entry_name,
            kind="code",
            identity=identity,
            availability=Availability.METADATA_MISMATCH,
            summary="the published digest is not the one the cabinet pins",
            details=problems,
            checked=[version_probe.url],
        )
    return Finding(
        entry=entry_name,
        kind="code",
        identity=identity,
        availability=Availability.AVAILABLE,
        summary=f"{code.artifact} present, sha256 unchanged",
        details=problems,
        checked=[version_probe.url],
    )


def classify_huggingface(
    entry_name: str, asset: Asset, revision_probe: Probe, repo_probe: Probe | None
) -> Finding:
    """Judge a pinned weights revision from Hugging Face's answers.

    ``repo_probe`` is only fetched when the revision request 404s, which is the
    one case where the hub does distinguish: a bad revision of a repository that
    exists answers 404, while the repository itself answering 401 means the hub
    is declining to say whether it exists.
    """
    identity = f"{asset.repo_id}@{asset.revision}"

    transport = _transport_finding(entry_name, "assets", identity, revision_probe)
    if transport is not None:
        return transport

    assert revision_probe.status is not None
    if revision_probe.status == 404:
        reachable = repo_probe is not None and repo_probe.status == 200
        return Finding(
            entry=entry_name,
            kind="assets",
            identity=identity,
            availability=Availability.REVISION_UNRESOLVABLE,
            summary=(
                f"{asset.repo_id} resolves and revision {asset.revision[:12]} does not"
                if reachable
                else f"neither {asset.repo_id} nor revision {asset.revision[:12]} resolves"
            ),
            details=[
                "The hub answered 404 for the pinned revision. A revision is immutable, so this "
                "means history was rewritten or the repository is no longer the one that was "
                "pinned. Nothing here establishes which."
            ],
            checked=[revision_probe.url] + ([repo_probe.url] if repo_probe else []),
        )
    if revision_probe.status != 200:
        return Finding(
            entry=entry_name,
            kind="assets",
            identity=identity,
            availability=Availability.UNKNOWN,
            summary=f"the hub answered {revision_probe.status}, which this check cannot read",
            details=[revision_probe.error or ""],
            checked=[revision_probe.url],
        )

    document = revision_probe.json()
    if not isinstance(document, dict):
        return Finding(
            entry=entry_name,
            kind="assets",
            identity=identity,
            availability=Availability.UNKNOWN,
            summary="the hub answered 200 with something that is not a JSON object",
            checked=[revision_probe.url],
        )

    details: list[str] = []
    if document.get("gated"):
        details.append(
            f"the repository is now gated ({document['gated']}); a fresh bootstrap will need "
            f"accepted terms and a token even though the revision still resolves"
        )
    resolved = str(document.get("sha", ""))
    if resolved and resolved != asset.revision:
        details.append(f"the hub resolved this request to {resolved}, not {asset.revision}")

    siblings = {
        str(item.get("rfilename")): item
        for item in document.get("siblings", [])
        if isinstance(item, dict)
    }

    missing = [pinned.path for pinned in asset.files if pinned.path not in siblings]
    if missing:
        return Finding(
            entry=entry_name,
            kind="assets",
            identity=identity,
            availability=Availability.PATHS_MISSING,
            summary=f"{len(missing)} pinned file(s) are not present at this revision",
            details=[*details, f"missing: {', '.join(sorted(missing))}"],
            checked=[revision_probe.url],
        )

    mismatches: list[str] = []
    for pinned in asset.files:
        published = siblings[pinned.path]
        size = published.get("size")
        if isinstance(size, int) and size != pinned.size:
            mismatches.append(
                f"{pinned.path}: hub publishes {size} bytes, the cabinet pins {pinned.size}"
            )
        lfs = published.get("lfs")
        if pinned.sha256 and isinstance(lfs, dict):
            digest = str(lfs.get("sha256", ""))
            if digest and digest != pinned.sha256:
                mismatches.append(
                    f"{pinned.path}: hub publishes sha256 {digest}, "
                    f"the cabinet pins {pinned.sha256}"
                )

    if mismatches:
        return Finding(
            entry=entry_name,
            kind="assets",
            identity=identity,
            availability=Availability.METADATA_MISMATCH,
            summary="published metadata no longer matches what the cabinet pins",
            details=[*details, *mismatches],
            checked=[revision_probe.url],
        )

    hashed = sum(1 for pinned in asset.files if pinned.sha256)
    return Finding(
        entry=entry_name,
        kind="assets",
        identity=identity,
        availability=Availability.AVAILABLE,
        summary=(
            f"{len(asset.files)} pinned file(s) present at the pinned revision; "
            f"{hashed} verified against the published sha256, the rest by size"
        ),
        details=details,
        checked=[revision_probe.url],
    )


# ---------------------------------------------------------------------------
# Driving the checks.
# ---------------------------------------------------------------------------


def check_code(entry_name: str, entry: Entry, timeout: float) -> Finding:
    version_url = f"{PYPI_API}/{entry.code.distribution}/{entry.code.version}/json"
    probe = fetch(version_url, timeout)
    project: Probe | None = None
    if probe.status == 404:
        project = fetch(f"{PYPI_API}/{entry.code.distribution}/json", timeout)
    return classify_pypi(entry_name, entry, probe, project)


def check_asset(entry_name: str, asset: Asset, timeout: float) -> Finding:
    revision_url = f"{HUGGINGFACE_API}/{asset.repo_id}/revision/{asset.revision}?blobs=true"
    probe = fetch(revision_url, timeout)
    repository: Probe | None = None
    if probe.status == 404:
        repository = fetch(f"{HUGGINGFACE_API}/{asset.repo_id}", timeout)
    return classify_huggingface(entry_name, asset, probe, repository)


def check_cabinet(cabinet: Cabinet, timeout: float) -> list[Finding]:
    findings: list[Finding] = []
    for name, entry in sorted(cabinet.entry.items()):
        if entry.code.kind == "pypi":
            findings.append(check_code(name, entry, timeout))
        for asset in entry.assets:
            findings.append(check_asset(name, asset, timeout))
    return findings


def exit_code(findings: list[Finding]) -> int:
    """0 when every pin resolved, 1 when one demonstrably did not, 2 when unsure.

    The third value is the point. A monitor that returned "fine" because it
    could not reach the network would be worse than no monitor, and one that
    returned "gone" for the same reason would be worse still.
    """
    if any(f.availability in CONCLUSIVE_FAILURES for f in findings):
        return EXIT_UNAVAILABLE
    if any(f.availability in INCONCLUSIVE for f in findings):
        return EXIT_UNCONFIRMED
    return EXIT_OK


def report(findings: list[Finding], code: int) -> None:
    marks = {
        Availability.AVAILABLE: "ok  ",
        Availability.REVISION_UNRESOLVABLE: "GONE",
        Availability.PATHS_MISSING: "GONE",
        Availability.METADATA_MISMATCH: "DIFF",
        Availability.AUTHENTICATION_REQUIRED: "auth",
        Availability.TRANSIENT: "????",
        Availability.UNKNOWN: "????",
    }
    print("cabinet remote availability — metadata only, no weights downloaded")
    print()
    for finding in findings:
        print(f"  [{marks[finding.availability]}] {finding.entry}/{finding.kind}")
        print(f"         {finding.identity}")
        print(f"         {finding.availability}: {finding.summary}")
        for detail in finding.details:
            if detail:
                print(f"         - {detail}")
    print()
    if code == EXIT_OK:
        print("every pinned artifact still resolves.")
    elif code == EXIT_UNAVAILABLE:
        bad = [f for f in findings if f.availability in CONCLUSIVE_FAILURES]
        print(f"{len(bad)} pinned artifact(s) could not be resolved:")
        for finding in bad:
            print(f"  {finding.entry}/{finding.kind}: {finding.identity} — {finding.summary}")
        print()
        print(
            "The cabinet is NOT updated automatically and this script does not repair anything. "
            "Choosing a replacement is a decision with its own evidence."
        )
    else:
        unsure = [f for f in findings if f.availability in INCONCLUSIVE]
        print(f"{len(unsure)} pinned artifact(s) could not be confirmed either way:")
        for finding in unsure:
            print(f"  {finding.entry}/{finding.kind}: {finding.identity} — {finding.summary}")
        print()
        print("Nothing here says an artifact is gone. Retry before concluding anything.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_cabinet_remote.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "exit codes: 0 every pin resolved, 1 a pin demonstrably did not, "
            "2 a pin could not be confirmed either way, 3 the cabinet is unreadable"
        ),
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)

    root = args.root or find_repository_root(Path.cwd())
    try:
        cabinet = load_repository_cabinet(root)
    except CabinetError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNREADABLE

    findings = check_cabinet(cabinet, args.timeout)
    code = exit_code(findings)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": code == EXIT_OK,
                    "exit_code": code,
                    "downloaded_weights": False,
                    "findings": [f.as_dict() for f in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        report(findings, code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
