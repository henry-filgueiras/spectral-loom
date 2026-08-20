"""Tests for the cabinet availability sentinel's judgement.

The script is the only explicitly networked thing in this repository, and these
tests never let it near a socket: they hand recorded provider answers to the
classification functions and check what it concludes. `tests/netguard.py` is
still armed, so a refactor that made classification reach out would fail here
rather than in a scheduled job at three in the morning.

What is being defended is restraint. It is easy to write a monitor that says
"deleted" whenever it gets a 4xx, and that monitor will eventually wake somebody
up to mourn an artifact that was merely behind an auth wall. The responses below
are the real shapes, taken from PyPI and the Hugging Face hub while the script
was written — including the surprising one: **the hub answers a request for a
repository that does not exist with 401, exactly as it answers a request for a
private repository**, so from outside the two are indistinguishable and this
check is required not to guess.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from spectral_loom.cabinet import Cabinet, load_repository_cabinet

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_cabinet_remote.py"


def _load() -> ModuleType:
    """Import the script by path; `scripts/` is deliberately not a package.

    Registered in `sys.modules` before execution because `@dataclass` resolves
    a class's own module to interpret its annotations, and a module that is not
    in the table yet resolves to None.
    """
    spec = importlib.util.spec_from_file_location("check_cabinet_remote", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sentinel = _load()

# The script is loaded by path, so mypy cannot see inside it and these are
# values rather than types. Helpers below are annotated `Any` for that reason
# and not because their shape is unknown.
Availability = sentinel.Availability
Probe = sentinel.Probe

CABINET: Cabinet = load_repository_cabinet(REPO_ROOT)
DEMUCS = CABINET.entry["demucs"]
ASSET = DEMUCS.assets[0]

VERSION_URL = "https://pypi.org/pypi/demucs/4.1.0/json"
REVISION_URL = f"https://huggingface.co/api/models/{ASSET.repo_id}/revision/{ASSET.revision}"


def pypi_ok(**overrides: object) -> Any:
    """PyPI's real answer shape for a published version."""
    entry = {
        "filename": DEMUCS.code.artifact,
        "packagetype": "bdist_wheel",
        "size": 100567,
        "digests": {"sha256": DEMUCS.code.sha256},
        "yanked": False,
        **overrides,
    }
    body = json.dumps({"info": {}, "urls": [entry]}).encode()
    return Probe(url=VERSION_URL, status=200, body=body)


def hub_ok(**overrides: object) -> Any:
    """The hub's real answer shape for `?blobs=true` at a resolvable revision."""
    siblings = []
    for pinned in ASSET.files:
        sibling: dict[str, object] = {"rfilename": pinned.path, "size": pinned.size}
        if pinned.sha256:
            sibling["lfs"] = {"sha256": pinned.sha256, "size": pinned.size}
        siblings.append(sibling)
    document = {"sha": ASSET.revision, "gated": False, "private": False, "siblings": siblings}
    document.update(overrides)
    return Probe(url=REVISION_URL, status=200, body=json.dumps(document).encode())


# ---------------------------------------------------------------------------
# The happy answer.
# ---------------------------------------------------------------------------


def test_a_published_distribution_with_the_pinned_digest_is_available() -> None:
    finding = sentinel.classify_pypi("demucs", DEMUCS, pypi_ok(), None)
    assert finding.availability is Availability.AVAILABLE
    assert DEMUCS.code.artifact in finding.summary


def test_a_resolvable_revision_with_matching_metadata_is_available() -> None:
    finding = sentinel.classify_huggingface("demucs", ASSET, hub_ok(), None)
    assert finding.availability is Availability.AVAILABLE
    assert "verified against the published sha256" in finding.summary


# ---------------------------------------------------------------------------
# Restraint: what the provider did not say.
# ---------------------------------------------------------------------------


