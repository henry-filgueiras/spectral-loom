"""Cabinet manifest tests.

Two jobs. The first is the tracked `model-cabinet.toml` itself: it is the only
record of what this project meant by ACE-Step, Demucs, and Basic Pitch that
survives a clean clone, so the properties that make it a *pin* rather than a
description are asserted rather than trusted.

The second is the verification logic the bootstrap uses to decide whether to
download eleven gigabytes. That decision is exactly the sort of thing that is
easy to get wrong and expensive to get wrong, and it is testable without a byte
of network or a byte of weights: a pinned file with a known size and a known
sha256 can be forged into `tmp_path` in three lines.

Hermetic, like everything in the default suite. Nothing here opens a socket and
nothing here needs `models/` to exist.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from spectral_loom.cabinet import (
    CABINET_FILENAME,
    Asset,
    AssetStatus,
    Cabinet,
    CabinetError,
    asset_directory,
    check_asset,
    find_repository_root,
    iter_assets,
    load_cabinet,
    load_repository_cabinet,
    needs_fetch,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cabinet() -> Cabinet:
    return load_repository_cabinet(REPO_ROOT)


# ---------------------------------------------------------------------------
# The tracked manifest.
# ---------------------------------------------------------------------------


def test_the_committed_manifest_parses(cabinet: Cabinet) -> None:
    assert cabinet.schema_version == "1"
    assert set(cabinet.entry) == {"ace-step", "demucs", "basic-pitch"}


def test_every_asset_revision_is_immutable(cabinet: Cabinet) -> None:
    """A branch moves and a tag can be moved; forty hex digits cannot.

    `scripts/README.md` rule 1 in executable form. A tag that moved after a
    result was recorded invalidates that result with no diff anywhere, so the
    contract refuses to hold one at all.
    """
    for name, _entry, asset in iter_assets(cabinet):
        assert len(asset.revision) == 40, name
        assert set(asset.revision) <= set("0123456789abcdef"), name


@pytest.mark.parametrize("moving", ["main", "v1.5", "refs/heads/main", "200BA991AE448051" * 2])
def test_a_moving_revision_is_rejected(cabinet: Cabinet, moving: str) -> None:
    """Including an uppercase sha, which is the same commit spelled differently.

    One commit, one spelling. Two spellings of the same revision produce two
    directories under `models/` and two apparently-different provenance records.
    """
    asset = next(a for _n, _e, a in iter_assets(cabinet))
    with pytest.raises(ValueError, match="revision"):
        Asset.model_validate(asset.model_dump() | {"revision": moving})


def test_every_entry_records_a_license(cabinet: Cabinet) -> None:
    """`scripts/README.md` rule 4. The weights are untracked, so this is the
    only place the answer survives."""
    for name, entry in cabinet.entry.items():
        assert entry.code.license, name
        for asset in entry.assets:
            assert asset.license, name


def test_every_code_identity_carries_a_published_digest(cabinet: Cabinet) -> None:
    for name, entry in cabinet.entry.items():
        assert len(entry.code.sha256) == 64, name
        assert entry.code.version, name


def test_every_weights_file_carries_an_upstream_hash(cabinet: Cabinet) -> None:
    """The weights themselves are hash-pinned; configuration may be size-pinned.

    The line is upstream's, not a threshold invented here: Hugging Face
    publishes a sha256 for LFS-tracked files, and in these repositories that is
    exactly the `.safetensors`. A tokenizer vocabulary is committed as a plain
    blob and has no published sha256, so it is pinned by size and by the
    revision it belongs to. Quoting a hash we computed ourselves as though
    upstream had published it would be worse than pinning by size.
    """
    for name, _entry, asset in iter_assets(cabinet):
        unhashed = [f for f in asset.files if f.sha256 is None and f.path.endswith(".safetensors")]
        assert not unhashed, f"{name}: {[f.path for f in unhashed]}"
        assert asset.hashed_files, name


def test_no_asset_fetches_executable_model_code(cabinet: Cabinet) -> None:
    """`scripts/README.md` rule 5, at the level of what is downloaded at all.

    `trust_remote_code` cannot be turned on for a repository that contains no
    code, and a pickle cannot execute if it is never fetched. Both classes are
    kept out here rather than guarded against later.
    """
    for name, _entry, asset in iter_assets(cabinet):
        for pinned in asset.files:
            assert not pinned.path.endswith((".py", ".pt", ".pth", ".pkl", ".bin")), (
                f"{name} would fetch {pinned.path}"
            )


def test_the_ace_step_pickle_is_excluded_deliberately(cabinet: Cabinet) -> None:
    """Not an accident of the file list: the exclusion is recorded as a choice."""
    asset = cabinet.entry["ace-step"].assets[0]
    assert "silence_latent.pt" in asset.excluded


def test_basic_pitch_has_no_assets_and_says_why(cabinet: Cabinet) -> None:
    """An entry with nothing to download is a fact about upstream, not a gap."""
    entry = cabinet.entry["basic-pitch"]
    assert entry.assets == []
    assert entry.code.bundled_weights is not None
    assert entry.code.bundled_weights_backend is not None


def test_total_bytes_matches_the_files_actually_fetched(cabinet: Cabinet) -> None:
    for name, _entry, asset in iter_assets(cabinet):
        assert asset.total_bytes == sum(f.size for f in asset.files), name


def test_an_adapter_resolves_to_exactly_one_entry(cabinet: Cabinet) -> None:
    name, entry = cabinet.entry_for_adapter("ace-step")
    assert name == "ace-step"
    assert entry.code.distribution == "diffusers"

    with pytest.raises(CabinetError, match="no cabinet entry provides adapter"):
        cabinet.entry_for_adapter("riffusion")


def test_a_missing_entry_names_the_ones_that_exist(cabinet: Cabinet) -> None:
    with pytest.raises(CabinetError, match="ace-step, basic-pitch, demucs"):
        cabinet.require("nope")


# ---------------------------------------------------------------------------
# Parsing failures.
# ---------------------------------------------------------------------------


def test_unreadable_manifest_is_reported_not_raised_bare(tmp_path: Path) -> None:
    with pytest.raises(CabinetError, match="cannot read"):
        load_cabinet(tmp_path / "absent.toml")


def test_malformed_toml_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / CABINET_FILENAME
    path.write_text("schema_version = \n", encoding="utf-8")
    with pytest.raises(CabinetError, match="not valid TOML"):
        load_cabinet(path)


MINIMAL_MANIFEST = """
schema_version = "1"

