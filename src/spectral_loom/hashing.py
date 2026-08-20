"""Content hashing, in one place because three stages now agree on it.

A hash is how this project identifies audio. Paths move, directory names name
intents rather than bytes, and a manifest is a claim about a file that may since
have changed — so every stage boundary is guarded by a digest, and every digest
in this repository is written the same way: ``sha256:`` followed by sixty-four
lowercase hex digits, matching ``contracts.ContentHash``.

The algorithm prefix is not decoration. It is what makes a future migration to
another digest a legible diff in a document rather than a silent reinterpretation
of every hash already written down.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Read in chunks so hashing an eleven-gigabyte cabinet does not need eleven
#: gigabytes of memory.
HASH_CHUNK = 1024 * 1024


def hash_bytes(payload: bytes) -> str:
    """The prefixed digest of a byte string."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def hash_file(path: Path) -> str:
    """The prefixed digest of a file's contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
