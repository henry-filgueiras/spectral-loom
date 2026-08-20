"""Shared fixtures.

No audio fixture is committed. Where a test needs audio-like input it synthesizes
a minimal WAV into pytest's `tmp_path`, which the test framework removes; see
`docs/architecture.md` on why generated audio never enters the tree.

The suite is hermetic. `tests/netguard.py` is re-exported here so its autouse
fixture applies to every test: nothing under `tests/` may open a connection that
leaves the machine, and nothing may need model weights on disk.
"""

from __future__ import annotations

import json
import math
import struct
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.netguard import _block_network  # noqa: F401  (autouse fixture)


@pytest.fixture
def write_json(tmp_path: Path) -> Callable[[str, Any], Path]:
    """Write a document to a temporary file and return its path."""

    def _write(name: str, document: Any) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def tone_wav(tmp_path: Path) -> Callable[..., Path]:
    """Synthesize a short mono sine WAV inside `tmp_path`.

    Deliberately tiny and deliberately temporary: pytest's temporary-directory
    lifecycle owns it, so nothing audio-shaped survives the test run.
    """

    def _write(name: str = "tone.wav", seconds: float = 0.25, hz: float = 440.0) -> Path:
        path = tmp_path / name
        rate = 8000
        frames = int(rate * seconds)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(
                b"".join(
                    struct.pack("<h", int(20000 * math.sin(2 * math.pi * hz * n / rate)))
                    for n in range(frames)
                )
            )
        return path

    return _write
