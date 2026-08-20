"""Turn a `SongSpec` into one generated audio file, and a record of how.

This is the first pipeline stage in the project and it is deliberately the
smallest one that could exist: read a specification, refuse if it is not pinned,
run one pinned model once, write the audio and a manifest beside it, stop. No
separation, no analysis, no timeline. Gate 2 of ``docs/roadmap.md`` ends with a
human listening, and nothing downstream of that is this module's business.

Three things it is careful about.

**Pinning is a precondition, not a warning.** A specification whose generator
revision is null, or whose revision is not the one the cabinet pins, does not
generate. There is no flag to override it. An unpinned generation produces audio
nobody can attribute to anything, and the cheapest moment to refuse is before
eleven gigabytes of weights are loaded.

**The manifest records observations and requests, never one dressed as the
other.** What the prompt asked for is in ``provenance[].parameters`` under a
stage labelled ``requested``. What the file turned out to contain — its hash,
duration, sample rate, channels — is in ``source_audio`` under ``observed``.
Whether the audio contains an electric bass is not knowable here and is not
claimed here. See ``archaeology/principles/0001``.

**An unchanged request does not buy another inference run.** The reuse rule is
the one ``docs/provenance.md`` already states: a stage's cache key is its input
hashes, its tool, its tool revision, and its parameters. If a manifest exists
whose generating stage matches all four *and* whose audio still hashes to what
that stage recorded, the run is skipped. That is a comparison of two provenance
records, not a cache framework.

The heavy imports live inside :func:`generate`. Everything above it — resolving
the cabinet entry, deciding the parameters, computing paths, judging whether a
previous result may be reused — is importable and testable in the default
environment, where torch is absent by design.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spectral_loom.cabinet import CABINET_FILENAME, Asset, Cabinet, Entry, asset_directory
from spectral_loom.contracts import (
    Extension,
    GenerationManifest,
    Provenance,
    SongSpec,
    SourceAudio,
    TruthLayer,
)

#: Generated audio lands here. Ignored by Git: it is bulky, and it is
#: regenerable from a pinned specification plus a pinned revision.
GENERATED_DIRNAME = "corpus/generated"

AUDIO_FILENAME = "source.wav"
MANIFEST_FILENAME = "generation-manifest.json"

#: The stage name in the manifest's provenance. Namespaced, like every stage.
GENERATE_STAGE = "generate"

_HASH_CHUNK = 1024 * 1024


class GenerationError(Exception):
    """Generation could not proceed, or produced something that failed its own checks."""


# ---------------------------------------------------------------------------
# Parameters: what is actually handed to the pinned interface.
# ---------------------------------------------------------------------------

#: Parameters this adapter sets itself, and which a specification may not
#: override, because they are not requests about the music — they are how this
#: project drives the pipeline.
RESERVED_PARAMS: frozenset[str] = frozenset(
    {
        "prompt",
        "lyrics",
        "audio_duration",
        "seed",
        "generator",
        "output_type",
        "return_dict",
        "bpm",
        "keyscale",
        "timesignature",
        "task_type",
    }
)

#: Parameters the pinned ACE-Step interface accepts and which materially change
#: the result. Anything outside this set in a specification is a typo or a
#: leftover from a different generator, and either way it is an error rather
#: than something silently dropped into a call it will not survive.
ACE_STEP_PARAMS: frozenset[str] = frozenset({"num_inference_steps", "shift", "dtype"})

#: The turbo checkpoint's own defaults, restated here because a default that
#: changes upstream is a cache-invalidation event and this is where it would be
#: noticed. `guidance_scale` is deliberately absent: the turbo weights are
#: guidance-distilled and the pipeline ignores it with a warning.
ACE_STEP_DEFAULTS: dict[str, Any] = {"num_inference_steps": 8, "shift": 3.0, "dtype": "bfloat16"}


# ---------------------------------------------------------------------------
# Reading back out of the parameter bag.
# ---------------------------------------------------------------------------
#
# `parameters` is JSON, because it is written to a manifest and read back from
# one months later. These narrow it at the point of use rather than trusting it,
# so a manifest hand-edited into nonsense fails here with the offending key
# rather than deep inside a pipeline call.


def _param_str(parameters: Extension, key: str) -> str:
    value = parameters[key]
    if not isinstance(value, str):
        raise GenerationError(f"parameter {key!r} must be a string, found {type(value).__name__}")
    return value


def _param_int(parameters: Extension, key: str) -> int:
    value = parameters[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise GenerationError(f"parameter {key!r} must be an integer, found {value!r}")
    return value


def _param_float(parameters: Extension, key: str) -> float:
    value = parameters[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise GenerationError(f"parameter {key!r} must be a number, found {value!r}")
    return float(value)


def _param_optional_int(parameters: Extension, key: str) -> int | None:
    return None if parameters.get(key) is None else _param_int(parameters, key)


def _param_optional_str(parameters: Extension, key: str) -> str | None:
    return None if parameters.get(key) is None else _param_str(parameters, key)


@dataclass(frozen=True)
class Plan:
    """Everything decided before a single weight is loaded.

    Separated from the run so that the decisions can be checked without a
    cabinet: which entry, which revision, which parameters, which paths, and
    whether an acceptable result already exists.
    """

    spec: SongSpec
    spec_path: Path
    spec_hash: str
    entry_name: str
    entry: Entry
    asset: Asset
    weights_dir: Path
    output_dir: Path
    audio_path: Path
    manifest_path: Path
    parameters: Extension
    tool: str
    tool_revision: str

    @property
    def specimen_id(self) -> str:
        return self.spec.specimen_id


def hash_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def resolve_parameters(spec: SongSpec, entry: Entry) -> Extension:
    """Decide the parameters this generation actually runs with.

    Everything that reaches the model and could change the result ends up here,
    because this dictionary is simultaneously the record of the request and the
    cache key — ``docs/provenance.md`` says those are the same information and
    this is where that stops being a slogan.

    The requested musical metadata is included: the pinned interface takes
    ``bpm``, ``keyscale``, and ``timesignature`` as conditioning, so they
    genuinely affect the output and genuinely belong in the key. They are still
    requests. Their presence here says the model was told 96; it says nothing
    about what came back.
    """
    if entry.adapter != "ace-step":
        raise GenerationError(
            f"no generation adapter for {entry.adapter!r}; this stage implements 'ace-step' only"
        )

    unknown = set(spec.generator_params) - ACE_STEP_PARAMS
    if unknown:
        reserved = sorted(unknown & RESERVED_PARAMS)
        detail = (
            f"{', '.join(reserved)} are set by this adapter and may not come from a specification"
            if reserved
            else f"the pinned interface accepts {', '.join(sorted(ACE_STEP_PARAMS))}"
        )
        raise GenerationError(
            f"specification sets generator_params this generator does not take: "
            f"{', '.join(sorted(unknown))}. {detail}"
        )

    parameters: Extension = dict(ACE_STEP_DEFAULTS)
    parameters.update(spec.generator_params)

    parameters["prompt"] = spec.requested_prompt
    parameters["lyrics"] = ""  # instrumental: no lyric conditioning at all
    parameters["audio_duration"] = spec.requested_duration_s
    parameters["seed"] = spec.seed
    parameters["task_type"] = "text2music"

    # Requested musical metadata, passed as conditioning in the interface's own
    # vocabulary. `timesignature` wants the numerator alone: "4", not "4/4".
    if spec.requested_bpm is not None:
        parameters["requested_bpm"] = round(spec.requested_bpm)
    if spec.requested_key is not None:
        parameters["requested_keyscale"] = spec.requested_key
    if spec.requested_time_signature is not None:
        parameters["requested_timesignature"] = spec.requested_time_signature.split("/")[0]
    return parameters


def plan(
    spec: SongSpec,
    spec_path: Path,
    spec_bytes: bytes,
    cabinet: Cabinet,
    repository_root: Path,
) -> Plan:
    """Resolve a specification against the cabinet, or refuse with the reason.

    Refuses before anything expensive happens, which is the whole point of doing
    it separately: a mismatch discovered after an eleven-gigabyte load is the
    same mismatch discovered for the price of reading two files.
    """
    entry_name, entry = cabinet.entry_for_adapter(spec.generator.adapter)

    if not entry.assets:
        raise GenerationError(
            f"cabinet entry {entry_name!r} has no weights to load; it cannot generate"
        )
    asset = entry.assets[0]

    if spec.generator.revision is None:
        raise GenerationError(
            f"{spec_path}: generator.revision is null, so this specimen cannot be generated "
            f"reproducibly. The cabinet pins {asset.repo_id} at {asset.revision}; set that "
            f"revision in the specification, or re-pin the cabinet, but do not generate "
            f"against whatever a branch points at today."
        )

    if spec.generator.revision != asset.revision:
        raise GenerationError(
            f"{spec_path}: generator.revision is {spec.generator.revision}, but "
            f"{CABINET_FILENAME} pins {entry_name} at {asset.revision}. One of the two is "
            f"stale; generating would produce audio attributed to a revision that did not "
            f"make it."
        )

    if spec.generator.model_id != asset.repo_id:
        raise GenerationError(
            f"{spec_path}: generator.model_id is {spec.generator.model_id!r}, but the cabinet "
            f"pins {asset.repo_id!r} for adapter {spec.generator.adapter!r}"
        )

    output_dir = repository_root / GENERATED_DIRNAME / spec.specimen_id
    return Plan(
        spec=spec,
        spec_path=spec_path,
        spec_hash=hash_bytes(spec_bytes),
        entry_name=entry_name,
        entry=entry,
        asset=asset,
        weights_dir=asset_directory(repository_root, entry_name, asset),
        output_dir=output_dir,
        audio_path=output_dir / AUDIO_FILENAME,
        manifest_path=output_dir / MANIFEST_FILENAME,
        parameters=resolve_parameters(spec, entry),
        tool=entry.code.symbol,
        tool_revision=(
            f"{entry.code.distribution}=={entry.code.version} {asset.repo_id}@{asset.revision}"
        ),
    )


# ---------------------------------------------------------------------------
# Reuse: an unchanged request does not buy another inference run.
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> GenerationManifest:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationError(f"cannot read {path}: {exc}") from exc
    return GenerationManifest.model_validate(document)


def reusable(plan: Plan) -> GenerationManifest | None:
    """An existing result for exactly this request, or None.

    Four things must agree — the specification's hash, the tool, the tool's
    revision, and the parameters — because those four are what
    ``docs/provenance.md`` defines the cache key to be. Then the audio itself is
    re-hashed against what that manifest recorded, because a manifest describing
    a file that has since changed is not a cache entry, it is a lie.
    """
    if not plan.manifest_path.is_file() or not plan.audio_path.is_file():
        return None
    try:
        existing = load_manifest(plan.manifest_path)
    except (GenerationError, ValueError):
        return None

    stage = next((p for p in existing.provenance if p.stage == GENERATE_STAGE), None)
    if stage is None:
        return None
    if stage.input_hashes.get("spec") != plan.spec_hash:
        return None
    if stage.tool != plan.tool or stage.tool_revision != plan.tool_revision:
        return None
    if stage.parameters != plan.parameters:
        return None
    if hash_file(plan.audio_path) != existing.source_audio.hash:
        return None
    return existing


# ---------------------------------------------------------------------------
# Observation: what the file actually turned out to be.
# ---------------------------------------------------------------------------


def observe_wav(path: Path) -> SourceAudio:
    """Measure a written WAV. Every field here is observed, none is requested.

    Duration comes from the frame count and the frame rate in the file's own
    header rather than from what was asked for, because the generator returning
    a different length than requested is exactly the kind of thing this project
    exists to notice rather than to assume away.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            channels = handle.getnchannels()
    except (OSError, wave.Error) as exc:
        raise GenerationError(f"{path} was written but is not readable as a WAV: {exc}") from exc

    if rate <= 0 or frames <= 0:
        raise GenerationError(f"{path} has {frames} frames at {rate} Hz; nothing was generated")

    return SourceAudio(
        hash=hash_file(path),
        duration_s=frames / rate,
        sample_rate_hz=rate,
        channels=channels,
    )