def test_a_401_is_reported_as_authentication_and_never_as_deletion() -> None:
    """The finding this whole file exists for.

    The hub answers 401 both for a repository that does not exist and for one
    the caller cannot see. Reporting either as "deleted" would be inventing a
    fact the provider explicitly declined to state.
    """
    probe = Probe(url=REVISION_URL, status=401, body=b'{"error":"Invalid username or password."}')
    finding = sentinel.classify_huggingface("demucs", ASSET, probe, None)

    assert finding.availability is Availability.AUTHENTICATION_REQUIRED
    rendered = " ".join([finding.summary, *finding.details])
    assert "NOT a statement that the artifact is gone" in rendered
    assert "indistinguishable" in rendered
    for claim in ("deleted", "removed", "no longer exists", "does not exist any"):
        assert claim not in rendered.lower(), f"the sentinel asserted {claim!r} on a 401"


def test_a_server_error_is_transient_and_says_nothing_about_the_artifact() -> None:
    probe = Probe(url=REVISION_URL, status=503, body=b"")
    finding = sentinel.classify_huggingface("demucs", ASSET, probe, None)
    assert finding.availability is Availability.TRANSIENT
    assert "says nothing about the artifact" in " ".join(finding.details)


def test_an_unreachable_provider_is_transient() -> None:
    probe = Probe(url=REVISION_URL, error="URLError: [Errno 8] nodename nor servname provided")
    finding = sentinel.classify_huggingface("demucs", ASSET, probe, None)
    assert finding.availability is Availability.TRANSIENT
    assert "could not be reached" in finding.summary


def test_an_unreadable_status_is_unknown_rather_than_forced_into_a_verdict() -> None:
    probe = Probe(url=REVISION_URL, status=418, body=b"")
    finding = sentinel.classify_huggingface("demucs", ASSET, probe, None)
    assert finding.availability is Availability.UNKNOWN


# ---------------------------------------------------------------------------
# Conclusive failures.
# ---------------------------------------------------------------------------


def test_a_404_revision_on_a_reachable_repository_names_which_half_resolved() -> None:
    """A revision is immutable, so this means history moved under the pin."""
    missing = Probe(url=REVISION_URL, status=404, body=b"")
    repository = Probe(url="https://huggingface.co/api/models/x", status=200, body=b"{}")
    finding = sentinel.classify_huggingface("demucs", ASSET, missing, repository)

    assert finding.availability is Availability.REVISION_UNRESOLVABLE
    assert "resolves and revision" in finding.summary
    assert "Nothing here establishes which" in " ".join(finding.details)


def test_a_404_revision_with_an_unreachable_repository_says_neither_resolved() -> None:
    missing = Probe(url=REVISION_URL, status=404, body=b"")
    repository = Probe(url="https://huggingface.co/api/models/x", status=401, body=b"")
    finding = sentinel.classify_huggingface("demucs", ASSET, missing, repository)

    assert finding.availability is Availability.REVISION_UNRESOLVABLE
    assert "neither" in finding.summary


def test_a_pinned_file_that_vanished_from_a_revision_is_paths_missing() -> None:
    document = json.loads(hub_ok().body or b"{}")
    document["siblings"] = [s for s in document["siblings"] if "safetensors" not in s["rfilename"]]
    probe = Probe(url=REVISION_URL, status=200, body=json.dumps(document).encode())

    finding = sentinel.classify_huggingface("demucs", ASSET, probe, None)
    assert finding.availability is Availability.PATHS_MISSING
    assert "955717e8.safetensors" in " ".join(finding.details)


def test_a_changed_published_digest_is_a_mismatch_not_an_absence() -> None:
    document = json.loads(hub_ok().body or b"{}")
    for sibling in document["siblings"]:
        if "lfs" in sibling:
            sibling["lfs"]["sha256"] = "0" * 64
    probe = Probe(url=REVISION_URL, status=200, body=json.dumps(document).encode())

    finding = sentinel.classify_huggingface("demucs", ASSET, probe, None)
    assert finding.availability is Availability.METADATA_MISMATCH
    assert "0" * 64 in " ".join(finding.details)


def test_a_changed_published_size_is_a_mismatch() -> None:
    document = json.loads(hub_ok().body or b"{}")
    document["siblings"][0]["size"] += 1
    probe = Probe(url=REVISION_URL, status=200, body=json.dumps(document).encode())

    finding = sentinel.classify_huggingface("demucs", ASSET, probe, None)
    assert finding.availability is Availability.METADATA_MISMATCH


