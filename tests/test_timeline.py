"""Tests for the compiler: its refusals, its semantics, and its determinism.

Everything here runs on synthesized WAVs in `tmp_path`, because everything worth
testing about this stage is either a check performed before a sample is read or
a property of the document it writes.

Three properties get most of the attention.

**Two human verdicts are preconditions, and neither is satisfiable by a path.**
Gate 2 accepted source bytes; gate 3 accepted a separation, identified by its
manifest's content hash. A stem that changed after either verdict stops the
compile and says which record it disagrees with.

**The document says only what the analysis established.** Three event types.
`activity.sample` observed, the other two inferred. No confidence anywhere,
because nothing here produces a calibrated one. Track names are the separator's
own output labels. Zero intervals is zero intervals inferred, not silence in the
recording.

**The bytes are the same every time.** Gate 4 requires it, and a boundary
artifact that changed when nothing changed could not be cached, diffed, or
compared against a later run. The tests for this look for the *classes* of
nondeterminism — a clock, a path, an ordering — rather than only comparing two
runs, because two runs a millisecond apart can agree by luck.
"""

from __future__ import annotations

import json
import wave
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from spectral_loom.contracts import (
    CriterionResponse,
    SeparationManifest,
    SongTimeline,
    TruthLayer,
)
from spectral_loom.hashing import hash_bytes, hash_file
from spectral_loom.review import (
    GATE_2_CRITERIA,
    GATE_3_CRITERIA,
    build_review,
    build_separation_review,
    review_path,
    separation_review_path,
    write_review,
    write_separation_review,
)
from spectral_loom.timeline import (
    EVENT_ORDER,
    INTERVAL_STAGE,
    MEASURE_STAGE,
    ONSET_STAGE,
    RECEIPT_FILENAME,
    CompileError,
    cache_miss_reason,
    canonical_bytes,
    compile_timeline,
    load_receipt,
    plan,
)
from tests.test_analysis import impulses_at, place, silence
from tests.test_review import manifest as generation_manifest

SPECIMEN = "sparse-funk-exposed-bass"
RATE = 8000
DURATION_S = 4.0

#: What each synthesized model output contains, chosen so that the four cases
#: this project actually met are all present: busy, sparse, continuous, and a
#: near-silent output that is nothing but a noise floor.
SHAPES: dict[str, str] = {
    "drums": "impulses",
    "bass": "bursts",
    "other": "continuous",
    "vocals": "noise-floor",
}