[runtime]
python = "3.11"
uv_extra = "cabinet"
environment_path = ".venv-cabinet"
torch = "2.13.0"
accelerator = "mps"

[entry.toy]
purpose = "nothing"
adapter = "toy"
upstream = "https://example.invalid"

[entry.toy.code]
kind = "pypi"
distribution = "toy"
version = "1.0"
symbol = "toy.run"
license = "MIT"
sha256 = "{sha}"
artifact = "toy-1.0-py3-none-any.whl"
"""


def test_a_minimal_manifest_is_enough(tmp_path: Path) -> None:
    """An entry with no assets is legal, because Basic Pitch is one."""
    path = tmp_path / CABINET_FILENAME
    path.write_text(MINIMAL_MANIFEST.format(sha="a" * 64), encoding="utf-8")
    parsed = load_cabinet(path)
    assert parsed.entry["toy"].assets == []


def test_an_unknown_field_is_an_error_not_a_shrug(tmp_path: Path) -> None:
    """A typo in a pinned field must fail loudly rather than be dropped.

    `Contract` forbids extra fields for exactly this: `reivsion` silently
    ignored means an asset pinned to nothing, discovered much later.
    """
    path = tmp_path / CABINET_FILENAME
    path.write_text(
        MINIMAL_MANIFEST.format(sha="a" * 64) + '\nreivsion = "typo"\n', encoding="utf-8"
    )
    with pytest.raises(CabinetError, match="reivsion"):
        load_cabinet(path)


def test_a_short_revision_is_rejected(tmp_path: Path) -> None:
    """An abbreviated sha is ambiguous, and ambiguity is what pinning removes."""
    path = tmp_path / CABINET_FILENAME
    path.write_text(
        MINIMAL_MANIFEST.format(sha="a" * 64)
        + """
