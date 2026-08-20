"""Separate one accepted specimen with the pinned Demucs, attributably.

The second pipeline stage, and the first one whose output another stage will
read as evidence. Everything about it is shaped by that: gates 4 and 5 will
compute activity, onsets and notes from these files, so a stem nobody can
attribute is an unattributable timeline six months from now.

Four things it is careful about.

**It runs only on bytes a human accepted.** Not on a specimen id, and not on a
directory name. `sparse-funk-exposed-bass` names an *intent* and survives
regeneration on purpose, so a matching path proves nothing about what is in it.
The source is hashed before a weight is loaded and matched against a tracked
`SpecimenReview`; a mismatch names both hashes and stops. See
``archaeology/decisions/0010``.

**It never resolves a moving revision.** ``demucs.pretrained.get_model`` calls
``hf_hub_download`` without a revision and therefore loads whatever ``main``
points at today. The pinned snapshot is loaded from disk instead, exactly as
``model-cabinet.toml`` records, and nothing here downloads anything.

**The backend is chosen, never fallen back to.** The same weights on MPS and on
CPU can differ in the last bits, so a result that cannot name its backend cannot
be compared with another run. An unavailable backend is a refusal. A CPU run is
an explicit flag that reaches the invocation, the provenance, the cache key and
the printed report — the one thing it may never be is quiet.

**A stem is named by the model that made it.** ``bass.wav`` means HTDemucs
assigned a signal to its ``bass`` output. It does not mean the file contains
only bass, and it does not mean the source contained a bass. This module writes
the files; it forms no opinion about whether the separation is any good, because
that is gate 3 and gate 3 is answered by ears.

Two parameters are worth their comment because they were chosen rather than
inherited. ``shifts`` stays at zero although upstream's own default is one:
``apply_model`` implements shifts by drawing a random offset from the unseeded
global RNG, which would make the stems unreproducible from the parameters this
manifest records. ``normalize`` reproduces what ``demucs.api.Separator`` does —
subtract the mean and divide by the standard deviation of the channel mean, then
undo it — because it materially changes the result and a parameter that is not
recorded is a cache key that cannot be recomputed.

As in :mod:`spectral_loom.generate`, the heavy imports live inside :func:`run`.
Everything above it is importable and testable in the default environment.
"""

from __future__ import annotations

import json
import math
import os
import platform
import shutil
import time
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from spectral_loom.cabinet import Asset, Cabinet, Entry, asset_directory
from spectral_loom.contracts import (
    AudioArtifact,
    Diagnostic,
    Extension,
    Provenance,
    SeparationManifest,
    Separator,
    SpecimenReview,
    Stem,
    TruthLayer,
)
from spectral_loom.generate import AUDIO_FILENAME, GENERATED_DIRNAME, MANIFEST_FILENAME
from spectral_loom.hashing import hash_bytes, hash_file
from spectral_loom.review import ReviewError, require_accepted

if TYPE_CHECKING:  # pragma: no cover - types only, and torch is not in this env
    import torch

#: Derived artifacts land here, one directory per specimen. Ignored by Git: a
#: stem is regenerable from accepted bytes plus a pinned revision.
DERIVED_DIRNAME = "corpus/derived"

SEPARATION_DIRNAME = "separation"
SEPARATION_MANIFEST_FILENAME = "separation-manifest.json"
DIAGNOSTICS_DIRNAME = "diagnostics"

#: The stage name in the manifest's provenance.
SEPARATE_STAGE = "separate"

#: What `apply_model` is actually called with, restated here rather than
#: inherited, so that an upstream default change becomes a diff and a cache
#: invalidation instead of a silent re-separation.
#:
#: `shifts` is the one that is not upstream's default, and the reason is
#: reproducibility rather than taste: shifts > 0 draws a random time offset from
#: the unseeded global RNG, so the same inputs and the same recorded parameters
#: would not produce the same stems twice.
DEMUCS_PARAMETERS: dict[str, Any] = {
    "shifts": 0,
    "split": True,
    "overlap": 0.25,
    "segment": None,
    "transition_power": 1.0,
    "normalize": True,
    "resample_to_model_rate": True,
    "output_subtype": "PCM_16",
}


class SeparationError(Exception):
    """Separation could not proceed, or produced something that failed its own checks."""


