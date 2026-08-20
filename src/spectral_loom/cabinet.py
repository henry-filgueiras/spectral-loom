"""Reading and checking the model cabinet.

``model-cabinet.toml`` is the tracked record of what this project means by
"ACE-Step", "Demucs", and "Basic Pitch". The weights it describes are not
tracked, so from a clean clone that file is the only surviving statement of
which code and which bytes produced any result here.

This module is the parser and the verifier, and it is deliberately **stdlib
only**. It is imported by ``spectral-loom doctor``, which runs in the default
environment where none of the cabinet is installed, and by the bootstrap script,
which has to decide whether to download something before it can import anything
that would download it. Neither may need ``huggingface_hub`` to answer "is this
already here".

The pinning vocabulary is upstream's, not this project's:

``code``
    The implementation that executes. A released distribution, identified by
    version and by the digest the index publishes for the exact artifact.
``assets``
    Weights fetched separately, identified by an immutable repository revision
    and by whatever per-file hashes upstream publishes. An entry may have none;
    Basic Pitch ships its weights inside its own wheel.
``runtime``
    The versions whose behaviour materially changes inference. The same weights
    under a different torch are a different result.

Layout on disk is this project's, not the hub's::

    models/<entry name>/<revision>/<path within the repository>

owned here rather than borrowed from a cache implementation, so that
``doctor`` can find an asset without importing the library that fetched it.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import Field, ValidationError

from spectral_loom.contracts import Contract

#: The tracked manifest, at the repository root beside `uv.lock`, because it is
#: the same kind of artifact: a lock over things fetched from the network.
CABINET_FILENAME: Final = "model-cabinet.toml"

#: Where fetched weights land. Ignored by Git; see `.gitignore`.
MODELS_DIRNAME: Final = "models"

#: An immutable Git revision. Forty lowercase hex digits and nothing else: a
#: branch moves, and a tag can be moved, which is the failure `scripts/README.md`
#: names explicitly.
Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]

#: A bare sha256, as upstream publishes it (no algorithm prefix — that
#: convention belongs to the timeline contract, and this file quotes upstream).
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_HASH_CHUNK = 1024 * 1024


class CabinetError(Exception):
    """The manifest could not be read, or does not describe a usable cabinet."""


# ---------------------------------------------------------------------------
# The manifest.
# ---------------------------------------------------------------------------


class CabinetFile(Contract):
    """One file within a pinned asset repository.

    ``sha256`` is present only where upstream publishes one. On the Hugging Face
    hub that means the LFS-tracked files, which is every file whose contents are
    weights; the small JSON beside them is verified by size alone. Saying so is
    better than inventing a hash we computed ourselves and calling it upstream's.
    """

    path: str = Field(min_length=1, max_length=512)
    size: int = Field(ge=0)
    sha256: Sha256 | None = None


class Asset(Contract):
    """A set of weights fetched at an exact revision."""

    kind: Literal["huggingface-repo"]
    repo_id: str = Field(min_length=1, max_length=200)
    revision: Revision
    license: str = Field(min_length=1, max_length=100)
    variant: str = Field(min_length=1, max_length=100)
    total_bytes: int = Field(ge=0)
    excluded: list[str] = Field(
        default_factory=list,
        description="Files present at the revision that this project deliberately does not fetch.",
    )
    files: list[CabinetFile] = Field(min_length=1)

    @property
    def hashed_files(self) -> list[CabinetFile]:
        return [f for f in self.files if f.sha256 is not None]


class Code(Contract):
    """The implementation that executes for one cabinet entry."""

    kind: Literal["pypi"]
    distribution: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    symbol: str = Field(min_length=1, max_length=200)
    license: str = Field(min_length=1, max_length=100)
    sha256: Sha256
    artifact: str = Field(min_length=1, max_length=200)

    bundled_weights: str | None = Field(
        default=None,
        description="Path within the distribution where it ships its own weights, if it does.",
    )
    bundled_weights_backend: str | None = Field(
        default=None,
        description="Which serialization of those weights this environment actually executes.",
    )

    @property
    def module(self) -> str:
        """Importable module name, which is not always the distribution name."""
        return self.symbol.split(".")[0]


class Entry(Contract):
    """One cabinet entry: an implementation, its assets, and why it is here."""

    purpose: str = Field(min_length=1, max_length=200)
    adapter: str = Field(min_length=1, max_length=64)
    upstream: str = Field(min_length=1, max_length=300)
    reference: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=8000)

    code: Code
    assets: list[Asset] = Field(default_factory=list)


class Runtime(Contract):
    """Versions shared by the whole cabinet whose behaviour changes results."""

    python: str = Field(min_length=1, max_length=20)
    uv_extra: str = Field(min_length=1, max_length=64)
    environment_path: str = Field(min_length=1, max_length=200)
    torch: str = Field(min_length=1, max_length=50)
    accelerator: str = Field(min_length=1, max_length=50)


class Cabinet(Contract):
    """The whole manifest."""

    schema_version: Literal["1"]
    runtime: Runtime
    entry: dict[str, Entry] = Field(min_length=1)

    def require(self, name: str) -> Entry:
        """Look up an entry, failing with the names that do exist."""
        try:
            return self.entry[name]
        except KeyError:
            raise CabinetError(
                f"no cabinet entry named {name!r}; {CABINET_FILENAME} has "
                f"{', '.join(sorted(self.entry))}"
            ) from None

    def entry_for_adapter(self, adapter: str) -> tuple[str, Entry]:
        """Find the entry a `SongSpec`'s generator adapter names.

        A specification names an adapter, not a cabinet key, because the adapter
        is this project's vocabulary and survives the cabinet being re-pinned.
        """
        matches = [(name, e) for name, e in self.entry.items() if e.adapter == adapter]
        if not matches:
            raise CabinetError(
                f"no cabinet entry provides adapter {adapter!r}; {CABINET_FILENAME} provides "
                f"{', '.join(sorted({e.adapter for e in self.entry.values()}))}"
            )
        if len(matches) > 1:
            raise CabinetError(
                f"cabinet entries {', '.join(sorted(n for n, _ in matches))} all claim "
                f"adapter {adapter!r}; an adapter must name exactly one implementation"
            )
        return matches[0]


def load_cabinet(path: Path) -> Cabinet:
    """Read and validate the manifest, or say precisely what is wrong with it."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CabinetError(f"cannot read {path}: {exc.strerror or exc}") from exc
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise CabinetError(f"{path} is not valid TOML: {exc}") from exc
    try:
        return Cabinet.model_validate(document)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in item['loc']) or '<document>'}: {item['msg']}"
            for item in exc.errors()
        )
        raise CabinetError(f"{path} is not a valid cabinet manifest: {details}") from exc