[[entry.toy.assets]]
kind = "huggingface-repo"
repo_id = "example/toy"
revision = "200ba99"
license = "MIT"
variant = "toy"
total_bytes = 1
files = [{ path = "a", size = 1 }]
""",
        encoding="utf-8",
    )
    with pytest.raises(CabinetError, match="revision"):
        load_cabinet(path)


def test_find_repository_root_walks_up(tmp_path: Path) -> None:
    (tmp_path / CABINET_FILENAME).write_text("", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_repository_root(nested) == tmp_path


def test_find_repository_root_falls_back_to_the_start(tmp_path: Path) -> None:
    assert find_repository_root(tmp_path) == tmp_path


# ---------------------------------------------------------------------------
# Verifying what is on disk. This is what decides whether to download 11 GiB.
# ---------------------------------------------------------------------------


def _forge(root: Path, entry: str, asset: Asset, contents: dict[str, bytes]) -> Path:
    directory = asset_directory(root, entry, asset)
    for relative, payload in contents.items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return directory


@pytest.fixture
def toy_asset() -> Asset:
    """A two-file asset whose real bytes fit in a test."""
    weights = b"weights" * 16
    config = b'{"ok": true}'
    return Asset(
        kind="huggingface-repo",
        repo_id="example/toy",
        revision="0" * 39 + "a",
        license="MIT",
        variant="toy",
        total_bytes=len(weights) + len(config),
        files=[
            {
                "path": "model.safetensors",
                "size": len(weights),
                "sha256": hashlib.sha256(weights).hexdigest(),
            },
            {"path": "config.json", "size": len(config)},
        ],
    )


@pytest.fixture
def toy_bytes() -> dict[str, bytes]:
    return {"model.safetensors": b"weights" * 16, "config.json": b'{"ok": true}'}


def test_absent_when_nothing_is_there(tmp_path: Path, toy_asset: Asset) -> None:
    report = check_asset(tmp_path, "toy", toy_asset, verify_hashes=True)
    assert report.status is AssetStatus.ABSENT
    assert needs_fetch(report)
    assert report.summary() == "not fetched"


def test_incomplete_when_some_files_are_missing(
    tmp_path: Path, toy_asset: Asset, toy_bytes: dict[str, bytes]
) -> None:
    _forge(tmp_path, "toy", toy_asset, {"config.json": toy_bytes["config.json"]})
    report = check_asset(tmp_path, "toy", toy_asset, verify_hashes=True)
    assert report.status is AssetStatus.INCOMPLETE
    assert [f.path for f in report.missing] == ["model.safetensors"]
    assert needs_fetch(report)


def test_verified_when_every_hash_matches(
    tmp_path: Path, toy_asset: Asset, toy_bytes: dict[str, bytes]
) -> None:
    _forge(tmp_path, "toy", toy_asset, toy_bytes)
    report = check_asset(tmp_path, "toy", toy_asset, verify_hashes=True)
    assert report.status is AssetStatus.VERIFIED
    assert not needs_fetch(report)


def test_present_but_unverified_when_hashing_is_skipped(
    tmp_path: Path, toy_asset: Asset, toy_bytes: dict[str, bytes]
) -> None:
    """`doctor` cannot afford to hash the cabinet, and must not claim it did.

    The two statuses are two different claims: one says the right number of
    bytes is there, the other says they are the right bytes.
    """
    _forge(tmp_path, "toy", toy_asset, toy_bytes)
    report = check_asset(tmp_path, "toy", toy_asset, verify_hashes=False)
    assert report.status is AssetStatus.PRESENT
    assert report.hashes_checked is False
    assert "hashes not checked" in report.summary()
    assert needs_fetch(report), "an unhashed report may never authorise skipping a fetch"


def test_a_truncated_download_is_corrupt_not_present(
    tmp_path: Path, toy_asset: Asset, toy_bytes: dict[str, bytes]
) -> None:
    forged = dict(toy_bytes, **{"model.safetensors": toy_bytes["model.safetensors"][:-10]})
    _forge(tmp_path, "toy", toy_asset, forged)
    report = check_asset(tmp_path, "toy", toy_asset, verify_hashes=False)
    assert report.status is AssetStatus.CORRUPT
    assert "expected 112 bytes, found 102" in report.bad[0].problem  # type: ignore[operator]


def test_right_length_wrong_bytes_is_caught_only_by_hashing(
    tmp_path: Path, toy_asset: Asset, toy_bytes: dict[str, bytes]
) -> None:
    """The exact case the size check cannot see, and the reason the bootstrap hashes.

    A re-download that silently produces different bytes of the same length is
    the failure `scripts/README.md` rule 3 exists to catch.
    """
    forged = dict(toy_bytes, **{"model.safetensors": b"WEIGHTS" * 16})
    _forge(tmp_path, "toy", toy_asset, forged)

    assert (
        check_asset(tmp_path, "toy", toy_asset, verify_hashes=False).status is AssetStatus.PRESENT
    )

    hashed = check_asset(tmp_path, "toy", toy_asset, verify_hashes=True)
    assert hashed.status is AssetStatus.CORRUPT
    assert "sha256" in hashed.bad[0].problem  # type: ignore[operator]


def test_assets_are_keyed_by_revision_so_repinning_does_not_overwrite(
    tmp_path: Path, toy_asset: Asset
) -> None:
    other = toy_asset.model_copy(update={"revision": "1" * 40})
    assert asset_directory(tmp_path, "toy", toy_asset) != asset_directory(tmp_path, "toy", other)
    assert asset_directory(tmp_path, "toy", toy_asset).parent.name == "toy"


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    payload = b"x" * (1024 * 1024 + 7)  # across the read-chunk boundary
    path = tmp_path / "blob"
    path.write_bytes(payload)
    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()
