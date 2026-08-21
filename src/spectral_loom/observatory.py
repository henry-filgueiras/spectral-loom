"""The Stem Observatory: a separation evidence microscope.

Gate 3 is passed by a human hearing the stems. That is the whole reason this
exists, and it is also the whole reason it is small. A gate whose evidence is
inconvenient to examine is a gate that gets waved through, and "open five
unrelated WAVs in a media player and try to remember what the fourth one sounded
like" is inconvenient enough to guarantee it.

So this is not the analytical projection of roadmap gate 6, and it is not a
generalized UI. It is one page whose only job is to make an honest answer to
"is the bass actually isolated" cheaper than a lazy one.

**One clock.** Every lane is an `AudioBufferSourceNode` started at the same
instant on one `AudioContext` timeline, which is what makes solo, mute and
A/B comparison meaningful. Independently running `<audio>` elements drift, and
two lanes that drift are two lanes you cannot compare.

**Labels stay honest.** A lane reads `HTDemucs · bass`, because that is what the
file is: the signal HTDemucs assigned to its `bass` output. It is not a verified
instrument, and the page never says it is. The reconstructed mix and the
residual are labelled engineering diagnostics and are visually separated from
the stems, because they are arithmetic rather than anybody's opinion.

**Nothing leaves the machine.** The page has no external stylesheet, script,
font or image; the server binds to loopback and serves a fixed whitelist of
files; and the audio is served from where it already lives rather than copied or
inlined, because seven eight-megabyte blobs base64'd into an HTML file is not a
microscope, it is a monument.

The split in this module is between what can be tested and what has to be
listened to. :func:`build_exhibit` and :func:`render` are pure, are exercised by
the hermetic suite, and are where the honesty lives. :func:`serve` starts a
socket and is not.


The page itself is `pages/stem_observatory.html`, a real file rather than a string in
this module. That is a bug fix, not tidiness: a template embedded in a
non-raw triple-quoted Python string is decoded by Python's parser before a
browser ever sees it, so a newline escape written in JavaScript silently
became a real newline inside a string literal and the page stopped parsing —
while every Python test still passed. A file has one reader and cannot be
escaped wrong.
"""

from __future__ import annotations

import html
import json
import webbrowser
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from spectral_loom.contracts import AudioArtifact, SeparationManifest, SpecimenReview
from spectral_loom.hashing import hash_file
from spectral_loom.separate import DERIVED_DIRNAME

#: Generated review assets land here, beside the separation they describe.
#: Ignored by Git with the rest of `corpus/derived/`.
REVIEW_DIRNAME = "review"
REVIEW_PAGE = "index.html"

#: Loopback only, and stated as a constant so that the intent is greppable
#: rather than hidden in a call. This page shows unpublished work and reads
#: files from a private checkout; it has no business being reachable.
LOOPBACK = "127.0.0.1"

#: What the whitelist may serve. Small and closed: this server exists to hand a
#: browser a page and the artifacts that page is about, and nothing else.
CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
}


PAGE_TEMPLATE = "stem_observatory.html"


#: The page lives in a real file beside this module rather than in a string
#: literal, and that is a bug fix rather than tidiness. A template embedded in a
#: non-raw triple-quoted Python string is decoded by *Python's* parser before
#: the browser ever sees it, so a `\n` written in JavaScript silently became a
#: real newline in the middle of a string literal and the page failed to parse.
#: Every Python test passed while nothing executed. A `.html` file has one
#: reader, gets syntax highlighting, and cannot be escaped wrong.
PAGES = Path(__file__).resolve().parent / "pages"


def load_page(name: str) -> str:
    """Read one page template, or say which file is missing and from where."""
    target = PAGES / name
    try:
        return target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ObservatoryError(
            f"cannot read the page template at {target}: {exc.strerror or exc}. It ships beside "
            f"the module; an installation that lost it is incomplete."
        ) from exc


class ObservatoryError(Exception):
    """The exhibit could not be assembled from what is on disk."""


# ---------------------------------------------------------------------------
# The exhibit: a manifest, turned into something a page can render.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Lane:
    """One audible row.

    ``kind`` is what keeps the page honest and is not cosmetic. A ``stem`` is a
    model's assignment, a ``diagnostic`` is arithmetic performed on those
    assignments, and a ``source`` is the evidence itself. They are rendered
    differently because confusing them is the specific mistake this page could
    most easily cause.
    """

    id: str
    label: str
    kind: str  # "source" | "stem" | "diagnostic"
    caption: str
    url: str
    path: str
    hash: str
    duration_s: float
    sample_rate_hz: int
    channels: int
    peak: float
    rms: float
    shortcut: str | None = None
    audible: bool = False