# ---------------------------------------------------------------------------
# The plan: everything decided before a weight is loaded.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeparationPlan:
    """A fully resolved request to separate one accepted specimen.

    Built without torch, so the refusals — unaccepted bytes, a missing cabinet,
    an unavailable backend, an existing directory this run must not overwrite —
    all happen for the price of reading a few files rather than after an
    eighty-megabyte model load and a minute of inference.
    """

    specimen_id: str
    review: SpecimenReview
    review_path: Path
    review_hash: str
    generation_manifest_hash: str

    source_path: Path
    source_hash: str

    entry_name: str
    entry: Entry
    asset: Asset
    weights_dir: Path
    bag_definition: Extension

    output_dir: Path
    manifest_path: Path
    device: str
    parameters: Extension
    cache_key_inputs: Extension
    cache_key: str

    repository_root: Path

    @property
    def model_signatures(self) -> list[str]:
        signatures = self.bag_definition["models"]
        assert isinstance(signatures, list)
        return [str(s) for s in signatures]

    @property
    def tool(self) -> str:
        return "demucs.apply.apply_model"

    @property
    def tool_revision(self) -> str:
        return (
            f"{self.entry.code.distribution}=={self.entry.code.version} "
            f"{self.asset.repo_id}@{self.asset.revision} "
            f"{self.asset.variant}/{'+'.join(self.model_signatures)}"
        )

    def relative(self, path: Path) -> str:
        """A path as the manifest records it: relative to the repository root."""
        return str(path.relative_to(self.repository_root))


