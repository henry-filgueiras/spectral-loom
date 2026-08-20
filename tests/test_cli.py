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
import yaml

from spectral_loom.cabinet import CABINET_FILENAME
from spectral_loom.cli import (
    CABINET_PACKAGES_KEPT_OUT,
    EXIT_BLOCKED,
    EXIT_INVALID,
    EXIT_OK,
    EXIT_UNREADABLE,
    collect_checks,
    main,
)
from spectral_loom.contracts import SongSpec
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
    assert "UNPINNED" not in out, "the example was pinned at gate 1"


def test_the_example_specification_agrees_with_the_cabinet() -> None:
    """The two places a revision is written must not drift apart.

    They are both tracked, they are edited in different rounds, and a
    specification pinned to a revision the cabinet no longer stocks generates
    nothing while looking perfectly valid.
    """
    from spectral_loom.cabinet import load_repository_cabinet

    spec = SongSpec.model_validate(
        yaml.safe_load((REPO_ROOT / "corpus" / "specs" / "example.yaml").read_text())
    )
    cabinet = load_repository_cabinet(REPO_ROOT)
    _name, entry = cabinet.entry_for_adapter(spec.generator.adapter)
    assert spec.generator.model_id == entry.assets[0].repo_id
    assert spec.generator.revision == entry.assets[0].revision