@dataclass(frozen=True)
class Exhibit:
    """Everything the page needs, and nothing that needed a model to compute."""

    specimen_id: str
    lanes: list[Lane]
    provenance: list[tuple[str, str]]
    warnings: list[str]
    measurements: list[tuple[str, str]]
    #: URL path to the absolute file it serves. The server's whole whitelist.
    files: dict[str, Path] = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return max((lane.duration_s for lane in self.lanes), default=0.0)

    def payload(self) -> dict[str, Any]:
        """The JSON the page is handed. Lanes only; prose stays in the HTML."""
        return {
            "specimen_id": self.specimen_id,
            "duration_s": self.duration_s,
            "lanes": [asdict(lane) for lane in self.lanes],
        }


def display_model_name(manifest: SeparationManifest) -> str:
    """What to call the separator on screen, in upstream's own capitalization."""
    return manifest.separator.weights_repo.split("/")[-1]


def verify(repository_root: Path, artifact: AudioArtifact) -> Path:
    """Confirm an artifact is where the manifest says and is what it says.

    Checked before the page is built rather than discovered as a decode failure
    in a browser, because "the residual sounds like silence" and "the residual
    file is missing" must not look the same to a person judging a gate.
    """
    target = repository_root / artifact.path
    if not target.is_file():
        raise ObservatoryError(
            f"{artifact.path} is declared by the separation manifest and is not on disk. "
            f"Re-run `spectral-loom separate`; a review of artifacts that are not there would "
            f"be a review of nothing."
        )
    found = hash_file(target)
    if found != artifact.hash:
        raise ObservatoryError(
            f"{artifact.path} hashes to {found}, and the separation manifest recorded "
            f"{artifact.hash}. These are not the bytes that were separated, and this page will "
            f"not present them as though they were."
        )
    return target


def build_exhibit(
    manifest: SeparationManifest,
    review: SpecimenReview,
    repository_root: Path,
) -> Exhibit:
    """Turn a separation manifest into lanes, provenance, and a file whitelist.

    Pure apart from reading and hashing the files it is about, which is the one
    thing it may not take on trust. The ordering is deliberate: the source
    first, because it is the evidence and everything else is a claim about it;
    the stems in the separator's own order; the diagnostics last and last for a
    reason.
    """
    model = display_model_name(manifest)
    lanes: list[Lane] = []
    files: dict[str, Path] = {}

    source = repository_root / manifest.source_path
    if not source.is_file():
        raise ObservatoryError(
            f"the separated source is not at {manifest.source_path}. The stems describe audio "
            f"this checkout no longer has."
        )
    source_hash = hash_file(source)
    if source_hash != manifest.source_audio.hash:
        raise ObservatoryError(
            f"{manifest.source_path} hashes to {source_hash}, and the separation was performed "
            f"on {manifest.source_audio.hash}. Comparing stems against different source bytes "
            f"than they came from would be worse than not comparing them."
        )

    files["/audio/source"] = source
    lanes.append(
        Lane(
            id="source",
            label="Source mix",
            kind="source",
            caption=(
                f"The exact bytes {review.review.reviewer} accepted on "
                f"{review.review.reviewed_on}. The evidence; everything below is a claim about it."
            ),
            url="/audio/source",
            path=manifest.source_path,
            hash=manifest.source_audio.hash,
            duration_s=manifest.source_audio.duration_s,
            sample_rate_hz=manifest.source_audio.sample_rate_hz or 0,
            channels=manifest.source_audio.channels or 0,
            peak=0.0,
            rms=0.0,
            shortcut="0",
            audible=True,
        )
    )

    for index, stem in enumerate(manifest.stems, start=1):
        files[f"/audio/{stem.model_output}"] = verify(repository_root, stem.audio)
        lanes.append(
            Lane(
                id=stem.model_output,
                label=f"{model} · {stem.model_output}",
                kind="stem",
                caption=(
                    f"The signal {model} assigned to its “{stem.model_output}” output. Not a "
                    f"verified instrument, and not evidence about what the source contained."
                ),
                url=f"/audio/{stem.model_output}",
                path=stem.audio.path,
                hash=stem.audio.hash,
                duration_s=stem.audio.duration_s,
                sample_rate_hz=stem.audio.sample_rate_hz,
                channels=stem.audio.channels,
                peak=stem.audio.peak,
                rms=stem.audio.rms,
                shortcut=str(index) if index <= 9 else None,
            )
        )

    shortcuts = {"reconstruction": "M", "residual": "R"}
    for diagnostic in manifest.diagnostics:
        if diagnostic.audio is None:
            continue
        files[f"/audio/{diagnostic.id}"] = verify(repository_root, diagnostic.audio)
        lanes.append(
            Lane(
                id=diagnostic.id,
                label=f"Diagnostic · {diagnostic.id}",
                kind="diagnostic",
                caption=diagnostic.description,
                url=f"/audio/{diagnostic.id}",
                path=diagnostic.audio.path,
                hash=diagnostic.audio.hash,
                duration_s=diagnostic.audio.duration_s,
                sample_rate_hz=diagnostic.audio.sample_rate_hz,
                channels=diagnostic.audio.channels,
                peak=diagnostic.audio.peak,
                rms=diagnostic.audio.rms,
                shortcut=shortcuts.get(diagnostic.id),
            )
        )

    return Exhibit(
        specimen_id=manifest.specimen_id,
        lanes=lanes,
        provenance=_provenance_rows(manifest, review),
        warnings=list(manifest.warnings),
        measurements=_measurement_rows(manifest),
        files=files,
    )