def find_repository_root(start: Path) -> Path:
    """Nearest ancestor holding the manifest, else the starting directory."""
    for candidate in [start, *start.parents]:
        if (candidate / CABINET_FILENAME).is_file():
            return candidate
    return start


def load_repository_cabinet(root: Path) -> Cabinet:
    return load_cabinet(root / CABINET_FILENAME)


# ---------------------------------------------------------------------------
# Checking what is actually on disk.
# ---------------------------------------------------------------------------


class AssetStatus(StrEnum):
    """How an asset's local copy stands relative to what the manifest pins.

    These are five different situations and the bootstrap does five different
    things about them, which is why they are not a boolean. In particular
    ``PRESENT`` and ``VERIFIED`` are not the same claim: hashing eleven
    gigabytes is affordable in a bootstrap and is not affordable in a `doctor`
    that a person runs to see whether their checkout is healthy.
    """

    ABSENT = "absent"
    INCOMPLETE = "incomplete"
    PRESENT = "present"
    VERIFIED = "verified"
    CORRUPT = "corrupt"


class FileReport(Contract):
    """What was found where one pinned file should be."""

    path: str
    expected_size: int
    actual_size: int | None = None
    expected_sha256: Sha256 | None = None
    actual_sha256: Sha256 | None = None
    problem: str | None = None

    @property
    def present(self) -> bool:
        return self.actual_size is not None

    @property
    def ok(self) -> bool:
        return self.present and self.problem is None


class AssetReport(Contract):
    """The verdict on one asset, and the evidence for it."""

    entry: str
    repo_id: str
    revision: str
    directory: str
    status: AssetStatus
    hashes_checked: bool
    files: list[FileReport]

    @property
    def missing(self) -> list[FileReport]:
        return [f for f in self.files if not f.present]

    @property
    def bad(self) -> list[FileReport]:
        return [f for f in self.files if f.present and f.problem is not None]

    def summary(self) -> str:
        """One line a human can act on."""
        if self.status is AssetStatus.VERIFIED:
            return f"{len(self.files)} file(s) verified against published hashes"
        if self.status is AssetStatus.PRESENT:
            return f"{len(self.files)} file(s) present at the expected sizes; hashes not checked"
        if self.status is AssetStatus.ABSENT:
            return "not fetched"
        if self.status is AssetStatus.INCOMPLETE:
            return f"{len(self.missing)} of {len(self.files)} file(s) missing"
        problems = "; ".join(f"{f.path}: {f.problem}" for f in self.bad[:3])
        return f"{len(self.bad)} file(s) do not match what is pinned — {problems}"


def models_root(repository_root: Path) -> Path:
    return repository_root / MODELS_DIRNAME