def compute_cache_key(inputs: Extension) -> str:
    """The digest of a stage's key inputs, rendered deterministically.

    Sorted keys and no incidental whitespace, because the key has to be
    recomputable from the manifest that records it — a key that depends on dict
    ordering is a key that stops matching for no reason anybody can find.
    """
    return hash_bytes(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def read_bag_definition(weights_dir: Path, asset: Asset) -> Extension:
    """The pinned bag's own definition of itself, read from the weights.

    `htdemucs.yaml` in the weights repository names the models in the bag and,
    where a bag is more than one model, how they are weighted and segmented. All
    of it changes the result, so all of it is read here and all of it goes in
    the cache key — rather than only the part this particular bag happens to
    use, which would silently stop being enough for the next entry.
    """
    definition = weights_dir / f"{asset.variant}.yaml"
    try:
        raw = definition.read_text(encoding="utf-8")
    except OSError as exc:
        raise SeparationError(
            f"cannot read the bag definition at {definition}: {exc.strerror or exc}. The pinned "
            f"weights are incomplete; `scripts/bootstrap_cabinet.py assets` establishes them."
        ) from exc

    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SeparationError(f"{definition} is not valid YAML: {exc}") from exc
    if not isinstance(document, dict) or not document.get("models"):
        raise SeparationError(f"{definition} does not name any models: {raw!r}")
    return dict(document)


def plan(
    specimen_id: str,
    cabinet: Cabinet,
    repository_root: Path,
    *,
    device: str | None = None,
) -> SeparationPlan:
    """Resolve a separation request, or refuse with the reason.

    The order of the checks is the point. The acceptance is verified before the
    cabinet is consulted and the cabinet before the backend, so the failure a
    person sees is the first thing that was actually wrong rather than whichever
    one happened to be checked first.
    """
    entry_name, entry = cabinet.entry_for_adapter("demucs")
    if not entry.assets:
        raise SeparationError(
            f"cabinet entry {entry_name!r} has no weights to load; it cannot separate"
        )
    asset = entry.assets[0]

    generated = repository_root / GENERATED_DIRNAME / specimen_id
    source_path = generated / AUDIO_FILENAME
    generation_manifest = generated / MANIFEST_FILENAME
    if not source_path.is_file():
        raise SeparationError(
            f"no audio for specimen {specimen_id!r} at {source_path}. Separation reads a file "
            f"that already exists; it does not generate one."
        )

    source_hash = hash_file(source_path)
    try:
        review, review_path = require_accepted(repository_root, specimen_id, source_hash)
    except ReviewError as exc:
        raise SeparationError(str(exc)) from exc

    if not generation_manifest.is_file():
        raise SeparationError(
            f"no generation manifest at {generation_manifest}. The review attributes these "
            f"bytes, but the manifest they were attributed from is gone; regenerate or restore "
            f"it before separating."
        )

    weights_dir = asset_directory(repository_root, entry_name, asset)
    if not weights_dir.is_dir():
        raise SeparationError(
            f"weights for {entry_name} are not on this machine: {weights_dir} does not exist. "
            f"Run `scripts/bootstrap_cabinet.py assets` — separation does not download."
        )
    bag_definition = read_bag_definition(weights_dir, asset)

    chosen = device or cabinet.runtime.accelerator
    parameters: Extension = dict(DEMUCS_PARAMETERS)

    cache_key_inputs: Extension = {
        "source_hash": source_hash,
        "code": f"{entry.code.distribution}=={entry.code.version}",
        "code_sha256": entry.code.sha256,
        "loaded_with": entry.code.symbol,
        "applied_with": "demucs.apply.apply_model",
        "weights_repo": asset.repo_id,
        "weights_revision": asset.revision,
        "weights_variant": asset.variant,
        "bag_definition": bag_definition,
        # The backend is in the key because the same weights on MPS and on CPU
        # can differ in the last bits. A cache entry that ignored it would hand
        # a CPU result to a run that asked for MPS and call them the same thing.
        "device": chosen,
        "parameters": parameters,
    }

    output_dir = repository_root / DERIVED_DIRNAME / specimen_id / SEPARATION_DIRNAME
    return SeparationPlan(
        specimen_id=specimen_id,
        review=review,
        review_path=review_path,
        review_hash=hash_file(review_path),
        generation_manifest_hash=hash_file(generation_manifest),
        source_path=source_path,
        source_hash=source_hash,
        entry_name=entry_name,
        entry=entry,
        asset=asset,
        weights_dir=weights_dir,
        bag_definition=bag_definition,
        output_dir=output_dir,
        manifest_path=output_dir / SEPARATION_MANIFEST_FILENAME,
        device=chosen,
        parameters=parameters,
        cache_key_inputs=cache_key_inputs,
        cache_key=compute_cache_key(cache_key_inputs),
        repository_root=repository_root,
    )


# ---------------------------------------------------------------------------
# Reuse: separation is expensive enough to require a real cache check.
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> SeparationManifest:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeparationError(f"cannot read {path}: {exc}") from exc
    try:
        return SeparationManifest.model_validate(document)
    except ValidationError as exc:
        raise SeparationError(f"{path} is not a valid separation manifest: {exc}") from exc


def cache_miss_reason(plan: SeparationPlan, manifest: SeparationManifest) -> str | None:
    """Why an existing manifest may not be reused, or None if it may be.

    Split out from :func:`reusable` and returning prose rather than a boolean,
    because ``docs/provenance.md`` says a run that should have hit cache and did
    not is a bug report. A silent miss is the cheapest possible way to hide an
    unstable key, so the reason is always available to be printed.

    Four independent things are checked, and a partial or corrupted prior run
    fails on the last two rather than being mistaken for a hit.
    """
    if manifest.cache_key != plan.cache_key:
        return (
            f"cache key differs: recorded {manifest.cache_key}, computed {plan.cache_key}. "
            f"Something in the source, the code, the weights, the parameters or the backend "
            f"is not what it was."
        )
    if manifest.source_audio.hash != plan.source_hash:
        return (
            f"the manifest describes source {manifest.source_audio.hash}, and the audio on "
            f"disk hashes to {plan.source_hash}"
        )

    declared = [s.audio for s in manifest.stems] + [
        d.audio for d in manifest.diagnostics if d.audio is not None
    ]
    for artifact in declared:
        target = plan.repository_root / artifact.path
        if not target.is_file():
            return f"a declared output is missing: {artifact.path}"
        if hash_file(target) != artifact.hash:
            return (
                f"{artifact.path} no longer hashes to what the manifest recorded; a manifest "
                f"describing a file that has since changed is not a cache entry"
            )

    outputs = {s.model_output for s in manifest.stems}
    if outputs != set(manifest.separator.sources):
        return (
            f"the manifest declares stems {sorted(outputs)} but its separator emits "
            f"{sorted(manifest.separator.sources)}; the record is internally inconsistent"
        )
    rates = {s.audio.sample_rate_hz for s in manifest.stems}
    if len(rates) != 1:
        return f"stems disagree about their sample rate: {sorted(rates)}"
    return None


def reusable(plan: SeparationPlan) -> SeparationManifest | None:
    """A complete, verified previous result for exactly this request, or None."""
    if not plan.manifest_path.is_file():
        return None
    try:
        existing = load_manifest(plan.manifest_path)
    except SeparationError:
        return None
    return None if cache_miss_reason(plan, existing) else existing


# ---------------------------------------------------------------------------
# Where an interrupted or superseded run goes.
# ---------------------------------------------------------------------------


def workspace(plan: SeparationPlan) -> Path:
    """A private directory to build the result in, beside where it will land.

    Beside, so that promotion is a rename on one filesystem rather than a copy.
    Per-process, so two concurrent runs cannot scribble on each other.
    """
    return plan.output_dir.with_name(f".{SEPARATION_DIRNAME}.partial.{os.getpid()}")


def superseded_path(output_dir: Path) -> Path:
    """The next unused name to move an existing result aside to.

    Moved rather than deleted. Bytes this project did not expect are evidence
    about something — an interrupted run, a different revision, a hand edit —
    and destroying them to make the current run succeed would be exactly the
    failure ``scripts/bootstrap_cabinet.py`` already refuses.
    """
    index = 0
    while True:
        candidate = output_dir.with_name(f"{output_dir.name}.superseded.{index}")
        if not candidate.exists():
            return candidate
        index += 1


def promote(plan: SeparationPlan, built: Path) -> Path | None:
    """Move a finished workspace into place, preserving anything already there.

    Returns where an existing result was moved to, or None if there was none.
    """
    preserved: Path | None = None
    if plan.output_dir.exists():
        preserved = superseded_path(plan.output_dir)
        os.replace(plan.output_dir, preserved)
    plan.output_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(built, plan.output_dir)
    return preserved


# ---------------------------------------------------------------------------
# Observation.
# ---------------------------------------------------------------------------


def runtime_identity(device: str) -> str:
    """The runtime string a provenance entry carries, including the backend."""
    version = ".".join(platform.python_version_tuple()[:2])
    machine = f"{platform.system().lower()}-{platform.machine()}"
    return f"cpython{version} {machine} {device}"


def rms_of(values: torch.Tensor) -> float:
    return float(values.to("cpu").double().pow(2).mean().sqrt())


def db_ratio(numerator: float, denominator: float) -> float | None:
    """Level of one signal relative to another, in dB, or None where undefined."""
    if numerator <= 0 or denominator <= 0:
        return None
    return round(20 * math.log10(numerator / denominator), 3)


# ---------------------------------------------------------------------------
# The run.
# ---------------------------------------------------------------------------


def resolve_device(requested: str) -> str:
    """Confirm the requested backend can actually execute, or refuse.

    **There is no fall back.** A run that quietly moved to CPU would produce
    perfectly good-looking stems that nothing later could compare against an MPS
    run, and the cache key would claim a backend that did not execute. Asking
    for CPU is legitimate and explicit; ending up on it is not.
    """
    import torch

    if requested == "cpu":
        return "cpu"
    if requested == "mps":
        if torch.backends.mps.is_available():
            return "mps"
        built = torch.backends.mps.is_built()
        detail = "built but unavailable on this host" if built else "not built into this torch"
        raise SeparationError(
            f"MPS is {detail}. "
            f"This stage does not fall back: the same weights on another backend are another "
            f"result, and a silent fall back would put a backend in the cache key that never "
            f"ran. Pass `--device cpu` to run on CPU deliberately."
        )
    if requested == "cuda":
        if torch.cuda.is_available():
            return "cuda"
        raise SeparationError(
            "CUDA is not available on this host, and this stage does not fall back."
        )
    raise SeparationError(f"unknown device {requested!r}; expected one of mps, cpu, cuda")


def run(plan: SeparationPlan, *, force: bool = False) -> tuple[SeparationManifest, bool]:
    """Separate the accepted specimen once. Returns the manifest and whether it is new.

    Everything torch-shaped is imported here so that the module above this point
    stays usable in the default environment, where the cabinet is absent by
    design.
    """
    if not force:
        existing = reusable(plan)
        if existing is not None:
            return existing, False

    if plan.output_dir.exists() and not force:
        reason = "it is not a directory"
        if plan.manifest_path.is_file():
            try:
                reason = cache_miss_reason(plan, load_manifest(plan.manifest_path)) or "unknown"
            except SeparationError as exc:
                reason = str(exc)
        else:
            reason = f"there is no {SEPARATION_MANIFEST_FILENAME} in it"
        raise SeparationError(
            f"{plan.output_dir} already exists and is not a result for this request: {reason}\n"
            f"Those bytes are not overwritten. Inspect them, move them, or pass --force, which "
            f"moves them aside rather than deleting them."
        )

    try:
        import soundfile
        import torch
        from demucs.apply import BagOfModels, apply_model
        from demucs.audio import convert_audio
        from demucs.hf import load_safetensors_model
    except ImportError as exc:
        raise SeparationError(
            f"the cabinet environment is not active: {exc}. Separation runs from "
            f"`.venv-cabinet`, e.g. `.venv-cabinet/bin/spectral-loom separate ...`."
        ) from exc

    device = resolve_device(plan.device)
    warned: list[str] = []
    if device == "cpu":
        warned.append(
            "ran on CPU by explicit request; this result is not comparable bit-for-bit with an "
            "MPS run of the same inputs"
        )

    started = datetime.now(UTC)
    clock = time.monotonic()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        load_started = time.monotonic()
        models = [
            load_safetensors_model(plan.weights_dir / f"{signature}.safetensors")
            for signature in plan.model_signatures
        ]
        bag = BagOfModels(
            models,
            plan.bag_definition.get("weights"),
            plan.bag_definition.get("segment"),
        )
        bag.eval()
        load_seconds = time.monotonic() - load_started

        # Read the accepted bytes, and convert them the way the pinned code
        # does: `demucs.api.Separator` resamples to the model's rate and matches
        # its channel count before anything else happens, and doing it any other
        # way would make this a different stage than the one being pinned.
        samples, source_rate = soundfile.read(
            str(plan.source_path), dtype="float32", always_2d=True
        )
        mix = torch.from_numpy(samples).T.contiguous()
        if source_rate != bag.samplerate or mix.shape[0] != bag.audio_channels:
            mix = convert_audio(mix, source_rate, bag.samplerate, bag.audio_channels)

        reference = mix.mean(0)
        mean = reference.mean()
        deviation = reference.std() + 1e-8

        inference_started = time.monotonic()
        with torch.no_grad():
            estimates = apply_model(
                bag,
                ((mix - mean) / deviation)[None],
                device=device,
                shifts=int(plan.parameters["shifts"]),  # type: ignore[arg-type]
                split=bool(plan.parameters["split"]),
                overlap=float(plan.parameters["overlap"]),  # type: ignore[arg-type]
                transition_power=float(plan.parameters["transition_power"]),  # type: ignore[arg-type]
                segment=plan.parameters["segment"],
                progress=False,
            )
        inference_seconds = time.monotonic() - inference_started
        estimates = estimates[0] * deviation + mean

    warned.extend(sorted({f"{w.category.__name__}: {w.message}" for w in caught})[:20])

    built = workspace(plan)
    if built.exists():
        shutil.rmtree(built)
    (built / DIAGNOSTICS_DIRNAME).mkdir(parents=True)

    try:
        stems, stem_audio = _write_stems(plan, built, bag.sources, estimates, bag.samplerate)
        diagnostics = _write_diagnostics(
            plan, built, mix, stem_audio, bag.samplerate, inference_seconds
        )
        for stem in stems:
            if stem.clipped_samples:
                warned.append(
                    f"{stem.model_output}: {stem.clipped_samples} sample(s) exceeded full scale "
                    f"and were clamped on write"
                )
            if stem.non_finite_samples:
                warned.append(
                    f"{stem.model_output}: {stem.non_finite_samples} non-finite sample(s) came "
                    f"out of the model and were written as zero"
                )

        elapsed_ms = int((time.monotonic() - clock) * 1000)
        manifest = SeparationManifest(
            specimen_id=plan.specimen_id,
            source_audio=plan.review.source_audio,
            source_path=plan.relative(plan.source_path),
            review_hash=plan.review_hash,
            generation_manifest_hash=plan.generation_manifest_hash,
            separator=Separator(
                adapter=plan.entry.adapter,
                code_distribution=plan.entry.code.distribution,
                code_version=plan.entry.code.version,
                code_sha256=plan.entry.code.sha256,
                loaded_with=plan.entry.code.symbol,
                applied_with="demucs.apply.apply_model",
                weights_repo=plan.asset.repo_id,
                weights_revision=plan.asset.revision,
                weights_variant=plan.asset.variant,
                model_signatures=plan.model_signatures,
                model_sample_rate_hz=int(bag.samplerate),
                model_audio_channels=int(bag.audio_channels),
                sources=list(bag.sources),
            ),
            stems=stems,
            diagnostics=diagnostics,
            cache_key=plan.cache_key,
            cache_key_inputs=plan.cache_key_inputs,
            warnings=warned,
            provenance=[
                Provenance(
                    stage=SEPARATE_STAGE,
                    tool=plan.tool,
                    tool_revision=plan.tool_revision,
                    # A named model's opinion about which signal belongs to
                    # which of its own outputs. Not an observation of the audio.
                    truth_layer=TruthLayer.INFERRED,
                    input_hashes={
                        "source": plan.source_hash,
                        "review": plan.review_hash,
                    },
                    parameters={
                        **plan.parameters,
                        "device": device,
                        "model_sample_rate_hz": int(bag.samplerate),
                        "source_sample_rate_hz": int(source_rate),
                        "load_seconds": round(load_seconds, 3),
                        "inference_seconds": round(inference_seconds, 3),
                    },
                    output_hashes={s.model_output: s.audio.hash for s in stems},
                    runtime=runtime_identity(device),
                    started_at=started,
                    duration_ms=elapsed_ms,
                )
            ],
        )
        write_manifest(built / SEPARATION_MANIFEST_FILENAME, manifest)
    except Exception:
        shutil.rmtree(built, ignore_errors=True)
        raise

    promote(plan, built)
    return manifest, True


def _write_stems(
    plan: SeparationPlan,
    built: Path,
    sources: list[str],
    estimates: torch.Tensor,
    rate: int,
) -> tuple[list[Stem], dict[str, torch.Tensor]]:
    """Write one file per model output, then measure the files that were written.

    Non-finite samples are zeroed and counted rather than allowed through: a NaN
    reaching a WAV writer produces bytes nobody can interpret, and a count is a
    fact worth carrying. Clipping is clamped and counted for the same reason it
    is not rescaled — a silent gain change would corrupt every later comparison
    against the source.
    """
    import soundfile
    import torch

    written: list[Stem] = []
    read_back: dict[str, torch.Tensor] = {}
    for index, name in enumerate(sources):
        signal = estimates[index].to("cpu").float()
        finite = torch.isfinite(signal)
        non_finite = int((~finite).sum())
        if non_finite:
            signal = torch.where(finite, signal, torch.zeros_like(signal))
        clipped = int((signal.abs() > 1.0).sum())
        signal = signal.clamp(-1.0, 1.0)

        path = built / f"{name}.wav"
        soundfile.write(str(path), signal.T.numpy(), int(rate), subtype="PCM_16")
        artifact, samples = _observe(plan, path, built)
        read_back[name] = samples
        written.append(
            Stem(
                model_output=name,
                audio=artifact,
                clipped_samples=clipped,
                non_finite_samples=non_finite,
            )
        )
    return written, read_back


def _write_diagnostics(
    plan: SeparationPlan,
    built: Path,
    mix: torch.Tensor,
    stems: dict[str, torch.Tensor],
    rate: int,
    inference_seconds: float,
) -> list[Diagnostic]:
    """Sum the stems, subtract them from the source, and measure the difference.

    Deliberately computed from the files that were just written rather than from
    the tensors that produced them, so the numbers describe what a person will
    actually hear and what a later stage will actually read.

    **No threshold is invented here.** Demucs is not trained to reconstruct
    additively and the write quantized to sixteen bits, so some residual is
    expected and none of it has a known pass mark. The residual is rendered so
    it can be listened to, measured so it can be compared with the next run, and
    left uninterpreted.
    """
    import soundfile
    import torch

    stacked = torch.stack(list(stems.values()))
    reconstruction = stacked.sum(dim=0)

    # The source at the rate the model actually saw. Comparing against the
    # original 48 kHz bytes would measure the resampler as well as the model.
    reference = mix[:, : reconstruction.shape[1]]
    reconstruction = reconstruction[:, : reference.shape[1]]
    residual = reference - reconstruction

    diagnostics: list[Diagnostic] = []
    paths = {
        "reconstruction": (
            reconstruction,
            "The four model outputs summed. An engineering diagnostic, not a stem: no model "
            "assigned anything to it.",
        ),
        "residual": (
            residual,
            "The source at the model's sample rate, minus the summed outputs. What separation "
            "did not account for. An engineering diagnostic, not a stem.",
        ),
    }
    rendered: dict[str, AudioArtifact] = {}
    for name, (signal, _) in paths.items():
        clamped = signal.clamp(-1.0, 1.0)
        path = built / DIAGNOSTICS_DIRNAME / f"{name}.wav"
        soundfile.write(str(path), clamped.T.numpy(), int(rate), subtype="PCM_16")
        rendered[name], _ = _observe(plan, path, built)

    source_rms = rms_of(reference)
    residual_rms = rms_of(residual)
    lag = _best_lag(reference, reconstruction)

    diagnostics.append(
        Diagnostic(
            id="reconstruction",
            description=paths["reconstruction"][1],
            audio=rendered["reconstruction"],
            measurements={
                "source_rms_at_model_rate": round(source_rms, 6),
                "reconstruction_rms": round(rms_of(reconstruction), 6),
                "peak_alignment_lag_samples": lag,
                "peak_alignment_lag_ms": round(1000 * lag / rate, 3),
                "note": (
                    "A lag of 0 means the summed outputs line up sample-for-sample with the "
                    "source; anything else is an unexplained temporal offset."
                ),
            },
        )
    )
    diagnostics.append(
        Diagnostic(
            id="residual",
            description=paths["residual"][1],
            audio=rendered["residual"],
            measurements={
                "residual_rms": round(residual_rms, 6),
                "residual_peak": round(float(residual.abs().max()), 6),
                "residual_relative_db": db_ratio(residual_rms, source_rms),
                "note": (
                    "Demucs is not trained to reconstruct additively and the outputs were "
                    "written as 16-bit PCM, so a nonzero residual is expected. This project "
                    "has no evidence for a pass threshold and does not assert one."
                ),
            },
        )
    )
    diagnostics.append(
        Diagnostic(
            id="stem-levels",
            description=(
                "Per-output level, to notice a stem that came back empty. An empty stem is a "
                "failure to assign, never evidence that the source lacked that instrument."
            ),
            measurements={
                name: {"rms": round(rms_of(signal), 6), "peak": round(float(signal.abs().max()), 6)}
                for name, signal in stems.items()
            },
        )
    )
    diagnostics.append(
        Diagnostic(
            id="timing",
            description="How long the run took, split into loading and inference.",
            measurements={"inference_seconds": round(inference_seconds, 3)},
        )
    )
    return diagnostics


def _best_lag(reference: torch.Tensor, other: torch.Tensor, limit: int = 4410) -> int:
    """The offset, in samples, at which two signals correlate best.

    Bounded to a tenth of a second and computed on the channel mean, because the
    question being asked is "did anything shift", not "by how much could it
    conceivably have shifted".
    """
    import torch

    a = reference.mean(0).double()
    b = other.mean(0).double()
    length = min(a.numel(), b.numel())
    a, b = a[:length], b[:length]
    if length == 0 or not torch.isfinite(a).all() or not torch.isfinite(b).all():
        return 0

    size = 1
    while size < 2 * length:
        size *= 2
    spectrum = torch.fft.rfft(a, size) * torch.fft.rfft(b, size).conj()
    correlation = torch.fft.irfft(spectrum, size)
    window = torch.cat((correlation[-limit:], correlation[: limit + 1]))
    return int(torch.argmax(window)) - limit


def _observe(plan: SeparationPlan, path: Path, built: Path) -> tuple[AudioArtifact, torch.Tensor]:
    """Measure a file that was just written, and hand back its samples.

    The recorded path is where the artifact will live *after promotion*, not
    where it currently sits in the workspace: a manifest naming a temporary
    directory would be wrong the moment it became correct.
    """
    import soundfile
    import torch

    samples, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    signal = torch.from_numpy(samples).T.contiguous()
    frames = signal.shape[1]
    if frames == 0 or rate <= 0:
        raise SeparationError(f"{path} was written but contains {frames} frames at {rate} Hz")

    final = plan.output_dir / path.relative_to(built)
    return (
        AudioArtifact(
            path=plan.relative(final),
            hash=hash_file(path),
            duration_s=frames / rate,
            sample_rate_hz=int(rate),
            channels=int(signal.shape[0]),
            peak=round(float(signal.abs().max()), 6),
            rms=round(rms_of(signal), 6),
        ),
        signal,
    )


def write_manifest(path: Path, manifest: SeparationManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
