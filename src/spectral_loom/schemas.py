"""Generate and compare the committed JSON Schemas for the contracts.

The Python models are the source of truth; ``schemas/*.schema.json`` is the
reviewable, language-neutral projection of them. Committing the generated file
is what makes a contract change visible in a diff to a reader who does not read
Python — which is the whole reason the compiler boundary is a file
(``archaeology/decisions/0003``).

Regenerate after any contract change::

    uv run python -m spectral_loom.schemas --write

``tests/test_schemas.py`` fails when the committed files and the models disagree.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from spectral_loom.contracts import (
    GENERATION_SCHEMA_ID,
    GENERATION_SCHEMA_VERSION,
    REVIEW_SCHEMA_ID,
    REVIEW_SCHEMA_VERSION,
    SEPARATION_SCHEMA_ID,
    SEPARATION_SCHEMA_VERSION,
    SPEC_SCHEMA_ID,
    SPEC_SCHEMA_VERSION,
    TIMELINE_SCHEMA_ID,
    TIMELINE_SCHEMA_VERSION,
    GenerationManifest,
    SeparationManifest,
    SongSpec,
    SongTimeline,
    SpecimenReview,
)

Exported = (
    type[SongSpec]
    | type[SongTimeline]
    | type[GenerationManifest]
    | type[SpecimenReview]
    | type[SeparationManifest]
)

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

#: Filename to the model it is generated from, plus the identity it declares.
EXPORTS: dict[str, tuple[Exported, str, str]] = {
    "song-spec.schema.json": (SongSpec, SPEC_SCHEMA_ID, SPEC_SCHEMA_VERSION),
    "song-timeline.schema.json": (SongTimeline, TIMELINE_SCHEMA_ID, TIMELINE_SCHEMA_VERSION),
    "generation-manifest.schema.json": (
        GenerationManifest,
        GENERATION_SCHEMA_ID,
        GENERATION_SCHEMA_VERSION,
    ),
    "specimen-review.schema.json": (
        SpecimenReview,
        REVIEW_SCHEMA_ID,
        REVIEW_SCHEMA_VERSION,
    ),
    "separation-manifest.schema.json": (
        SeparationManifest,
        SEPARATION_SCHEMA_ID,
        SEPARATION_SCHEMA_VERSION,
    ),
}


def schemas_dir() -> Path:
    """The committed schema directory, resolved from this file's location."""
    return Path(__file__).resolve().parents[2] / "schemas"


def build(model: Exported, schema_id: str, version: str) -> dict[str, Any]:
    """Build one JSON Schema document, stamped with its dialect and identity."""
    schema: dict[str, Any] = {
        "$schema": SCHEMA_DIALECT,
        "$id": f"https://spectral-loom.invalid/schemas/{schema_id}/{version}.json",
    }
    schema.update(model.model_json_schema(mode="validation"))
    return schema


def render(schema: dict[str, Any]) -> str:
    """Serialize deterministically: sorted keys, two-space indent, trailing newline."""
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def generate() -> dict[str, str]:
    """Every schema this project publishes, as filename to rendered text."""
    return {name: render(build(*spec)) for name, spec in EXPORTS.items()}


def write(target: Path | None = None) -> list[Path]:
    """Write the schemas to disk, returning the paths that actually changed."""
    directory = target or schemas_dir()
    directory.mkdir(parents=True, exist_ok=True)
    changed: list[Path] = []
    for name, text in generate().items():
        path = directory / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            changed.append(path)
    return changed


def drift(target: Path | None = None) -> list[str]:
    """Names of committed schemas that disagree with the models, or are missing."""
    directory = target or schemas_dir()
    stale: list[str] = []
    for name, text in generate().items():
        path = directory / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(name)
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m spectral_loom.schemas",
        description="Generate the committed JSON Schemas, or check them for drift.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the schemas. Without it, drift is only reported.",
    )
    args = parser.parse_args(argv)

    if args.write:
        changed = write()
        for path in changed:
            print(f"wrote {path}")
        if not changed:
            print("schemas already up to date")
        return 0

    stale = drift()
    for name in stale:
        print(f"stale: schemas/{name}", file=sys.stderr)
    if stale:
        print("run: uv run python -m spectral_loom.schemas --write", file=sys.stderr)
        return 1
    print("schemas match the contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