def _provenance_rows(manifest: SeparationManifest, review: SpecimenReview) -> list[tuple[str, str]]:
    """What produced these files, flattened into label/value pairs.

    Everything a person would otherwise have to open two JSON documents to find,
    and nothing that would need interpreting. The page shows it behind a
    disclosure rather than on the surface, because provenance has to be *in
    reach* while auditioning without being what you are looking at.
    """
    separator = manifest.separator
    stage = manifest.provenance[0]
    parameters = {k: v for k, v in stage.parameters.items() if k != "device"}

    rows: list[tuple[str, str]] = [
        ("specimen", manifest.specimen_id),
        ("source", f"{manifest.source_path}"),
        ("source sha256", manifest.source_audio.hash),
        (
            "source observed",
            f"{manifest.source_audio.duration_s:.2f} s · "
            f"{manifest.source_audio.sample_rate_hz} Hz · {manifest.source_audio.channels} ch",
        ),
        (
            "accepted by",
            f"{review.review.reviewer} on {review.review.reviewed_on} "
            f"(gate 2; fitness as a specimen, not a claim about content)",
        ),
        ("review sha256", manifest.review_hash),
        ("separator code", f"{separator.code_distribution}=={separator.code_version}"),
        ("code sha256", separator.code_sha256),
        ("loaded with", separator.loaded_with),
        ("applied with", separator.applied_with),
        ("weights", f"{separator.weights_repo}@{separator.weights_revision}"),
        ("model signature", f"{separator.weights_variant}/{'+'.join(separator.model_signatures)}"),
        (
            "model format",
            f"{separator.model_sample_rate_hz} Hz · {separator.model_audio_channels} ch · "
            f"outputs {', '.join(separator.sources)}",
        ),
        ("backend", str(stage.parameters.get("device", "unrecorded"))),
        ("runtime", stage.runtime or "unrecorded"),
        ("started", stage.started_at.isoformat() if stage.started_at else "unrecorded"),
        (
            "elapsed",
            f"{stage.duration_ms / 1000:.2f} s" if stage.duration_ms is not None else "unrecorded",
        ),
        ("parameters", json.dumps(parameters, sort_keys=True)),
        ("cache key", manifest.cache_key),
        ("truth layer", f"{stage.truth_layer} — a model's opinion at an exact revision"),
    ]
    for stem in manifest.stems:
        rows.append((f"{stem.model_output} sha256", stem.audio.hash))
    return rows


def _measurement_rows(manifest: SeparationManifest) -> list[tuple[str, str]]:
    """The engineering diagnostics, rendered without a verdict attached."""
    rows: list[tuple[str, str]] = []
    for diagnostic in manifest.diagnostics:
        for key, value in sorted(diagnostic.measurements.items()):
            if key == "note":
                continue
            rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
            rows.append((f"{diagnostic.id}.{key}", str(rendered)))
    return rows


# ---------------------------------------------------------------------------
# The page.
# ---------------------------------------------------------------------------

_PAGE_TOKEN = "/*__EXHIBIT__*/"
_ROWS_TOKEN = "<!--__ROWS__-->"
_LANES_TOKEN = "<!--__LANES__-->"
_TITLE_TOKEN = "<!--__TITLE__-->"


def render(exhibit: Exhibit) -> str:
    """The whole page: one HTML file, no external anything."""
    return (
        load_page(PAGE_TEMPLATE)
        .replace(_TITLE_TOKEN, html.escape(exhibit.specimen_id))
        .replace(_LANES_TOKEN, _render_lanes(exhibit))
        .replace(_ROWS_TOKEN, _render_rows(exhibit))
        .replace(_PAGE_TOKEN, json.dumps(exhibit.payload()))
    )


