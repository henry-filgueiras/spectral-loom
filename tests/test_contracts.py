"""Contract tests.

These check the properties the contracts exist to enforce, not the plumbing of
pydantic: that requests stay labelled as requests, that an event cannot cite
evidence that is not in the document, and that a typo is an error rather than a
silently dropped field.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from spectral_loom.contracts import (
    SPEC_SCHEMA_VERSION,
    TIMELINE_SCHEMA_VERSION,
    Event,
    Evidence,
    Provenance,
    SongSpec,
    SongTimeline,
    SourceAudio,
    Track,
    TruthLayer,
)

VALID_SPEC: dict[str, Any] = {
    "specimen_id": "test-specimen",
    "generator": {"adapter": "ace-step", "model_id": "ACE-Step/ACE-Step-v1.5", "revision": None},
    "requested_prompt": "sparse funk with exposed bass",
    "seed": 7,
    "requested_duration_s": 45.0,
    "requested_bpm": 96.0,
    "requested_key": "D minor",
    "requested_time_signature": "4/4",
    "requested_instruments": ["electric bass", "drum kit"],
}


def hashed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def minimal_timeline() -> SongTimeline:
    """The smallest honest timeline: one stage, one track, one observation."""
    return SongTimeline(
        specimen_id="test-specimen",
        source_audio=SourceAudio(hash=hashed("audio"), duration_s=45.0, sample_rate_hz=44100),
        provenance=[
            Provenance(
                stage="activity",
                tool="spectral-loom-test",
                tool_revision="0.0.1+test",
                truth_layer=TruthLayer.INFERRED,
                input_hashes={"source": hashed("audio")},
                parameters={"window_s": 0.05},
                runtime="cpython3.11 macos-arm64",
                duration_ms=12,
            )
        ],
        tracks=[
            Track(
                id="bass",
                source="stems/bass.wav",
                role="bass",
                events=[
                    Event(
                        type="activity.interval",
                        start_s=1.5,
                        end_s=3.25,
                        confidence=0.82,
                        evidence=Evidence(artifact="stems/bass.wav", stage="activity"),
                        payload={"rms_db": -18.4},
                    )
                ],
            )
        ],
    )


# --- specification --------------------------------------------------------


def test_spec_stamps_its_own_schema_identity() -> None:
    spec = SongSpec.model_validate(VALID_SPEC)
    assert spec.schema_id == "spectral-loom/song-spec"
    assert spec.schema_version == SPEC_SCHEMA_VERSION


def test_every_musical_spec_field_is_labelled_as_requested() -> None:
    """Guards principle:1 at the schema level: no bare `bpm`, `key`, or `duration`."""
    musical = {"bpm", "key", "scale", "time_signature", "instruments", "duration_s", "tempo"}
    assert musical.isdisjoint(SongSpec.model_fields), (
        "a musical field on SongSpec must be named requested_*; an unlabelled name asserts "
        "an observation the specification cannot possibly have made"
    )


def test_an_unpinned_generator_revision_is_visible_not_silent() -> None:
    spec = SongSpec.model_validate(VALID_SPEC)
    assert spec.generator.revision is None
    assert spec.generator.is_pinned is False


def test_generator_params_are_contained_rather_than_flattened() -> None:
    spec = SongSpec.model_validate({**VALID_SPEC, "generator_params": {"guidance_scale": 7.5}})
    assert spec.generator_params == {"guidance_scale": 7.5}


def test_unknown_top_level_spec_field_is_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        SongSpec.model_validate({**VALID_SPEC, "observed_bpm": 92.0})
    assert "observed_bpm" in str(caught.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("specimen_id", "Not A Slug"),
        ("seed", -1),
        ("requested_duration_s", 0),
        ("requested_bpm", 0),
        ("requested_time_signature", "four-four"),
        ("requested_prompt", ""),
    ],
)
def test_spec_rejects_out_of_range_values(field: str, value: Any) -> None:
    with pytest.raises(ValidationError) as caught:
        SongSpec.model_validate({**VALID_SPEC, field: value})
    assert field in str(caught.value)


# --- timeline -------------------------------------------------------------


def test_minimal_timeline_round_trips() -> None:
    timeline = minimal_timeline()
    again = SongTimeline.model_validate(timeline.model_dump(mode="json"))
    assert again == timeline
    assert again.schema_version == TIMELINE_SCHEMA_VERSION
    assert again.time_unit == "seconds"


def test_event_cannot_cite_evidence_from_a_stage_that_is_not_recorded() -> None:
    document = minimal_timeline().model_dump(mode="json")
    document["tracks"][0]["events"][0]["evidence"]["stage"] = "separation"
    with pytest.raises(ValidationError) as caught:
        SongTimeline.model_validate(document)
    assert "not in this timeline's provenance" in str(caught.value)


def test_event_cannot_end_before_it_starts() -> None:
    with pytest.raises(ValidationError) as caught:
        Event(
            type="activity.interval",
            start_s=3.0,
            end_s=1.0,
            evidence=Evidence(artifact="mix", stage="activity"),
        )
    assert "ends before it starts" in str(caught.value)


def test_timeline_requires_at_least_one_provenance_stage() -> None:
    document = minimal_timeline().model_dump(mode="json")
    document["provenance"] = []
    with pytest.raises(ValidationError) as caught:
        SongTimeline.model_validate(document)
    assert "provenance" in str(caught.value)


def test_duplicate_stage_names_are_rejected() -> None:
    document = minimal_timeline().model_dump(mode="json")
    document["provenance"].append(dict(document["provenance"][0]))
    with pytest.raises(ValidationError) as caught:
        SongTimeline.model_validate(document)
    assert "duplicate provenance stage names" in str(caught.value)


def test_duplicate_track_ids_are_rejected() -> None:
    document = minimal_timeline().model_dump(mode="json")
    document["tracks"].append(dict(document["tracks"][0]))
    with pytest.raises(ValidationError) as caught:
        SongTimeline.model_validate(document)
    assert "duplicate track ids" in str(caught.value)


def test_source_audio_hash_must_be_algorithm_prefixed() -> None:
    document = minimal_timeline().model_dump(mode="json")
    document["source_audio"]["hash"] = "d41d8cd98f00b204e9800998ecf8427e"
    with pytest.raises(ValidationError) as caught:
        SongTimeline.model_validate(document)
    assert "hash" in str(caught.value)


def test_event_vocabulary_is_open() -> None:
    """A new observation kind is a new namespace, never a schema change."""
    for kind in ("activity.sample", "activity.interval", "onset", "note.midi", "beat.downbeat"):
        event = Event(
            type=kind,
            start_s=0.0,
            evidence=Evidence(artifact="mix", stage="activity"),
        )
        assert event.type == kind


def test_timeline_carries_no_rendering_instructions() -> None:
    """The boundary is musical observation. Anything drawable belongs downstream."""
    rendering = {"color", "colour", "shader", "geometry", "camera", "layer", "opacity", "focus"}
    for model in (SongTimeline, Track, Event, Evidence):
        assert rendering.isdisjoint(model.model_fields), f"{model.__name__} leaks a render field"


def test_timeline_rejects_a_rendering_field_smuggled_into_the_envelope() -> None:
    document = minimal_timeline().model_dump(mode="json")
    document["camera"] = {"fov": 60}
    with pytest.raises(ValidationError) as caught:
        SongTimeline.model_validate(document)
    assert "camera" in str(caught.value)


# --- fixtures that must stay temporary ------------------------------------


def test_synthesized_audio_stays_inside_the_temporary_directory(
    tone_wav: Callable[..., Path], tmp_path: Path
) -> None:
    """Audio-like input exists only for the life of the test."""
    path = tone_wav()
    assert path.exists()
    assert path.parent == tmp_path
    assert path.stat().st_size > 0
    assert hashed(path.read_bytes().hex()).startswith("sha256:")