def asset_directory(repository_root: Path, entry_name: str, asset: Asset) -> Path:
    """Where an asset's files live.

    Keyed by revision, so re-pinning downloads beside the old copy rather than
    over it: two revisions of the same weights are two different things, and a
    directory that silently becomes a different revision is how an unattributable
    result gets made.
    """
    return models_root(repository_root) / entry_name / asset.revision


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def check_asset(
    repository_root: Path,
    entry_name: str,
    asset: Asset,
    *,
    verify_hashes: bool,
) -> AssetReport:
    """Judge an asset's local copy without changing or fetching anything.

    With ``verify_hashes`` off this reads only directory metadata, which is what
    makes it cheap enough for `doctor`. The distinction between "the right number
    of bytes is there" and "those are the right bytes" is preserved in the
    status rather than papered over: a truncated download that happens to have
    been truncated at the exact expected length is the only case the size check
    misses, and the bootstrap closes it before it fetches anything.
    """
    directory = asset_directory(repository_root, entry_name, asset)
    reports: list[FileReport] = []

    for pinned in asset.files:
        target = directory / pinned.path
        report = FileReport(
            path=pinned.path,
            expected_size=pinned.size,
            expected_sha256=pinned.sha256,
        )
        if not target.is_file():
            reports.append(report)
            continue
        report.actual_size = target.stat().st_size
        if report.actual_size != pinned.size:
            report.problem = f"expected {pinned.size} bytes, found {report.actual_size}"
        elif verify_hashes and pinned.sha256 is not None:
            report.actual_sha256 = sha256_file(target)
            if report.actual_sha256 != pinned.sha256:
                report.problem = f"sha256 {report.actual_sha256} does not match {pinned.sha256}"
        reports.append(report)

    present = [r for r in reports if r.present]
    bad = [r for r in reports if r.present and r.problem is not None]

    if bad:
        status = AssetStatus.CORRUPT
    elif not present:
        status = AssetStatus.ABSENT
    elif len(present) < len(reports):
        status = AssetStatus.INCOMPLETE
    elif verify_hashes:
        status = AssetStatus.VERIFIED
    else:
        status = AssetStatus.PRESENT

    return AssetReport(
        entry=entry_name,
        repo_id=asset.repo_id,
        revision=asset.revision,
        directory=str(directory),
        status=status,
        hashes_checked=verify_hashes,
        files=reports,
    )


def iter_assets(cabinet: Cabinet) -> Iterator[tuple[str, Entry, Asset]]:
    """Every downloadable asset in the cabinet, with the entry that owns it."""
    for name, entry in sorted(cabinet.entry.items()):
        for asset in entry.assets:
            yield name, entry, asset


def needs_fetch(report: AssetReport) -> bool:
    """Whether the bootstrap has work to do for this asset.

    ``VERIFIED`` and ``PRESENT`` are both "leave it alone" — but only a report
    produced with hashing on can say ``VERIFIED``, so the bootstrap asks for one
    and this function does not have to know which caller it is serving.
    """
    return report.status is not AssetStatus.VERIFIED


# ---------------------------------------------------------------------------
# Checking the environment, without importing anything from it.
# ---------------------------------------------------------------------------


class InstalledCode(Contract):
    """What is installed where a cabinet entry's implementation should be."""

    distribution: str
    pinned_version: str
    installed_version: str | None = None

    @property
    def present(self) -> bool:
        return self.installed_version is not None

    @property
    def matches(self) -> bool:
        return self.installed_version == self.pinned_version


def environment_site_packages(repository_root: Path, cabinet: Cabinet) -> Path:
    """Where the cabinet environment's distributions live.

    Derived rather than searched, and derived from the same `python` the
    manifest pins, so a mismatch shows up as "not installed" rather than as a
    silently different interpreter's packages being reported as this one's.
    """
    version = ".".join(cabinet.runtime.python.split(".")[:2])
    return (
        repository_root
        / cabinet.runtime.environment_path
        / "lib"
        / f"python{version}"
        / "site-packages"
    )


def installed_versions(site_packages: Path) -> dict[str, str]:
    """Read distribution versions out of an environment this process is not in.

    Metadata on disk, never an import: `doctor` runs in the default environment
    where torch is absent by design, and importing eleven gigabytes to answer
    "is it installed" would make the answer cost more than the question.
    """
    if not site_packages.is_dir():
        return {}

    from importlib.metadata import DistributionFinder, distributions

    found: dict[str, str] = {}
    context = DistributionFinder.Context(path=[str(site_packages)])
    for distribution in distributions(context=context):
        name = distribution.metadata["Name"]
        if name:
            found[_normalize(name)] = distribution.version
    return found


def check_code(cabinet: Cabinet, installed: dict[str, str], entry: Entry) -> InstalledCode:
    return InstalledCode(
        distribution=entry.code.distribution,
        pinned_version=entry.code.version,
        installed_version=installed.get(_normalize(entry.code.distribution)),
    )


def _normalize(name: str) -> str:
    """PEP 503 name normalization: `basic-pitch` and `basic_pitch` are one name."""
    return re.sub(r"[-_.]+", "-", name).lower()