def _render_lanes(exhibit: Exhibit) -> str:
    parts: list[str] = []
    for lane in exhibit.lanes:
        ident = html.escape(lane.id)
        key = (
            f"<kbd>{html.escape(lane.shortcut)}</kbd>"
            if lane.shortcut
            else '<span class="nokey"></span>'
        )
        detail = f"{lane.sample_rate_hz} Hz · {lane.channels} ch"
        if lane.kind != "source":
            detail += f" · peak {lane.peak:.3f} · rms {lane.rms:.4f}"
        parts.append(
            f'<div class="lane {html.escape(lane.kind)}" data-lane="{ident}">'
            f'  <div class="head">'
            f'    <div class="title">{key}<span class="name">{html.escape(lane.label)}</span></div>'
            f'    <div class="meta">{html.escape(detail)}</div>'
            f'    <div class="caption">{html.escape(lane.caption)}</div>'
            f'    <div class="buttons">'
            f'      <button data-act="mute" data-lane="{ident}">mute</button>'
            f'      <button data-act="solo" data-lane="{ident}">solo</button>'
            f"    </div>"
            f"  </div>"
            f'  <div class="wave"><canvas data-canvas="{ident}"></canvas></div>'
            f"</div>"
        )
    return "\n".join(parts)


def _render_rows(exhibit: Exhibit) -> str:
    def table(title: str, rows: list[tuple[str, str]], note: str = "") -> str:
        if not rows:
            return ""
        body = "".join(
            f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in rows
        )
        caption = f'<p class="note">{html.escape(note)}</p>' if note else ""
        return f"<h3>{html.escape(title)}</h3>{caption}<table>{body}</table>"

    warnings = (
        table("Warnings", [("", w) for w in exhibit.warnings])
        if exhibit.warnings
        else '<h3>Warnings</h3><p class="note">None recorded.</p>'
    )
    return (
        table("Provenance", exhibit.provenance)
        + table(
            "Engineering diagnostics",
            exhibit.measurements,
            "Measurements, not verdicts. Demucs is not trained to reconstruct additively and the "
            "outputs were written as 16-bit PCM, so a nonzero residual is expected. This project "
            "has no evidence for a pass threshold and asserts none.",
        )
        + warnings
    )


# ---------------------------------------------------------------------------
# The server.
# ---------------------------------------------------------------------------


def _handler(files: dict[str, Path], page: bytes) -> type[BaseHTTPRequestHandler]:
    """A handler that serves exactly one page and one fixed set of files.

    A whitelist rather than a document root, so there is no path to traverse:
    a request either names a URL the exhibit put in its own table, or it is a
    404. `SimpleHTTPRequestHandler` would have been fewer lines and would have
    exposed the checkout.

    Content type comes from the extension of the file on disk rather than from
    the request, because the whitelist is this project's own table and guessing
    from a URL a browser sent would be reading input to decide how to label
    output.
    """

    class Observatory(BaseHTTPRequestHandler):
        server_version = "spectral-loom-observatory"

        def do_GET(self) -> None:  # the stdlib names this method, not this project
            route = self.path.split("?", 1)[0]
            if route in {"/", "/index.html"}:
                self._send(page, "text/html; charset=utf-8")
                return
            target = files.get(route)
            if target is None:
                self.send_error(404, "no such artifact in this exhibit")
                return
            try:
                self._send(target.read_bytes(), CONTENT_TYPES.get(target.suffix, "audio/wav"))
            except OSError as exc:
                self.send_error(500, f"cannot read {route}: {exc}")

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:
            """Quiet. The page makes one request per lane and says so itself."""

    return Observatory


def write_page(
    repository_root: Path, specimen_id: str, page: str, filename: str = REVIEW_PAGE
) -> Path:
    """Put a rendered page on disk beside the artifacts it describes.

    Written as well as served, because an artifact you can point at is easier to
    reason about than one that only exists inside a process — and because
    `corpus/derived/` is already the ignored place derived things go.
    """
    target = repository_root / DERIVED_DIRNAME / specimen_id / REVIEW_DIRNAME / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return target


def serve(
    files: dict[str, Path],
    page: str,
    *,
    title: str,
    port: int = 0,
    open_browser: bool = True,
) -> None:
    """Serve one page and its whitelist on loopback until interrupted.

    Takes the whitelist rather than an exhibit, because two different review
    surfaces now need exactly this and nothing else from each other. That is
    the whole of what they share: a loopback socket, a fixed table of files,
    and no way to reach anything not in it.

    Port 0 by default: the kernel picks a free one, so two specimens can be
    open at once and nothing collides with whatever else is listening.
    """
    encoded = page.encode("utf-8")

    class Server(ThreadingHTTPServer):
        # Threading, because the page fetches every lane at once and a
        # single-threaded server would serialize several megabyte reads.
        daemon_threads = True
        allow_reuse_address = True

    try:
        httpd = Server((LOOPBACK, port), _handler(files, encoded))
    except OSError as exc:
        raise ObservatoryError(f"cannot listen on {LOOPBACK}:{port}: {exc}") from exc

    url = f"http://{LOOPBACK}:{httpd.server_address[1]}/"
    print(title)
    print(f"  {url}")
    print("  loopback only; nothing here reaches the network")
    print("  Ctrl-C to stop")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
