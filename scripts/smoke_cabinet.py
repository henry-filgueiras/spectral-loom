#!/usr/bin/env python3
"""Run each pinned cabinet entry once, and report what actually happened.

    .venv-cabinet/bin/python scripts/smoke_cabinet.py [entry ...] [--json]

A smoke supports exactly one claim: **this pinned thing executes on this machine,
in this environment, on this backend.** It is what gate 1 of `docs/roadmap.md`
means by "installed and run once", and it is not evidence about quality. Whether
a separation is clean is gate 3, judged by listening to the stems. Whether notes
are right is gate 5. Mistaking a green smoke for either of those is the mistake
this paragraph exists to prevent.

The facts worth capturing are the ones that are invisible afterwards: which
device was actually selected, which serialization of a model was actually loaded,
and which warnings change what a result means. A backend that silently falls back
to CPU produces a perfectly good-looking output, and nothing later in the
pipeline would notice.

Inputs are synthesized here, into a temporary directory the operating system
reclaims. Nothing audio-shaped enters the tree.

Human-invoked. Never a test, never CI: it needs the weights, and the hermetic
suite has none. See `README.md` in this directory and
`archaeology/decisions/0007`.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import struct
import sys
import tempfile
import time
import warnings
import wave
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from spectral_loom.cabinet import (  # noqa: E402
    Cabinet,
    CabinetError,
    asset_directory,
    find_repository_root,
    load_repository_cabinet,
)

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_UNREADABLE = 3

#: Short enough that a failure is cheap and long enough to be real inference.
SMOKE_SECONDS = 2.0
SMOKE_RATE = 44100

#: The shortest generation the pinned checkpoint is documented to support. A
#: smoke should not cost what the specimen costs.
ACE_STEP_SMOKE_SECONDS = 10.0


def _tone(path: Path, seconds: float = SMOKE_SECONDS, rate: int = SMOKE_RATE) -> Path:
    """A two-channel chord with a beat under it, written into a temporary file.

    Deliberately not silence and not white noise: a separator handed silence can
    return silence and look like it worked. Two pitched voices plus a periodic
    transient is the cheapest input that makes a real separator do real work.
    """
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        samples = bytearray()
        for n in range(frames):
            t = n / rate
            bass = 0.45 * math.sin(2 * math.pi * 82.4 * t)
            lead = 0.25 * math.sin(2 * math.pi * 440.0 * t)
            click = 0.30 if (n % (rate // 2)) < 200 else 0.0
            left = max(-1.0, min(1.0, bass + click))
            right = max(-1.0, min(1.0, lead + click))
            samples += struct.pack("<hh", int(left * 30000), int(right * 30000))
        handle.writeframes(bytes(samples))
    return path


def _runtime() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": f"{platform.system().lower()}-{platform.machine()}",
        "macos": platform.mac_ver()[0] or None,
    }


def _torch_devices() -> dict[str, Any]:
    import torch

    return {
        "torch": torch.__version__,
        "mps_available": bool(torch.backends.mps.is_available()),
        "mps_built": bool(torch.backends.mps.is_built()),
        "cuda_available": bool(torch.cuda.is_available()),
    }


# ---------------------------------------------------------------------------
# Basic Pitch
# ---------------------------------------------------------------------------


def smoke_basic_pitch(root: Path, cabinet: Cabinet, workdir: Path) -> dict[str, Any]:
    """Run note inference on a synthesized chord.

    The backend is the interesting fact. `basic_pitch` chooses a serialization at
    import time from whichever runtime is importable, so what executes is a
    property of the resolved environment rather than of anything this project
    asked for — and the selected serialization is part of what produced any note.
    """
    import basic_pitch
    from basic_pitch.inference import predict

    audio = _tone(workdir / "basic-pitch-input.wav")
    started = time.monotonic()
    _model_output, midi, note_events = predict(str(audio))
    elapsed = time.monotonic() - started

    return {
        "executed": True,
        "backend": Path(str(basic_pitch.ICASSP_2022_MODEL_PATH)).name,
        "weights_path": str(basic_pitch.ICASSP_2022_MODEL_PATH),
        "coremltools_present": basic_pitch.CT_PRESENT,
        "tensorflow_present": basic_pitch.TF_PRESENT,
        "onnx_present": basic_pitch.ONNX_PRESENT,
        "tflite_present": basic_pitch.TFLITE_PRESENT,
        "note_events": len(note_events),
        "midi_instruments": len(midi.instruments),
        "first_note": (
            {
                "start_s": round(note_events[0][0], 3),
                "end_s": round(note_events[0][1], 3),
                "midi_pitch": note_events[0][2],
                "amplitude": round(float(note_events[0][3]), 4),
            }
            if note_events
            else None
        ),
        "seconds": round(elapsed, 2),
        "input_seconds": SMOKE_SECONDS,
    }


# ---------------------------------------------------------------------------
# Demucs
# ---------------------------------------------------------------------------


def smoke_demucs(root: Path, cabinet: Cabinet, workdir: Path) -> dict[str, Any]:
    """Separate a synthesized chord with the pinned HTDemucs snapshot.

    Loaded from the pinned directory rather than through
    `demucs.pretrained.get_model`, which calls `hf_hub_download` with no revision
    and therefore resolves whatever `main` points at today. Using it would make
    this smoke a statement about a moving target.
    """
    import torch
    import yaml
    from demucs.apply import BagOfModels, apply_model
    from demucs.hf import load_safetensors_model

    entry = cabinet.require("demucs")
    asset = entry.assets[0]
    weights = asset_directory(root, "demucs", asset)
    bag_definition = yaml.safe_load((weights / f"{asset.variant}.yaml").read_text())
    signatures = bag_definition["models"]

    started = time.monotonic()
    models = [load_safetensors_model(weights / f"{sig}.safetensors") for sig in signatures]
    bag = BagOfModels(models, bag_definition.get("weights"), bag_definition.get("segment"))
    bag.eval()
    loaded = time.monotonic() - started

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    audio = _tone(workdir / "demucs-input.wav", rate=bag.samplerate)
    with wave.open(str(audio), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    samples = torch.frombuffer(bytearray(raw), dtype=torch.int16).float() / 32768.0
    mix = samples.view(-1, 2).T.contiguous()

    started = time.monotonic()
    with torch.no_grad():
        stems = apply_model(bag, mix[None], device=device, split=True, progress=False)
    elapsed = time.monotonic() - started

    return {
        "executed": True,
        "signatures": signatures,
        "weights_dir": str(weights),
        "device_requested": device,
        "sources": list(bag.sources),
        "model_samplerate": bag.samplerate,
        "input_shape": list(mix.shape),
        "output_shape": list(stems.shape),
        "output_dtype": str(stems.dtype),
        "output_is_finite": bool(torch.isfinite(stems).all()),
        "per_source_rms": {
            source: round(float(stems[0, index].pow(2).mean().sqrt()), 6)
            for index, source in enumerate(bag.sources)
        },
        "load_seconds": round(loaded, 2),
        "seconds": round(elapsed, 2),
        "input_seconds": SMOKE_SECONDS,
    }


# ---------------------------------------------------------------------------
# ACE-Step
# ---------------------------------------------------------------------------


def smoke_ace_step(root: Path, cabinet: Cabinet, workdir: Path) -> dict[str, Any]:
    """Generate ten seconds with the pinned turbo checkpoint.

    The shortest documented generation, because a smoke should not cost what the
    specimen costs. Whether the result is any good is not a question a smoke may
    answer, and this one does not listen to it.
    """
    import torch
    from diffusers import AceStepPipeline

    entry = cabinet.require("ace-step")
    asset = entry.assets[0]
    weights = asset_directory(root, "ace-step", asset)
    device = "mps" if torch.backends.mps.is_available() else "cpu"

    started = time.monotonic()
    pipeline = AceStepPipeline.from_pretrained(str(weights), dtype=torch.bfloat16)
    pipeline = pipeline.to(device)
    loaded = time.monotonic() - started

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        started = time.monotonic()
        audio = pipeline(
            prompt="solo acoustic double bass, one slow phrase, nothing else",
            lyrics="",
            audio_duration=ACE_STEP_SMOKE_SECONDS,
            num_inference_steps=8,
            shift=3.0,
            generator=torch.Generator("cpu").manual_seed(0),
        ).audios
        elapsed = time.monotonic() - started

    waveform = audio[0]
    return {
        "executed": True,
        "weights_dir": str(weights),
        "device_requested": device,
        "device_used": str(pipeline.transformer.device),
        "dtype": str(pipeline.transformer.dtype),
        "sample_rate": int(pipeline.sample_rate),
        "output_shape": list(waveform.shape),
        "output_dtype": str(waveform.dtype),
        "output_is_finite": bool(torch.isfinite(waveform.float()).all()),
        "output_peak": round(float(waveform.float().abs().max()), 5),
        "output_rms": round(float(waveform.float().pow(2).mean().sqrt()), 6),
        "warnings": sorted({f"{w.category.__name__}: {w.message}" for w in caught})[:10],
        "load_seconds": round(loaded, 2),
        "seconds": round(elapsed, 2),
        "requested_seconds": ACE_STEP_SMOKE_SECONDS,
    }


SMOKES = {
    "basic-pitch": smoke_basic_pitch,
    "demucs": smoke_demucs,
    "ace-step": smoke_ace_step,
}


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="smoke_cabinet.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "entries",
        nargs="*",
        choices=[*SMOKES, []],
        help="cabinet entries to smoke; default is all of them, cheapest first",
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    root = args.root or find_repository_root(Path.cwd())
    try:
        cabinet = load_repository_cabinet(root)
    except CabinetError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_UNREADABLE

    chosen = args.entries or list(SMOKES)
    report: dict[str, Any] = {
        "repository": str(root),
        "runtime": _runtime(),
        "entries": {},
    }
    try:
        report["torch"] = _torch_devices()
    except ImportError as exc:
        print(
            f"the cabinet environment is not active: {exc}. Run this with "
            f"`{cabinet.runtime.environment_path}/bin/python`.",
            file=sys.stderr,
        )
        return EXIT_BLOCKED

    failed = False
    with tempfile.TemporaryDirectory(prefix="spectral-loom-smoke-") as temporary:
        workdir = Path(temporary)
        for name in chosen:
            if not args.json:
                print(f"--- {name} ---", flush=True)
            try:
                result = SMOKES[name](root, cabinet, workdir)
            except Exception as exc:  # a failed smoke is a recorded result, not a crash
                failed = True
                result = {"executed": False, "error": f"{type(exc).__name__}: {exc}"}
            report["entries"][name] = result
            if not args.json:
                for key, value in result.items():
                    print(f"  {key}: {value}")
                print(flush=True)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return EXIT_BLOCKED if failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
