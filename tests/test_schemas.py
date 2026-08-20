"""Schema drift.

The Python contracts are the source of truth; `schemas/*.schema.json` is their
committed, language-neutral projection. If these disagree, the reviewable
artifact that decision:3 relies on has stopped describing the code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spectral_loom import schemas


def test_committed_schemas_match_the_contracts() -> None:
    stale = schemas.drift()
    assert not stale, (
        f"committed schemas are stale: {stale}. "
        "Regenerate with: uv run python -m spectral_loom.schemas --write"
    )


def test_every_contract_has_a_committed_schema() -> None:
    for name in schemas.EXPORTS:
        assert (schemas.schemas_dir() / name).is_file()


def test_schemas_declare_their_dialect_and_identity() -> None:
    for name in schemas.EXPORTS:
        document: dict[str, Any] = json.loads(
            (schemas.schemas_dir() / name).read_text(encoding="utf-8")
        )
        assert document["$schema"] == schemas.SCHEMA_DIALECT
        assert document["$id"].endswith("0.1.0.json")


def test_generation_is_deterministic(tmp_path: Path) -> None:
    assert schemas.write(tmp_path), "first write must produce files"
    assert schemas.write(tmp_path) == [], "a second write must change nothing"
    assert schemas.drift(tmp_path) == []


def test_timeline_schema_forbids_unknown_envelope_fields() -> None:
    document: dict[str, Any] = json.loads(
        (schemas.schemas_dir() / "song-timeline.schema.json").read_text(encoding="utf-8")
    )
    assert document["additionalProperties"] is False