def signal_for(shape: str) -> np.ndarray:
    if shape == "impulses":
        return impulses_at(DURATION_S, [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
    if shape == "bursts":
        return place(DURATION_S, [(0.4, 1.4), (2.4, 3.4)], amplitude=0.4)
    if shape == "continuous":
        return place(DURATION_S, [(0.0, DURATION_S)], amplitude=0.3)
    if shape == "noise-floor":
        return np.random.default_rng(20260820).normal(0.0, 0.0009, int(DURATION_S * RATE))
    raise AssertionError(shape)


def write_wav(path: Path, signal: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(signal, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(data)
    return path


# ---------------------------------------------------------------------------
# A repository-shaped fixture: source, stems, two manifests, two reviews.
# ---------------------------------------------------------------------------


def build_repository(
    root: Path, *, separation_reviewed: bool = True, separation_accepted: bool = True
) -> SeparationManifest:
    """Everything `plan` reads, and nothing it does not."""
    source = write_wav(
        root / "corpus/generated" / SPECIMEN / "source.wav",
        place(DURATION_S, [(0.0, 4.0)], amplitude=0.3),
    )
    source_hash = hash_file(source)

    generation = generation_manifest(source_hash)
    (root / "corpus/generated" / SPECIMEN / "generation-manifest.json").write_text(
        json.dumps(generation.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    specimen_review = build_review(
        generation,
        manifest_bytes=b"{}",
        cabinet_bytes=b"",
        reviewer="Henry",
        reviewed_on=date(2026, 8, 20),
        responses={c.id: CriterionResponse.YES for c in GATE_2_CRITERIA},
        accepted=True,
    )
    specimen_review_path = review_path(root, SPECIMEN, source_hash)
    write_review(specimen_review_path, specimen_review)

    separation_dir = root / "corpus/derived" / SPECIMEN / "separation"
    stems: list[dict[str, Any]] = []
    for name, shape in SHAPES.items():
        target = write_wav(separation_dir / f"{name}.wav", signal_for(shape))
        stems.append(
            {
                "model_output": name,
                "audio": {
                    "path": str(target.relative_to(root)),
                    "hash": hash_file(target),
                    "duration_s": DURATION_S,
                    "sample_rate_hz": RATE,
                    "channels": 1,
                    "peak": 0.9,
                    "rms": 0.1,
                },
                "clipped_samples": 0,
                "non_finite_samples": 0,
            }
        )

    manifest = SeparationManifest.model_validate(
        {
            "specimen_id": SPECIMEN,
            "source_audio": {
                "hash": source_hash,
                "duration_s": DURATION_S,
                "sample_rate_hz": RATE,
                "channels": 1,
            },
            "source_path": str(source.relative_to(root)),
            "review_hash": hash_file(specimen_review_path),
            "generation_manifest_hash": "sha256:" + "e" * 64,
            "separator": {
                "adapter": "demucs",
                "code_distribution": "demucs",
                "code_version": "4.1.0",
                "code_sha256": "f" * 64,
                "loaded_with": "demucs.hf.load_safetensors_model",
                "applied_with": "demucs.apply.apply_model",
                "weights_repo": "adefossez/HTDemucs",
                "weights_revision": "b" * 40,
                "weights_variant": "htdemucs",
                "model_signatures": ["955717e8"],
                "model_sample_rate_hz": RATE,
                "model_audio_channels": 1,
                "sources": list(SHAPES),
            },
            "stems": stems,
            "diagnostics": [],
            "cache_key": "sha256:" + "7" * 64,
            "cache_key_inputs": {"source_hash": source_hash},
            "warnings": [],
            "provenance": [
                {
                    "stage": "separate",
                    "tool": "demucs.apply.apply_model",
                    "tool_revision": "demucs==4.1.0 adefossez/HTDemucs@" + "b" * 40,
                    "truth_layer": "inferred",
                    "input_hashes": {"source": source_hash},
                    "parameters": {"shifts": 0},
                    "output_hashes": {s["model_output"]: s["audio"]["hash"] for s in stems},
                    "runtime": "cpython3.11 darwin-arm64 mps",
                    "started_at": "2026-08-20T23:24:17.257172Z",
                    "duration_ms": 2792,
                }
            ],
        }
    )
    manifest_path = separation_dir / "separation-manifest.json"
    manifest_bytes = (
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)

    if separation_reviewed:
        review = build_separation_review(
            manifest,
            manifest_path=str(manifest_path.relative_to(root)),
            manifest_bytes=manifest_bytes,
            reviewer="Henry",
            reviewed_on=date(2026, 8, 20),
            responses={c.id: CriterionResponse.YES for c in GATE_3_CRITERIA},
            accepted=separation_accepted,
        )
        write_separation_review(
            separation_review_path(root, SPECIMEN, hash_bytes(manifest_bytes)), review
        )
    return manifest


def compiled(root: Path) -> tuple[SongTimeline, Any, Any]:
    build_repository(root)
    prepared = plan(SPECIMEN, root)
    timeline, receipt, produced = compile_timeline(prepared)
    assert produced
    return timeline, receipt, prepared


# ---------------------------------------------------------------------------
# Refusals: the preconditions, in the order a person would want them.
# ---------------------------------------------------------------------------


def test_compiling_refuses_when_there_is_no_separation(tmp_path: Path) -> None:
    with pytest.raises(CompileError, match="no separation manifest at"):
        plan(SPECIMEN, tmp_path)


def test_compiling_refuses_a_separation_nobody_reviewed(tmp_path: Path) -> None:
    build_repository(tmp_path, separation_reviewed=False)
    with pytest.raises(CompileError, match="Gate 3 is passed by a human hearing the stems"):
        plan(SPECIMEN, tmp_path)


def test_compiling_refuses_a_separation_a_human_rejected(tmp_path: Path) -> None:
    build_repository(tmp_path, separation_accepted=False)
    with pytest.raises(CompileError, match="did NOT accept"):
        plan(SPECIMEN, tmp_path)


def test_compiling_refuses_a_separation_regenerated_since_the_review(tmp_path: Path) -> None:
    """The refusal this stage exists to make.

    The review is on disk, the specimen id matches, the directory matches — and
    the separation manifest is not the one anybody heard.
    """
    build_repository(tmp_path)
    manifest_path = tmp_path / "corpus/derived" / SPECIMEN / "separation/separation-manifest.json"
    document = json.loads(manifest_path.read_text())
    document["warnings"] = ["re-separated later, on another day"]
    manifest_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")

    with pytest.raises(CompileError) as caught:
        plan(SPECIMEN, tmp_path)
    assert "nobody has reviewed" in str(caught.value)


def test_compiling_refuses_a_stem_that_changed_since_the_separation(tmp_path: Path) -> None:
    build_repository(tmp_path)
    stem = tmp_path / "corpus/derived" / SPECIMEN / "separation/bass.wav"
    stem.write_bytes(stem.read_bytes() + b"\x00\x00")
    with pytest.raises(CompileError, match="not the bytes that were separated"):
        plan(SPECIMEN, tmp_path)


def test_compiling_refuses_a_stem_that_is_missing(tmp_path: Path) -> None:
    build_repository(tmp_path)
    (tmp_path / "corpus/derived" / SPECIMEN / "separation/other.wav").unlink()
    with pytest.raises(CompileError, match="a timeline about nothing"):
        plan(SPECIMEN, tmp_path)


def test_compiling_refuses_when_the_source_recording_is_gone(tmp_path: Path) -> None:
    """The timeline is a set of claims about a recording nobody could check."""
    build_repository(tmp_path)
    (tmp_path / "corpus/generated" / SPECIMEN / "source.wav").unlink()
    with pytest.raises(CompileError, match="cannot be checked by anybody"):
        plan(SPECIMEN, tmp_path)


def test_compiling_refuses_stems_that_cannot_share_the_source_timeline(tmp_path: Path) -> None:
    manifest = build_repository(tmp_path)
    manifest_path = tmp_path / "corpus/derived" / SPECIMEN / "separation/separation-manifest.json"
    document = json.loads(manifest_path.read_text())
    document["source_audio"]["duration_s"] = DURATION_S + 5.0
    manifest_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    # Re-review, so the failure under test is the duration and not the hash.
    review = build_separation_review(
        SeparationManifest.model_validate(document),
        manifest_path=str(manifest_path.relative_to(tmp_path)),
        manifest_bytes=manifest_path.read_bytes(),
        reviewer="Henry",
        reviewed_on=date(2026, 8, 20),
        responses={c.id: CriterionResponse.YES for c in GATE_3_CRITERIA},
        accepted=True,
    )
    write_separation_review(
        separation_review_path(tmp_path, SPECIMEN, hash_file(manifest_path)), review
    )
    assert manifest.source_audio.duration_s == DURATION_S

    with pytest.raises(CompileError, match="cannot be placed on one timeline"):
        plan(SPECIMEN, tmp_path)


# ---------------------------------------------------------------------------
# What the document says.
# ---------------------------------------------------------------------------


def test_the_timeline_is_about_the_original_recording_not_a_stem(tmp_path: Path) -> None:
    """A stem is evidence for an event. It is not what the timeline is about."""
    timeline, _, prepared = compiled(tmp_path)
    assert timeline.source_audio.hash == prepared.source_hash
    assert timeline.source_audio == prepared.manifest.source_audio
    assert timeline.time_unit == "seconds"


def test_only_the_three_event_types_gate_four_admits_appear(tmp_path: Path) -> None:
    timeline, _, _ = compiled(tmp_path)
    kinds = {event.type for track in timeline.tracks for event in track.events}
    assert kinds <= set(EVENT_ORDER)
    assert "note" not in kinds


def test_tracks_are_named_for_the_model_output_that_produced_them(tmp_path: Path) -> None:
    timeline, _, _ = compiled(tmp_path)
    assert [track.id for track in timeline.tracks] == [f"htdemucs.{n}" for n in SHAPES]
    for track in timeline.tracks:
        assert track.role is not None
        assert "model output" in track.role
    # And nothing has been renamed after a guess about what is in it.
    rendered = json.dumps(timeline.model_dump(mode="json"))
    assert "guitar" not in rendered
    assert "synth" not in rendered


def test_measurement_is_observed_and_the_two_rules_are_inferred(tmp_path: Path) -> None:
    timeline, _, _ = compiled(tmp_path)
    layers = {entry.stage: entry.truth_layer for entry in timeline.provenance}
    assert layers[MEASURE_STAGE] is TruthLayer.OBSERVED
    assert layers[INTERVAL_STAGE] is TruthLayer.INFERRED
    assert layers[ONSET_STAGE] is TruthLayer.INFERRED
    # And the lineage back to the request survives with its own layer intact.
    assert layers["generate"] is TruthLayer.REQUESTED
    assert layers["separate"] is TruthLayer.INFERRED


def test_no_event_carries_a_manufactured_confidence(tmp_path: Path) -> None:
    """The schema has the field. Nothing here produces a calibrated value for it."""
    timeline, _, _ = compiled(tmp_path)
    assert all(event.confidence is None for track in timeline.tracks for event in track.events)


def test_an_onset_carries_the_statistic_that_produced_it(tmp_path: Path) -> None:
    timeline, _, _ = compiled(tmp_path)
    onsets = [event for track in timeline.tracks for event in track.events if event.type == "onset"]
    assert onsets
    for onset in onsets:
        assert onset.payload["flux"] > onset.payload["threshold"]  # type: ignore[operator]
        assert "margin" in onset.payload
        assert "temporal_resolution_s" in onset.payload
        assert onset.end_s is None


def test_every_event_cites_evidence_that_resolves(tmp_path: Path) -> None:
    timeline, _, prepared = compiled(tmp_path)
    stages = {entry.stage for entry in timeline.provenance}
    by_path = {stem.relative_path: stem.hash for stem in prepared.stems}
    for track in timeline.tracks:
        for event in track.events:
            assert event.evidence.stage in stages
            assert event.evidence.artifact in by_path
            assert event.evidence.artifact_hash == by_path[event.evidence.artifact]


def test_an_activity_sample_spans_the_window_it_measured(tmp_path: Path) -> None:
    timeline, _, _ = compiled(tmp_path)
    samples = [e for e in timeline.tracks[0].events if e.type == "activity.sample"]
    for sample in samples:
        assert sample.end_s is not None
        assert sample.end_s - sample.start_s == pytest.approx(
            float(sample.payload["analysis_window_s"]),  # type: ignore[arg-type]
            abs=1e-6,
        )


def test_a_near_silent_output_produces_no_inference_rather_than_a_claim(tmp_path: Path) -> None:
    """The `vocals` case, end to end.

    It gets its measurements, because a measurement of quiet is still a
    measurement. It gets no intervals and no onsets, and the document says so by
    containing nothing — which the review surface must render as "nothing was
    inferred" rather than as "nothing was there".
    """
    timeline, _, _ = compiled(tmp_path)
    quiet = next(t for t in timeline.tracks if t.id == "htdemucs.vocals")
    kinds = [event.type for event in quiet.events]
    assert kinds.count("activity.sample") > 0
    assert kinds.count("activity.interval") == 0
    assert kinds.count("onset") == 0


def test_the_parameters_that_change_an_event_are_in_the_document(tmp_path: Path) -> None:
    timeline, _, _ = compiled(tmp_path)
    by_stage = {entry.stage: entry.parameters for entry in timeline.provenance}
    for key in ("window_samples", "hop_samples", "enter_dbfs", "exit_dbfs", "merge_gap_s"):
        assert key in by_stage[INTERVAL_STAGE]
    for key in ("fft_samples", "hop_samples", "median_multiplier", "flux_floor", "min_gap_s"):
        assert key in by_stage[ONSET_STAGE]
    assert by_stage[MEASURE_STAGE]["downmix"] == "channel_mean"


# ---------------------------------------------------------------------------
# Determinism.
# ---------------------------------------------------------------------------


def test_events_are_in_a_stable_order(tmp_path: Path) -> None:
    timeline, _, _ = compiled(tmp_path)
    for track in timeline.tracks:
        keys = [(e.start_s, EVENT_ORDER[e.type]) for e in track.events]
        assert keys == sorted(keys)


def test_the_canonical_bytes_carry_no_clock_and_no_local_path(tmp_path: Path) -> None:
    """The classes of nondeterminism, looked for by name.

    Comparing two runs would catch these only by luck: two compiles a
    millisecond apart can agree on a timestamp truncated to the second.
    """
    timeline, receipt, _ = compiled(tmp_path)
    text = canonical_bytes(timeline).decode("utf-8")

    assert str(tmp_path) not in text
    assert "/private/" not in text
    assert "partial" not in text
    # The run telemetry exists — it is just not in here.
    assert receipt.duration_ms >= 0
    assert receipt.runtime.startswith("cpython")
    for entry in timeline.provenance:
        if entry.stage in {MEASURE_STAGE, INTERVAL_STAGE, ONSET_STAGE}:
            assert entry.started_at is None
            assert entry.duration_ms is None
            assert entry.runtime is None


def test_recompiling_unchanged_inputs_produces_identical_bytes(tmp_path: Path) -> None:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)

    first, first_receipt, produced = compile_timeline(prepared)
    assert produced
    second, second_receipt, again = compile_timeline(plan(SPECIMEN, tmp_path), force=True)
    assert again

    assert canonical_bytes(first) == canonical_bytes(second)
    assert first_receipt.timeline_sha256 == second_receipt.timeline_sha256
    assert first_receipt.cache_key == second_receipt.cache_key


def test_an_unchanged_request_is_a_verified_cache_hit(tmp_path: Path) -> None:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    _, first, produced = compile_timeline(prepared)
    assert produced

    timeline, receipt, again = compile_timeline(plan(SPECIMEN, tmp_path))
    assert not again
    assert receipt.timeline_sha256 == first.timeline_sha256
    assert hash_file(prepared.timeline_path) == receipt.timeline_sha256
    assert timeline.tracks


def test_a_changed_output_is_not_a_cache_hit(tmp_path: Path) -> None:
    """A receipt describing a document that has since changed is not a cache entry."""
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    compile_timeline(prepared)
    prepared.timeline_path.write_text(
        prepared.timeline_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
    )

    reason = cache_miss_reason(prepared, load_receipt(prepared.receipt_path))
    assert reason is not None
    assert "hashes to" in reason

    _, _, produced = compile_timeline(plan(SPECIMEN, tmp_path))
    assert produced


def test_a_missing_output_is_not_a_cache_hit(tmp_path: Path) -> None:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    compile_timeline(prepared)
    prepared.timeline_path.unlink()

    reason = cache_miss_reason(prepared, load_receipt(prepared.receipt_path))
    assert reason is not None
    assert "declared output is missing" in reason


def test_a_different_parameter_is_a_different_key(tmp_path: Path) -> None:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    compile_timeline(prepared)

    receipt = load_receipt(prepared.receipt_path)
    altered = receipt.model_copy(update={"cache_key": "sha256:" + "0" * 64})
    reason = cache_miss_reason(prepared, altered)
    assert reason is not None
    assert "cache key differs" in reason


def test_the_cache_key_covers_the_stems_the_tool_and_the_parameters(tmp_path: Path) -> None:
    build_repository(tmp_path)
    inputs = plan(SPECIMEN, tmp_path).cache_key_inputs
    assert set(inputs["stem_hashes"]) == set(SHAPES)  # type: ignore[arg-type]
    assert inputs["tool"] == "spectral_loom.analysis"
    assert "numpy_version" in inputs
    assert INTERVAL_STAGE in inputs["parameters"]  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Bytes this stage did not write.
# ---------------------------------------------------------------------------


def test_an_unexpected_directory_where_the_output_goes_stops_the_run(tmp_path: Path) -> None:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    prepared.output_dir.mkdir(parents=True)
    (prepared.output_dir / "somebody-elses-notes.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(CompileError, match="not something this stage wrote"):
        compile_timeline(prepared)
    assert (prepared.output_dir / "somebody-elses-notes.txt").read_text() == "keep me"


def test_a_previous_compile_is_replaced_without_ceremony(tmp_path: Path) -> None:
    """Its own output is regenerable in seconds and does not need a flag."""
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    compile_timeline(prepared)
    _, _, produced = compile_timeline(prepared, force=True)
    assert produced
    assert (prepared.output_dir / RECEIPT_FILENAME).is_file()


def test_a_workspace_is_cleaned_up_when_the_compile_fails(tmp_path: Path) -> None:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    # Truncate a stem *after* planning, so the failure happens during the read
    # rather than during verification.
    (tmp_path / "corpus/derived" / SPECIMEN / "separation/bass.wav").write_bytes(b"RIFFnope")

    with pytest.raises(CompileError):
        compile_timeline(prepared)
    assert not list(prepared.output_dir.parent.glob(".timeline.partial.*"))


def test_a_timeline_of_pure_silence_is_measurements_and_nothing_else(tmp_path: Path) -> None:
    """Digital silence still gets measured. It just claims nothing."""
    build_repository(tmp_path)
    separation = tmp_path / "corpus/derived" / SPECIMEN / "separation"
    write_wav(separation / "drums.wav", silence(DURATION_S))
    # Rebuild the records so the only difference is the audio.
    _rehash_repository(tmp_path)

    timeline, _, _ = compile_timeline(plan(SPECIMEN, tmp_path))
    quiet = next(t for t in timeline.tracks if t.id == "htdemucs.drums")
    assert {e.type for e in quiet.events} == {"activity.sample"}
    assert all(e.payload["rms_dbfs"] == -120.0 for e in quiet.events)


def _rehash_repository(root: Path) -> None:
    """Re-derive the manifest and the gate 3 review after a stem was replaced."""
    separation = root / "corpus/derived" / SPECIMEN / "separation"
    manifest_path = separation / "separation-manifest.json"
    document = json.loads(manifest_path.read_text())
    for stem in document["stems"]:
        stem["audio"]["hash"] = hash_file(root / stem["audio"]["path"])
    document["provenance"][0]["output_hashes"] = {
        s["model_output"]: s["audio"]["hash"] for s in document["stems"]
    }
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path.write_bytes(payload)

    review = build_separation_review(
        SeparationManifest.model_validate(document),
        manifest_path=str(manifest_path.relative_to(root)),
        manifest_bytes=payload,
        reviewer="Henry",
        reviewed_on=date(2026, 8, 20),
        responses={c.id: CriterionResponse.YES for c in GATE_3_CRITERIA},
        accepted=True,
    )
    write_separation_review(separation_review_path(root, SPECIMEN, hash_bytes(payload)), review)


# ---------------------------------------------------------------------------
# The seven questions, and the one place the answers are split.
# ---------------------------------------------------------------------------

#: `docs/provenance.md`: an artifact whose provenance cannot answer all seven is
#: not evidence of anything. Four of them are answerable from any stage in the
#: document; the rest depend on whether the stage emitted a file of its own.
ALWAYS_IN_THE_DOCUMENT = ("input_hashes", "tool_revision", "parameters", "truth_layer")


def test_every_stage_answers_the_four_questions_that_do_not_move(tmp_path: Path) -> None:
    timeline, _, _ = compiled(tmp_path)
    for entry in timeline.provenance:
        for field in ALWAYS_IN_THE_DOCUMENT:
            assert getattr(entry, field), f"{entry.stage} cannot answer {field}"
        assert entry.tool


def test_the_analysis_stages_carry_no_clock_and_the_receipt_does(tmp_path: Path) -> None:
    """The trade `docs/provenance.md` documents, asserted rather than described.

    Questions 4 and 5 are omitted from the document because they are exactly the
    fields that would make it differ between two runs of the same inputs — and,
    for `runtime`, between two *machines*. Omitting it means a timeline is a
    function of its inputs rather than of who ran it. The answers are not lost;
    they are in the receipt.
    """
    timeline, receipt, _ = compiled(tmp_path)
    analysis = [
        p for p in timeline.provenance if p.stage in {MEASURE_STAGE, INTERVAL_STAGE, ONSET_STAGE}
    ]
    assert len(analysis) == 3
    for entry in analysis:
        assert entry.started_at is None
        assert entry.duration_ms is None
        assert entry.runtime is None
        # Question 6 has no answer here: the stage emits events into the
        # document, not a file, and a document cannot carry its own hash.
        assert entry.output_hashes == {}

    assert receipt.started_at is not None
    assert receipt.duration_ms >= 0
    assert receipt.runtime
    assert receipt.timeline_sha256.startswith("sha256:")


def test_the_copied_upstream_stages_still_answer_all_seven(tmp_path: Path) -> None:
    """The exception is the analysis stages only; nothing else was weakened."""
    timeline, _, _ = compiled(tmp_path)
    for stage in ("generate", "separate"):
        entry = next(p for p in timeline.provenance if p.stage == stage)
        assert entry.runtime and entry.duration_ms is not None
        assert entry.output_hashes, f"{stage} emitted files and must name their hashes"


def test_the_receipt_records_both_human_verdicts_the_compile_required(tmp_path: Path) -> None:
    """Where the authorisation trail lives, since it is not a provenance stage."""
    _, receipt, prepared = compiled(tmp_path)
    assert receipt.specimen_review_hash == prepared.specimen_review_hash
    assert receipt.separation_review_hash == prepared.separation_review_hash
    assert receipt.separation_manifest_hash == prepared.manifest_hash