def runtime_identity(device: str) -> str:
    """The runtime string a provenance entry carries.

    It matters more than it looks: the same weights on MPS and on CPU can differ
    in the last bits, and a result that cannot name its backend cannot be
    compared with another run. ``docs/provenance.md`` says so; this is the value
    that makes it true.
    """
    version = ".".join(platform.python_version_tuple()[:2])
    machine = f"{platform.system().lower()}-{platform.machine()}"
    return f"cpython{version} {machine} {device}"


# ---------------------------------------------------------------------------
# The run.
# ---------------------------------------------------------------------------


def select_device() -> tuple[str, str | None]:
    """Choose a backend, and say plainly when the chosen one is not the fast one.

    Returns the device and, where the answer is not what the cabinet records, a
    sentence explaining what happened. A silent fall back to CPU is the failure
    this returns a second value to prevent.
    """
    import torch

    if torch.backends.mps.is_available():
        return "mps", None
    if not torch.backends.mps.is_built():
        return "cpu", "this torch was not built with MPS; generation will run on CPU"
    return "cpu", "MPS is built but unavailable on this host; generation will run on CPU"


def generate(plan: Plan, *, force: bool = False) -> tuple[GenerationManifest, bool]:
    """Run the pinned generator once. Returns the manifest and whether it is new.

    Everything torch-shaped is imported here so that the module above this point
    stays usable in the default environment.
    """
    if not force:
        existing = reusable(plan)
        if existing is not None:
            return existing, False

    if not plan.weights_dir.is_dir():
        raise GenerationError(
            f"weights for {plan.entry_name} are not on this machine: {plan.weights_dir} does not "
            f"exist. Run `scripts/bootstrap_cabinet.py assets` — generation does not download."
        )

    try:
        import soundfile
        import torch
        from diffusers import AceStepPipeline
    except ImportError as exc:
        raise GenerationError(
            f"the cabinet environment is not active: {exc}. Generation runs from "
            f"`.venv-cabinet`, e.g. `.venv-cabinet/bin/spectral-loom generate ...`."
        ) from exc

    device, warning = select_device()
    if warning:
        print(f"warning: {warning}", file=sys.stderr)

    dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[
        _param_str(plan.parameters, "dtype")
    ]

    started = datetime.now(UTC)
    clock = time.monotonic()

    pipeline = AceStepPipeline.from_pretrained(str(plan.weights_dir), dtype=dtype)
    pipeline = pipeline.to(device)

    # A CPU generator, seeded once. diffusers samples on the CPU and moves the
    # result, so the same seed gives the same noise regardless of the backend —
    # which is what makes the seed a reproducibility parameter rather than a
    # machine-specific one.
    torch_generator = torch.Generator("cpu").manual_seed(_param_int(plan.parameters, "seed"))

    audio = pipeline(
        prompt=_param_str(plan.parameters, "prompt"),
        lyrics=_param_str(plan.parameters, "lyrics"),
        audio_duration=_param_float(plan.parameters, "audio_duration"),
        num_inference_steps=_param_int(plan.parameters, "num_inference_steps"),
        shift=_param_float(plan.parameters, "shift"),
        task_type=_param_str(plan.parameters, "task_type"),
        # Requested conditioning, in the pinned interface's vocabulary.
        bpm=_param_optional_int(plan.parameters, "requested_bpm"),
        keyscale=_param_optional_str(plan.parameters, "requested_keyscale"),
        timesignature=_param_optional_str(plan.parameters, "requested_timesignature"),
        generator=torch_generator,
    ).audios

    plan.output_dir.mkdir(parents=True, exist_ok=True)
    waveform = audio[0].T.to(torch.float32).cpu().numpy()
    soundfile.write(str(plan.audio_path), waveform, int(pipeline.sample_rate), subtype="PCM_16")

    elapsed_ms = int((time.monotonic() - clock) * 1000)
    source_audio = observe_wav(plan.audio_path)

    manifest = GenerationManifest(
        specimen_id=plan.specimen_id,
        spec_path=str(plan.spec_path),
        spec_hash=plan.spec_hash,
        source_audio=source_audio,
        provenance=[
            Provenance(
                stage=GENERATE_STAGE,
                tool=plan.tool,
                tool_revision=plan.tool_revision,
                # The stage emits evidence rather than a claim about evidence,
                # and everything handed to it was asked for. Nothing in
                # `parameters` is a measurement.
                truth_layer=TruthLayer.REQUESTED,
                input_hashes={"spec": plan.spec_hash},
                parameters=plan.parameters,
                output_hashes={"source": source_audio.hash},
                runtime=runtime_identity(device),
                started_at=started,
                duration_ms=elapsed_ms,
            )
        ],
    )
    write_manifest(plan.manifest_path, manifest)
    return manifest, True


def write_manifest(path: Path, manifest: GenerationManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
