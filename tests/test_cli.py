"""CLI tests.

The CLI's contract is its exit codes and the usefulness of its errors, so that is
what these check. They also pin the property that makes `doctor` usable during
bootstrap: an absent model dependency is information, never a failure.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from spectral_loom.cabinet import CABINET_FILENAME
from spectral_loom.cli import (
    CABINET_PACKAGES_KEPT_OUT,
    EXIT_INVALID,
    EXIT_OK,
    EXIT_UNREADABLE,
    collect_checks,
    main,
)
from tests.test_contracts import VALID_SPEC, minimal_timeline

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_help_works(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    out = capsys.readouterr().out
    assert "doctor" in out
    assert "validate-spec" in out
    assert "validate-timeline" in out
    assert "exit codes" in out


def test_no_command_is_an_error() -> None:
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code != 0


# --- doctor ---------------------------------------------------------------


def test_doctor_reports_the_local_environment(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == EXIT_OK
    out = capsys.readouterr().out
    for expected in ("os", "python", "uv", "ffmpeg", "repository", "writable:"):
        assert expected in out


def test_doctor_json_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor", "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    names = {check["name"] for check in payload["checks"]}
    assert {"os", "python", "uv", "ffmpeg", "repository"} <= names


def test_doctor_does_not_create_the_directories_it_probes(tmp_path: Path) -> None:
    """`doctor` reports on the world; it does not change it."""
    before = set(tmp_path.iterdir())
    collect_checks(tmp_path)
    assert set(tmp_path.iterdir()) == before


# --- doctor and the model cabinet -----------------------------------------
#
# These build cabinet states on disk rather than requiring one. A test that
# passes only on a machine with eleven gigabytes of weights is not a test of
# `doctor`, it is a test of that machine.


def _cabinet_at(root: Path, *, revision: str = "b" * 40) -> Path:
    """A one-entry cabinet with one small asset, written into `tmp_path`."""
    payload = b"weights" * 8
    digest = hashlib.sha256(payload).hexdigest()
    (root / CABINET_FILENAME).write_text(
        f"""
schema_version = "1"

[runtime]
python = "3.11"
uv_extra = "cabinet"
environment_path = ".venv-cabinet"
torch = "2.13.0"
accelerator = "mps"

[entry.toy]
purpose = "testing"
adapter = "toy"
upstream = "https://example.invalid"

[entry.toy.code]
kind = "pypi"
distribution = "toy"
version = "1.0"
symbol = "toy.run"
license = "MIT"
sha256 = "{"a" * 64}"
artifact = "toy-1.0-py3-none-any.whl"