def test_a_repository_that_became_gated_is_reported_while_still_available() -> None:
    """Resolvable today, and a fresh bootstrap would now need a token."""
    finding = sentinel.classify_huggingface("demucs", ASSET, hub_ok(gated="auto"), None)
    assert finding.availability is Availability.AVAILABLE
    assert "now gated" in " ".join(finding.details)


def test_a_missing_pypi_version_distinguishes_the_two_reasons() -> None:
    missing = Probe(url=VERSION_URL, status=404, body=b"")
    known = Probe(url="https://pypi.org/pypi/demucs/json", status=200, body=b"{}")
    unknown = Probe(url="https://pypi.org/pypi/demucs/json", status=404, body=b"")

    with_project = sentinel.classify_pypi("demucs", DEMUCS, missing, known)
    without = sentinel.classify_pypi("demucs", DEMUCS, missing, unknown)

    assert with_project.availability is Availability.REVISION_UNRESOLVABLE
    assert "is on the index and 4.1.0 is not" in with_project.summary
    assert "no record of demucs at all" in without.summary
    assert "does not distinguish deleted from never-published" in " ".join(with_project.details)


def test_a_missing_artifact_filename_is_paths_missing() -> None:
    finding = sentinel.classify_pypi("demucs", DEMUCS, pypi_ok(filename="something-else.whl"), None)
    assert finding.availability is Availability.PATHS_MISSING


def test_a_changed_wheel_digest_is_a_mismatch() -> None:
    probe = pypi_ok(digests={"sha256": "1" * 64})
    finding = sentinel.classify_pypi("demucs", DEMUCS, probe, None)
    assert finding.availability is Availability.METADATA_MISMATCH
    assert DEMUCS.code.sha256 in " ".join(finding.details)


def test_a_yanked_release_is_still_available_because_an_exact_pin_installs_it() -> None:
    probe = pypi_ok(yanked=True, yanked_reason="broken metadata")
    finding = sentinel.classify_pypi("demucs", DEMUCS, probe, None)
    assert finding.availability is Availability.AVAILABLE
    assert "yanked" in " ".join(finding.details)


# ---------------------------------------------------------------------------
# The exit code, which is the scheduled job's whole interface.
# ---------------------------------------------------------------------------


def finding(availability: object) -> object:
    return sentinel.Finding(
        entry="demucs", kind="assets", identity="x", availability=availability, summary=""
    )


@pytest.mark.parametrize(
    ("availabilities", "expected"),
    [
        ([Availability.AVAILABLE, Availability.AVAILABLE], 0),
        ([Availability.AVAILABLE, Availability.PATHS_MISSING], 1),
        ([Availability.AVAILABLE, Availability.TRANSIENT], 2),
        ([Availability.AUTHENTICATION_REQUIRED], 2),
        # A conclusive failure outranks an inconclusive one: something IS gone.
        ([Availability.TRANSIENT, Availability.REVISION_UNRESOLVABLE], 1),
    ],
)
def test_the_exit_code_separates_gone_from_could_not_check(
    availabilities: list[object], expected: int
) -> None:
    """A monitor that returned "fine" because it could not reach the network
    would be worse than no monitor, and one that returned "gone" for the same
    reason would be worse still."""
    assert sentinel.exit_code([finding(a) for a in availabilities]) == expected


def test_the_report_never_calls_an_unconfirmed_artifact_gone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    findings = [sentinel.classify_huggingface("demucs", ASSET, Probe(REVISION_URL, 401), None)]
    code = sentinel.exit_code(findings)
    sentinel.report(findings, code)

    out = capsys.readouterr().out
    assert code == 2
    assert "could not be confirmed either way" in out
    assert "Nothing here says an artifact is gone" in out


def test_the_script_declares_that_it_downloads_no_weights() -> None:
    """Asserted against the source, because it is the script's central promise."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "metadata only" in source
    for forbidden in ("hf_hub_download", "snapshot_download", "resolve/", "huggingface_hub"):
        assert forbidden not in source, f"the sentinel could fetch bytes: {forbidden!r}"
