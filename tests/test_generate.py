"""Generation-stage tests: everything decided before a weight is loaded.

The expensive half of `spectral_loom.generate` cannot be tested here and is not
pretended to be — it needs eleven gigabytes and a GPU, and `decision:7` keeps
both out of the default suite. What *can* be tested here is everything that
decides whether the expensive half should run at all, and that is the half where
a mistake is silent: a specification pinned to a stale revision, a parameter the
generator does not take, a cache key that matches when it should not.

The manifest's truth-layer discipline is asserted here too, because "the prompt
is not an observation" is the project's founding rule and a rule that only a
document asserts is a hope.

Hermetic: no network, no weights, no torch. Manifests are synthesized.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from spectral_loom.cabinet import Cabinet, CabinetError, load_repository_cabinet
from spectral_loom.contracts import (
    GenerationManifest,
    Provenance,
    SongSpec,
    SourceAudio,
    TruthLayer,
)
from spectral_loom.generate import (
    ACE_STEP_DEFAULTS,
    GENERATE_STAGE,
    GenerationError,
    Plan,
    hash_bytes,
    hash_file,
    observe_wav,
    plan,
    resolve_parameters,
    reusable,
    runtime_identity,
    write_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "corpus" / "specs" / "example.yaml"


@pytest.fixture(scope="module")
def cabinet() -> Cabinet:
    return load_repository_cabinet(REPO_ROOT)


@pytest.fixture
def spec_bytes() -> bytes:
    return EXAMPLE.read_bytes()


@pytest.fixture
def spec(spec_bytes: bytes) -> SongSpec:
    return SongSpec.model_validate(yaml.safe_load(spec_bytes.decode("utf-8")))


@pytest.fixture
def planned(spec: SongSpec, spec_bytes: bytes, cabinet: Cabinet, tmp_path: Path) -> Plan:
    return plan(spec, EXAMPLE, spec_bytes, cabinet, tmp_path)


# ---------------------------------------------------------------------------
# Pinning is a precondition.
# ---------------------------------------------------------------------------


def test_the_committed_example_plans(planned: Plan) -> None:
    assert planned.specimen_id == "sparse-funk-exposed-bass"
    assert planned.entry_name == "ace-step"
    assert planned.audio_path.name == "source.wav"
    assert planned.manifest_path.name == "generation-manifest.json"
    assert "corpus/generated/sparse-funk-exposed-bass" in str(planned.output_dir)


def test_a_null_revision_refuses_and_says_what_is_pinned(
    spec: SongSpec, spec_bytes: bytes, cabinet: Cabinet, tmp_path: Path
) -> None:
    """The cheapest moment to refuse is before eleven gigabytes are loaded."""
    unpinned = spec.model_copy(
        update={"generator": spec.generator.model_copy(update={"revision": None})}
    )
    with pytest.raises(GenerationError) as caught:
        plan(unpinned, EXAMPLE, spec_bytes, cabinet, tmp_path)
    message = str(caught.value)
    assert "revision is null" in message
    assert cabinet.entry["ace-step"].assets[0].revision in message, "say what it should have been"


def test_a_stale_revision_refuses_rather_than_generating(
    spec: SongSpec, spec_bytes: bytes, cabinet: Cabinet, tmp_path: Path
) -> None:
    """A specification and a cabinet that disagree cannot both be right.

    Generating anyway would attribute the audio to a revision that did not make
    it, which is worse than not generating.
    """
    stale = spec.model_copy(
        update={"generator": spec.generator.model_copy(update={"revision": "0" * 40})}
    )
    with pytest.raises(GenerationError, match="stale"):
        plan(stale, EXAMPLE, spec_bytes, cabinet, tmp_path)


def test_a_mismatched_model_id_refuses(
    spec: SongSpec, spec_bytes: bytes, cabinet: Cabinet, tmp_path: Path
) -> None:
    wrong = spec.model_copy(
        update={"generator": spec.generator.model_copy(update={"model_id": "ACE-Step/Ace-Step1.5"})}
    )
    with pytest.raises(GenerationError, match="model_id"):
        plan(wrong, EXAMPLE, spec_bytes, cabinet, tmp_path)


def test_an_unknown_adapter_names_the_ones_that_exist(
    spec: SongSpec, spec_bytes: bytes, cabinet: Cabinet, tmp_path: Path
) -> None:
    other = spec.model_copy(
        update={"generator": spec.generator.model_copy(update={"adapter": "musicgen"})}
    )
    with pytest.raises(CabinetError, match="no cabinet entry provides adapter"):
        plan(other, EXAMPLE, spec_bytes, cabinet, tmp_path)


# ---------------------------------------------------------------------------
# Parameters are the request and the cache key at once.
# ---------------------------------------------------------------------------


def test_parameters_carry_everything_that_reaches_the_model(planned: Plan) -> None:
    parameters = planned.parameters
    assert parameters["num_inference_steps"] == 8
    assert parameters["shift"] == 3.0
    assert parameters["dtype"] == "bfloat16"
    assert parameters["seed"] == 20260820
    assert parameters["audio_duration"] == 45.0
    assert parameters["lyrics"] == "", "instrumental: no lyric conditioning"
    assert "funk" in str(parameters["prompt"])


def test_requested_metadata_is_passed_but_stays_named_as_requested(planned: Plan) -> None:
    """It conditions the model, so it is in the key. It is still a request.

    `requested_bpm: 96` in this dictionary says the model was told 96. It says
    nothing whatever about what came back, and the name is what keeps those two
    readings apart at every later point of use.
    """
    assert planned.parameters["requested_bpm"] == 96
    assert planned.parameters["requested_keyscale"] == "D minor"
    assert planned.parameters["requested_timesignature"] == "4", "numerator only, not '4/4'"
    assert "bpm" not in planned.parameters
    assert not any(
        key in planned.parameters for key in ("observed_bpm", "key", "keyscale", "instruments")
    )


def test_a_parameter_the_generator_does_not_take_is_an_error(
    spec: SongSpec, spec_bytes: bytes, cabinet: Cabinet, tmp_path: Path
) -> None:
    """The placeholders this specification used to carry, kept as a regression.

    `guidance_scale` is ignored by the guidance-distilled turbo weights, so
    accepting it would put a value in the cache key that changes nothing about
    the result — an invalidation that invalidates nothing.
    """
    stale_params = spec.model_copy(
        update={"generator_params": {"guidance_scale": 7.5, "scheduler": "euler"}}
    )
    with pytest.raises(GenerationError) as caught:
        plan(stale_params, EXAMPLE, spec_bytes, cabinet, tmp_path)
    assert "guidance_scale" in str(caught.value)
    assert "scheduler" in str(caught.value)


def test_a_specification_may_not_set_what_the_adapter_owns(
    spec: SongSpec, spec_bytes: bytes, cabinet: Cabinet, tmp_path: Path
) -> None:
    hijack = spec.model_copy(update={"generator_params": {"prompt": "something else"}})
    with pytest.raises(GenerationError, match="set by this adapter"):
        plan(hijack, EXAMPLE, spec_bytes, cabinet, tmp_path)


def test_defaults_are_restated_rather_than_inherited(spec: SongSpec, cabinet: Cabinet) -> None:
    """An upstream default that changes is a cache-invalidation event.

    If `num_inference_steps` were left to the pipeline's own default, an upstream
    change would silently alter every result while every cache key stayed
    identical. Restating it here is what makes such a change a diff.
    """
    bare = spec.model_copy(update={"generator_params": {}})
    parameters = resolve_parameters(bare, cabinet.entry["ace-step"])
    for key, value in ACE_STEP_DEFAULTS.items():
        assert parameters[key] == value


def test_the_tool_revision_names_code_and_weights_separately(planned: Plan) -> None:
    """Two identities, because upstream versions them separately."""
    assert "diffusers==0.40.0" in planned.tool_revision
    assert "ACE-Step/acestep-v15-xl-turbo-diffusers@" in planned.tool_revision
    assert planned.asset.revision in planned.tool_revision


# ---------------------------------------------------------------------------
# Reuse: the cache key is the provenance record.
# ---------------------------------------------------------------------------


def _synthesize(planned: Plan, wav: Path, **overrides: object) -> GenerationManifest:
    """A manifest describing `wav` as though this plan had produced it."""
    planned.output_dir.mkdir(parents=True, exist_ok=True)
    planned.audio_path.write_bytes(wav.read_bytes())
    stage = {
        "stage": GENERATE_STAGE,
        "tool": planned.tool,
        "tool_revision": planned.tool_revision,
        "truth_layer": TruthLayer.REQUESTED,
        "input_hashes": {"spec": planned.spec_hash},
        "parameters": planned.parameters,
        "output_hashes": {"source": hash_file(planned.audio_path)},
        "runtime": runtime_identity("mps"),
        "started_at": datetime.now(UTC),
        "duration_ms": 1234,
    }
    stage.update(overrides)
    manifest = GenerationManifest(
        specimen_id=planned.specimen_id,
        spec_path=str(planned.spec_path),
        spec_hash=planned.spec_hash,
        source_audio=observe_wav(planned.audio_path),
        provenance=[Provenance.model_validate(stage)],
    )
    write_manifest(planned.manifest_path, manifest)
    return manifest


def test_an_unchanged_request_reuses_the_existing_specimen(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    _synthesize(planned, tone_wav())
    assert reusable(planned) is not None


def test_nothing_to_reuse_before_anything_is_generated(planned: Plan) -> None:
    assert reusable(planned) is None


def test_a_changed_parameter_invalidates_the_reuse(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    _synthesize(planned, tone_wav(), parameters={**planned.parameters, "shift": 2.0})
    assert reusable(planned) is None


def test_a_changed_specification_invalidates_the_reuse(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    _synthesize(planned, tone_wav(), input_hashes={"spec": hash_bytes(b"a different request")})
    assert reusable(planned) is None


def test_a_changed_revision_invalidates_the_reuse(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    """Same prompt, same seed, different weights — a different result entirely."""
    _synthesize(planned, tone_wav(), tool_revision="diffusers==0.40.0 example/other@" + "b" * 40)
    assert reusable(planned) is None


def test_audio_that_changed_under_its_manifest_is_not_a_cache_hit(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    """A manifest describing a file that has since changed is not a cache entry.

    It is a document making a false claim, and reusing it would attach a
    truthful-looking provenance record to bytes that record never saw.
    """
    _synthesize(planned, tone_wav())
    planned.audio_path.write_bytes(tone_wav("other.wav", hz=880.0).read_bytes())
    assert reusable(planned) is None


def test_a_manifest_without_its_audio_is_not_a_cache_hit(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    _synthesize(planned, tone_wav())
    planned.audio_path.unlink()
    assert reusable(planned) is None


def test_a_corrupt_manifest_is_ignored_rather_than_fatal(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    """Regenerating is recoverable; crashing on a half-written file is not."""
    _synthesize(planned, tone_wav())
    planned.manifest_path.write_text("{not json", encoding="utf-8")
    assert reusable(planned) is None


# ---------------------------------------------------------------------------
# Observation, and the truth-layer rule.
# ---------------------------------------------------------------------------


def test_observations_come_from_the_file_not_from_the_request(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    """The requested duration is 45 s. The measured one is what gets recorded.

    A generator returning a different length than asked for is exactly the sort
    of thing this project exists to notice rather than assume away.
    """
    manifest = _synthesize(planned, tone_wav(seconds=0.25, hz=440.0))
    assert planned.parameters["audio_duration"] == 45.0
    assert manifest.source_audio.duration_s == pytest.approx(0.25)
    assert manifest.source_audio.sample_rate_hz == 8000
    assert manifest.source_audio.channels == 1
    assert manifest.source_audio.hash == hash_file(planned.audio_path)


def test_the_manifest_states_no_musical_fact_about_the_audio(
    planned: Plan, tone_wav: Callable[..., Path]
) -> None:
    """The founding rule, asserted against the serialized document.

    The prompt asks for 96 BPM, D minor, and an electric bass. None of that may
    appear anywhere in this manifest except inside a stage explicitly labelled
    `requested`, under a key that says so.
    """
    _synthesize(planned, tone_wav())
    document = json.loads(planned.manifest_path.read_text())

    assert document["source_audio"].keys() == {"hash", "duration_s", "sample_rate_hz", "channels"}

    stage = document["provenance"][0]
    assert stage["truth_layer"] == "requested"
    for key in stage["parameters"]:
        assert key not in {"bpm", "key", "keyscale", "time_signature", "instruments"}, (
            f"{key} reads as an observation about the audio"
        )

    without_requested_stage = {**document, "provenance": []}
    serialized = json.dumps(without_requested_stage)
    for leaked in ("96", "D minor", "electric bass"):
        assert leaked not in serialized, f"{leaked!r} escaped the requested layer"


def test_a_generation_manifest_forbids_unknown_fields(planned: Plan) -> None:
    document = {
        "schema_id": "spectral-loom/generation-manifest",
        "schema_version": "0.1.0",
        "specimen_id": planned.specimen_id,
        "spec_path": "x",
        "spec_hash": "sha256:" + "a" * 64,
        "source_audio": {"hash": "sha256:" + "b" * 64, "duration_s": 1.0},
        "provenance": [
            {
                "stage": GENERATE_STAGE,
                "tool": "t",
                "tool_revision": "r",
                "truth_layer": "requested",
            }
        ],
        "observed_bpm": 96,
    }
    with pytest.raises(ValueError, match="observed_bpm"):
        GenerationManifest.model_validate(document)


def test_an_empty_or_unreadable_wav_is_a_failure_not_a_zero_length_specimen(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "source.wav"
    broken.write_bytes(b"not a wav at all")
    with pytest.raises(GenerationError, match="not readable as a WAV"):
        observe_wav(broken)


def test_runtime_identity_names_the_backend() -> None:
    """A result that cannot name its backend cannot be compared with another run."""
    identity = runtime_identity("mps")
    assert identity.startswith("cpython3.11 ")
    assert identity.endswith(" mps")


def test_generation_refuses_when_the_weights_are_absent(planned: Plan) -> None:
    """`generate` never downloads. Weights are a precondition a human establishes."""
    from spectral_loom.generate import generate

    assert not planned.weights_dir.exists()
    with pytest.raises(GenerationError, match="bootstrap_cabinet"):
        generate(planned)


def test_a_source_audio_of_zero_duration_is_rejected(tmp_path: Path) -> None:
    """`SourceAudio.duration_s` is `gt=0`, so silence-of-no-length cannot be recorded."""
    with pytest.raises(ValueError):
        SourceAudio(hash="sha256:" + "c" * 64, duration_s=0.0)