[[entry.toy.assets]]
kind = "huggingface-repo"
repo_id = "example/toy"
revision = "{revision}"
license = "MIT"
variant = "toy"
total_bytes = {len(payload)}
files = [
  {{ path = "model.safetensors", size = {len(payload)}, sha256 = "{digest}" }},
]
""",
        encoding="utf-8",
    )
    return root


def _stock(root: Path, revision: str = "b" * 40, *, contents: bytes = b"weights" * 8) -> None:
    target = root / "models" / "toy" / revision / "model.safetensors"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(contents)


def _checks(root: Path, **kwargs: bool) -> dict[str, str]:
    return {check.name: check.status for check in collect_checks(root, **kwargs)}


def test_an_empty_cabinet_is_information_not_failure(tmp_path: Path) -> None:
    """A fresh clone has a fully pinned, entirely empty cabinet. That is fine.

    Bootstrap health and inference readiness are different questions and do not
    share an exit code; decision 5 says so and this is where it is enforced.
    """
    _cabinet_at(tmp_path)
    checks = _checks(tmp_path)
    assert checks["cabinet"] == "ok"
    assert checks["cabinet-assets:toy"] == "info"
    assert "fail" not in checks.values()
    assert main(["doctor", "--json"]) == EXIT_OK


def test_doctor_distinguishes_present_from_verified(tmp_path: Path) -> None:
    """Two different claims, and `doctor` may only make the cheap one by default."""
    _cabinet_at(tmp_path)
    _stock(tmp_path)

    cheap = {c.name: c.detail for c in collect_checks(tmp_path)}
    assert "present" in cheap["cabinet-assets:toy"]
    assert "hashes not checked" in cheap["cabinet-assets:toy"]

    thorough = {c.name: c.detail for c in collect_checks(tmp_path, verify=True)}
    assert "verified" in thorough["cabinet-assets:toy"]


def test_doctor_reports_wrong_bytes_as_a_blocking_failure(tmp_path: Path) -> None:
    """A file of the right length and the wrong contents is not a warning."""
    _cabinet_at(tmp_path)
    _stock(tmp_path, contents=b"WEIGHTS" * 8)
    assert _checks(tmp_path, verify=True)["cabinet-assets:toy"] == "fail"


def test_doctor_reports_the_license_of_what_it_found(tmp_path: Path) -> None:
    """The weights are untracked, so the license has to survive in the report."""
    _cabinet_at(tmp_path)
    details = {c.name: c.detail for c in collect_checks(tmp_path)}
    assert "[MIT]" in details["cabinet-assets:toy"]


def test_doctor_downloads_nothing_and_writes_nothing(tmp_path: Path) -> None:
    """The netguard fixture covers the first half; this covers the second."""
    _cabinet_at(tmp_path)
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    collect_checks(tmp_path, verify=True)
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")} == before


def test_a_broken_manifest_blocks(tmp_path: Path) -> None:
    """An unreadable cabinet is a real problem with the checkout, unlike an empty one."""
    (tmp_path / CABINET_FILENAME).write_text('schema_version = "9"\n', encoding="utf-8")
    assert _checks(tmp_path)["cabinet"] == "fail"


def test_the_default_environment_stays_light() -> None:
    """decision 5, asserted rather than hoped: no cabinet package in `.venv`.

    If this fails, something installed torch into the environment that runs the
    tests, and `uv sync` is no longer the cheap thing a contributor runs.
    """
    for package in CABINET_PACKAGES_KEPT_OUT:
        assert importlib.util.find_spec(package) is None, f"{package} leaked into the default env"


def test_the_committed_cabinet_is_reported_for_this_repository() -> None:
    """The real manifest, at whatever stocking level this machine happens to be."""
    checks = {c.name: c for c in collect_checks(REPO_ROOT)}
    assert checks["cabinet"].status == "ok"
    for name in ("ace-step", "demucs", "basic-pitch"):
        assert f"cabinet-code:{name}" in checks
        assert f"cabinet-assets:{name}" in checks
    assert checks["accelerator"].status == "info", "a backend doctor did not measure is not a fact"


# --- validate-spec --------------------------------------------------------


def test_committed_example_specification_validates(capsys: pytest.CaptureFixture[str]) -> None:
    example = REPO_ROOT / "corpus" / "specs" / "example.yaml"
    assert main(["validate-spec", str(example)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "valid song specification" in out
    assert "requested, not observed" in out
    assert "UNPINNED" in out, "an unresolved generator revision must be visible, not silent"


def test_valid_json_spec_validates(write_json: Callable[[str, Any], Path]) -> None:
    assert main(["validate-spec", str(write_json("spec.json", VALID_SPEC))]) == EXIT_OK


def test_invalid_spec_names_the_offending_field(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    broken = {**VALID_SPEC, "requested_bpm": -4}
    assert main(["validate-spec", str(write_json("spec.json", broken))]) == EXIT_INVALID
    err = capsys.readouterr().err
    assert "requested_bpm" in err
    assert "greater than 0" in err


def test_spec_missing_a_required_field_reports_it(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    partial = {key: value for key, value in VALID_SPEC.items() if key != "seed"}
    assert main(["validate-spec", str(write_json("spec.json", partial))]) == EXIT_INVALID
    assert "seed" in capsys.readouterr().err


# --- validate-timeline ----------------------------------------------------


def test_minimal_timeline_fixture_validates(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """A timeline synthesized during the test run, never a committed artifact."""
    document = minimal_timeline().model_dump(mode="json")
    path = write_json("song.timeline.json", document)
    assert main(["validate-timeline", str(path)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "valid song timeline" in out
    assert "activity" in out


def test_timeline_summary_json_lists_stages_and_tracks(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_json("song.timeline.json", minimal_timeline().model_dump(mode="json"))
    assert main(["validate-timeline", str(path), "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["summary"]["stages"] == ["activity"]
    assert payload["summary"]["tracks"] == {"bass": 1}


def test_timeline_with_dangling_evidence_fails_usefully(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    document = minimal_timeline().model_dump(mode="json")
    document["tracks"][0]["events"][0]["evidence"]["stage"] = "separation"
    path = write_json("song.timeline.json", document)
    assert main(["validate-timeline", str(path)]) == EXIT_INVALID
    assert "not in this timeline's provenance" in capsys.readouterr().err


# --- failure modes --------------------------------------------------------


def test_missing_file_is_unreadable_not_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate-spec", str(tmp_path / "absent.json")]) == EXIT_UNREADABLE
    assert "cannot read" in capsys.readouterr().err


def test_malformed_json_is_invalid_and_reports_position(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "spec.json"
    path.write_text('{"specimen_id": "x",,}', encoding="utf-8")
    assert main(["validate-spec", str(path)]) == EXIT_INVALID
    err = capsys.readouterr().err
    assert "not valid JSON" in err
    assert "line 1" in err


def test_malformed_yaml_is_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("specimen_id: x\n  bad: [unclosed\n", encoding="utf-8")
    assert main(["validate-spec", str(path)]) == EXIT_INVALID
    assert "not valid YAML" in capsys.readouterr().err


def test_non_mapping_document_is_rejected(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["validate-spec", str(write_json("spec.json", ["not", "a", "mapping"]))])
        == EXIT_INVALID
    )
    assert "expected a mapping" in capsys.readouterr().err


def test_failure_json_output_carries_the_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate-timeline", str(tmp_path / "absent.json"), "--json"]) == EXIT_UNREADABLE
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert payload["exit_code"] == EXIT_UNREADABLE
