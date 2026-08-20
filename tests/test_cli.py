"""CLI tests.

The CLI's contract is its exit codes and the usefulness of its errors, so that is
what these check. They also pin the property that makes `doctor` usable during
bootstrap: an absent model dependency is information, never a failure.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from spectral_loom.cli import EXIT_INVALID, EXIT_OK, EXIT_UNREADABLE, collect_checks, main
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


def test_absent_model_dependencies_are_informational_not_failures() -> None:
    """Bootstrap health and inference readiness are different questions."""
    checks = {check.name: check for check in collect_checks(REPO_ROOT)}
    model_checks = [check for name, check in checks.items() if name.startswith("model-dep:")]
    assert model_checks, "doctor must report on the future model cabinet"
    assert all(check.status in {"ok", "info"} for check in model_checks)
    assert not any(check.status == "fail" for check in collect_checks(REPO_ROOT))


def test_doctor_does_not_create_the_directories_it_probes(tmp_path: Path) -> None:
    """`doctor` reports on the world; it does not change it."""
    before = set(tmp_path.iterdir())
    collect_checks(tmp_path)
    assert set(tmp_path.iterdir()) == before


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