def test_an_unpinned_specification_still_reports_unpinned(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """The property the example used to carry, kept where it cannot be lost."""
    unpinned = {**VALID_SPEC, "generator": {**VALID_SPEC["generator"], "revision": None}}
    assert main(["validate-spec", str(write_json("spec.json", unpinned))]) == EXIT_OK
    assert "UNPINNED" in capsys.readouterr().out


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


# --- generate --------------------------------------------------------------
#
# Only the refusals are testable here. Generation itself needs eleven gigabytes
# and a GPU, and `decision:7` keeps both out of the default suite.


def test_generate_refuses_an_unpinned_specification(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Blocked, not invalid: the document is fine, the world is not ready."""
    unpinned = {**VALID_SPEC, "generator": {**VALID_SPEC["generator"], "revision": None}}
    path = write_json("spec.json", unpinned)
    (path.parent / CABINET_FILENAME).write_text(
        (REPO_ROOT / CABINET_FILENAME).read_text(), encoding="utf-8"
    )
    assert main(["generate", str(path)]) == EXIT_BLOCKED
    err = capsys.readouterr().err
    assert "blocked" in err
    assert "revision is null" in err


def test_generate_reports_an_unreadable_specification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["generate", str(tmp_path / "absent.yaml")]) == EXIT_UNREADABLE


def test_generate_anchors_on_the_cabinet_not_on_git(
    write_json: Callable[[str, Any], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """A specification outside any checkout still finds the cabinet beside it.

    `doctor` anchors on `.git` because it reports on a checkout. `generate`
    anchors on `model-cabinet.toml` because everything it needs — the pinned
    identities, the weights, the output tree — hangs off the manifest.
    """
    path = write_json("spec.json", VALID_SPEC)
    assert not (path.parent / ".git").exists()
    assert main(["generate", str(path)]) == EXIT_BLOCKED
    assert "cannot read" in capsys.readouterr().err, "no manifest beside it, and it says so"


# --- accept ----------------------------------------------------------------
#
# `accept` is the one command whose whole job is binding a human's words to a
# specific byte stream, so what is worth testing is what it refuses to bind.


def _accept_fixture(root: Path, *, audio: bytes = b"RIFF....WAVEfmt ") -> tuple[Path, str]:
    """A repository-shaped directory with one generated specimen in it."""
    (root / CABINET_FILENAME).write_text(
        (REPO_ROOT / CABINET_FILENAME).read_text(), encoding="utf-8"
    )
    directory = root / "corpus/generated/sparse-funk-exposed-bass"
    directory.mkdir(parents=True)
    audio_path = directory / "source.wav"
    audio_path.write_bytes(audio)
    digest = "sha256:" + hashlib.sha256(audio).hexdigest()

    manifest = {
        "schema_id": "spectral-loom/generation-manifest",
        "schema_version": "0.1.0",
        "specimen_id": "sparse-funk-exposed-bass",
        "spec_path": "corpus/specs/example.yaml",
        "spec_hash": "sha256:" + "c" * 64,
        "source_audio": {
            "hash": digest,
            "duration_s": 45.0,
            "sample_rate_hz": 48000,
            "channels": 2,
        },
        "provenance": [
            {
                "stage": "generate",
                "tool": "diffusers.AceStepPipeline",
                "tool_revision": "diffusers==0.40.0 x@" + "0" * 40,
                "truth_layer": "requested",
                "input_hashes": {"spec": "sha256:" + "c" * 64},
                "parameters": {"prompt": "sparse instrumental", "seed": 1},
                "output_hashes": {"source": digest},
            }
        ],
    }
    (directory / "generation-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return audio_path, digest


ACCEPT_ANSWERS = [
    "--bass-exposed",
    "yes",
    "--silence-between-phrases",
    "yes",
    "--parts-separable",
    "yes",
    "--generator-failure",
    "no",
]


def _accept_argv(*extra: str) -> list[str]:
    return [
        "accept",
        "sparse-funk-exposed-bass",
        "--reviewer",
        "Henry",
        "--reviewed-on",
        "2026-08-20",
        *ACCEPT_ANSWERS,
        *extra,
    ]


def test_accept_writes_a_review_keyed_by_the_hash_it_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, digest = _accept_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(_accept_argv("--json")) == EXIT_OK

    written = sorted((tmp_path / "corpus/reviews").glob("*.review.json"))
    assert len(written) == 1
    assert digest.split(":")[1][:12] in written[0].name
    document = json.loads(written[0].read_text())
    assert document["source_audio"]["hash"] == digest
    assert document["review"]["accepted"] is True
    assert document["review"]["reviewer"] == "Henry"


def test_accept_refuses_when_the_audio_no_longer_matches_its_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The manifest is a claim about a file, and the file is what is reviewed."""
    audio_path, _ = _accept_fixture(tmp_path)
    audio_path.write_bytes(b"different bytes entirely")
    monkeypatch.chdir(tmp_path)

    assert main(_accept_argv()) == EXIT_BLOCKED
    assert "has since changed" in capsys.readouterr().err


def test_accept_refuses_without_a_generation_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Accepting unattributable bytes would record a judgement about nothing."""
    _accept_fixture(tmp_path)
    (tmp_path / "corpus/generated/sparse-funk-exposed-bass/generation-manifest.json").unlink()
    monkeypatch.chdir(tmp_path)

    assert main(_accept_argv()) == EXIT_BLOCKED
    assert "cannot be attributed" in capsys.readouterr().err


def test_accept_will_not_quietly_overwrite_a_recorded_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _accept_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(_accept_argv()) == EXIT_OK
    assert main(_accept_argv()) == EXIT_BLOCKED
    assert "deliberate act" in capsys.readouterr().err
    assert main(_accept_argv("--force")) == EXIT_OK


def test_accept_records_a_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _accept_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    argv = [
        "accept",
        "sparse-funk-exposed-bass",
        "--reviewer",
        "Henry",
        "--reviewed-on",
        "2026-08-20",
        "--bass-exposed",
        "no",
        "--silence-between-phrases",
        "unclear",
        "--parts-separable",
        "no",
        "--generator-failure",
        "yes",
        "--reject",
        "--summary",
        "voice-like pad throughout; the bass is buried",
    ]
    assert main(argv) == EXIT_OK

    written = next((tmp_path / "corpus/reviews").glob("*.review.json"))
    document = json.loads(written.read_text())
    assert document["review"]["accepted"] is False
    assert "buried" in document["review"]["notes"]


def test_accept_requires_every_criterion(tmp_path: Path) -> None:
    """A review with a blank question is a partially examined assumption."""
    with pytest.raises(SystemExit) as caught:
        main(["accept", "x", "--reviewer", "H", "--reviewed-on", "2026-08-20"])
    assert caught.value.code == 2  # argparse's own usage error


def test_accept_rejects_a_malformed_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _accept_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(_accept_argv("--note", "no-equals-sign")) == EXIT_INVALID
    assert "CRITERION=TEXT" in capsys.readouterr().err
