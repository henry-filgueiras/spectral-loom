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
        _TEMPLATE.replace(_TITLE_TOKEN, html.escape(exhibit.specimen_id))
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


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stem Observatory — <!--__TITLE__--></title>
<style>
:root {
  --bg: #0d1013; --panel: #14181d; --line: #232a31; --ink: #d7dee5;
  --dim: #8b97a3; --accent: #6fd0c0; --stem: #7aa7ff; --diag: #c99bd8;
  --warn: #e0a76a;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --labels: 320px;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 13px/1.5 var(--mono); -webkit-font-smoothing: antialiased;
}
header {
  position: sticky; top: 0; z-index: 5; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: 12px 18px;
}
h1 { margin: 0 0 2px; font-size: 14px; font-weight: 600; letter-spacing: .02em; }
h1 span { color: var(--accent); }
.sub { color: var(--dim); font-size: 12px; }
.transport { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
button {
  font: inherit; background: #1b2229; color: var(--ink); border: 1px solid var(--line);
  border-radius: 4px; padding: 3px 9px; cursor: pointer;
}
button:hover { border-color: var(--accent); }
button.on { background: var(--accent); color: #06201c; border-color: var(--accent); }
button.off { opacity: .45; }
.clock { font-variant-numeric: tabular-nums; color: var(--accent); min-width: 11ch; }
kbd {
  display: inline-block; min-width: 1.6em; text-align: center; border: 1px solid var(--line);
  border-bottom-width: 2px; border-radius: 3px; padding: 0 4px; margin-right: 7px;
  color: var(--dim); font-size: 11px; background: #10151a;
}
.nokey { display: inline-block; width: 1.6em; margin-right: 7px; }
main { padding: 14px 18px 40px; }
/* The label column is a fixed width so that the playhead overlay, which is
   taken out of flow, can be positioned against the same edge. Placing the
   overlay as a grid item instead does not work: `grid-row: 1 / -1` resolves
   against the *explicit* grid, which has one row here, so it would land in the
   first waveform's cell and shunt every lane one place along. */
#stack { position: relative; display: grid; grid-template-columns: var(--labels) 1fr; }
.lane { display: contents; }
.head {
  border-top: 1px solid var(--line); padding: 10px 14px 10px 0;
}
/* Centred rather than top-aligned: the row's height comes from the label
   column, and a waveform pinned to the top of a taller row reads as though it
   belongs to the lane above it. */
.wave { border-top: 1px solid var(--line); display: flex; align-items: center; }
.wave canvas { display: block; width: 100%; height: 88px; }
.lane.stem .name { color: var(--stem); }
.lane.diagnostic .name { color: var(--diag); }
.lane.source .name { color: var(--accent); }
.name { font-weight: 600; }
.meta { color: var(--dim); font-size: 11px; margin: 2px 0 0 2.3em; }
.caption { color: var(--dim); font-size: 11px; margin: 4px 0 6px 2.3em; max-width: 42ch; }
.buttons { margin-left: 2.3em; display: flex; gap: 6px; }
.buttons button { font-size: 11px; padding: 1px 8px; }
#overlay, #hit {
  position: absolute; top: 0; bottom: 0; left: var(--labels); right: 0;
  pointer-events: none;
}
#overlay { z-index: 3; }
#hit { z-index: 4; pointer-events: auto; cursor: crosshair; }
#playhead {
  position: absolute; top: 0; bottom: 0; width: 1px; background: var(--accent);
  box-shadow: 0 0 6px var(--accent); left: 0;
}
#loop {
  position: absolute; top: 0; bottom: 0; background: rgba(111,208,192,.10);
  border-left: 1px solid rgba(111,208,192,.5); border-right: 1px solid rgba(111,208,192,.5);
  display: none;
}
details { margin-top: 26px; border-top: 1px solid var(--line); padding-top: 12px; }
summary { cursor: pointer; color: var(--dim); }
summary:hover { color: var(--ink); }
h3 { font-size: 12px; margin: 18px 0 6px; color: var(--accent); letter-spacing: .04em;
     text-transform: uppercase; }
table { border-collapse: collapse; width: 100%; }
th, td {
  text-align: left; vertical-align: top; padding: 2px 12px 2px 0; font-weight: 400;
  border-bottom: 1px solid #1a2027; word-break: break-all;
}
th { color: var(--dim); width: 20ch; white-space: nowrap; }
.note { color: var(--dim); max-width: 88ch; margin: 4px 0 8px; }
.keys { color: var(--dim); font-size: 11px; margin-top: 8px; }
.keys b { color: var(--ink); font-weight: 600; }
#status { color: var(--warn); margin: 10px 0 0; }
</style>
</head>
<body>
<header>
  <h1>Stem Observatory — <span><!--__TITLE__--></span></h1>
  <div class="sub">
    Lane names are the separator's own output names. They are not verified instruments,
    and an empty lane is a failure to assign rather than evidence of absence.
  </div>
  <div class="transport">
    <button id="play">play</button>
    <button id="stop">stop</button>
    <span class="clock" id="clock">0:00.00 / 0:00.00</span>
    <button id="loopin">[ in</button>
    <button id="loopout">out ]</button>
    <button id="loopclear">clear loop</button>
    <span class="clock" id="loopinfo"></span>
  </div>
  <div class="keys">
    <b>space</b> play/pause · <b>0</b> source · <b>1-4</b> solo one output · <b>A</b> all four
    outputs · <b>M</b> rendered sum · <b>R</b> residual · <b>[</b> <b>]</b> loop bounds ·
    <b>&larr;</b> <b>&rarr;</b> seek 5 s · <b>esc</b> clear solo and loop
  </div>
  <p id="status">decoding…</p>
</header>
<main>
  <div id="stack">
    <!--__LANES__-->
    <div id="overlay"><div id="loop"></div><div id="playhead"></div></div>
    <div id="hit"></div>
  </div>
  <details>
    <summary>Provenance, diagnostics, and warnings</summary>
    <!--__ROWS__-->
  </details>
</main>
<script>
const EXHIBIT = /*__EXHIBIT__*/;
const lanes = EXHIBIT.lanes;
const ctx = new (window.AudioContext || window.webkitAudioContext)();
const master = ctx.createGain();
master.connect(ctx.destination);

const gains = {}, buffers = {}, muted = {}, solo = new Set();
lanes.forEach(l => {
  const g = ctx.createGain();
  g.gain.value = 0;
  g.connect(master);
  gains[l.id] = g;
  muted[l.id] = false;
});
lanes.filter(l => l.audible).forEach(l => solo.add(l.id));

let sources = [], playing = false, offset = 0, startedAt = 0;
let duration = EXHIBIT.duration_s;
let loop = { a: null, b: null };

/* ---- gain ------------------------------------------------------------- */
function audible(id) {
  if (solo.size) return solo.has(id);
  return !muted[id];
}
function applyGains() {
  const now = ctx.currentTime;
  lanes.forEach(l => gains[l.id].gain.setTargetAtTime(audible(l.id) ? 1 : 0, now, 0.012));
  document.querySelectorAll('[data-act]').forEach(b => {
    const id = b.dataset.lane, act = b.dataset.act;
    const on = act === 'solo' ? solo.has(id) : muted[id];
    b.classList.toggle('on', on);
  });
  document.querySelectorAll('.lane').forEach(el => {
    el.style.opacity = audible(el.dataset.lane) ? '1' : '.42';
  });
}

/* ---- transport -------------------------------------------------------- */
function looping() { return loop.a !== null && loop.b !== null && loop.b > loop.a; }

function stopSources() {
  sources.forEach(s => { try { s.stop(); } catch (e) {} });
  sources = [];
}
function start(at) {
  stopSources();
  if (looping()) at = (at < loop.a || at >= loop.b) ? loop.a : at;
  at = Math.max(0, Math.min(at, duration - 0.01));
  const when = ctx.currentTime + 0.04;
  sources = lanes.map(l => {
    const buf = buffers[l.id];
    if (!buf) return null;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    if (looping()) { src.loop = true; src.loopStart = loop.a; src.loopEnd = loop.b; }
    src.connect(gains[l.id]);
    src.start(when, at);
    return src;
  }).filter(Boolean);
  startedAt = when;
  offset = at;
  playing = true;
  document.getElementById('play').textContent = 'pause';
}
function pause() {
  offset = position();
  stopSources();
  playing = false;
  document.getElementById('play').textContent = 'play';
}
function position() {
  if (!playing) return offset;
  let p = offset + (ctx.currentTime - startedAt);
  if (p < 0) p = 0;
  if (looping() && p > loop.b) {
    const span = loop.b - loop.a;
    p = loop.a + ((p - loop.a) % span);
  }
  return Math.min(p, duration);
}
function seek(to) {
  if (playing) start(to); else { offset = Math.max(0, Math.min(to, duration)); draw(); }
}
function toggle() {
  if (ctx.state === 'suspended') ctx.resume();
  playing ? pause() : start(offset >= duration - 0.02 ? 0 : offset);
}

/* ---- solo helpers ------------------------------------------------------ */
function soloOnly(ids) {
  solo.clear();
  ids.forEach(i => solo.add(i));
  applyGains();
}
const stemIds = lanes.filter(l => l.kind === 'stem').map(l => l.id);

/* ---- drawing ----------------------------------------------------------- */
function peaksFor(buffer, width) {
  const n = buffer.length, block = Math.max(1, Math.floor(n / width));
  const out = new Float32Array(width * 2);
  const chans = [];
  for (let c = 0; c < buffer.numberOfChannels; c++) chans.push(buffer.getChannelData(c));
  for (let x = 0; x < width; x++) {
    let lo = 0, hi = 0;
    const s = x * block, e = Math.min(n, s + block);
    for (const data of chans) {
      for (let i = s; i < e; i++) {
        const v = data[i];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    out[x * 2] = lo; out[x * 2 + 1] = hi;
  }
  return out;
}
const colours = { source: '#6fd0c0', stem: '#7aa7ff', diagnostic: '#c99bd8' };
function drawLane(lane) {
  const canvas = document.querySelector(`[data-canvas="${lane.id}"]`);
  const buf = buffers[lane.id];
  if (!canvas || !buf) return;
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.floor(canvas.clientWidth));
  const h = Math.max(1, Math.floor(canvas.clientHeight));
  canvas.width = w * dpr; canvas.height = h * dpr;
  const g = canvas.getContext('2d');
  g.scale(dpr, dpr);
  g.clearRect(0, 0, w, h);
  g.strokeStyle = '#1d242b';
  g.beginPath(); g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke();
  const p = peaksFor(buf, w);
  g.strokeStyle = colours[lane.kind] || '#7aa7ff';
  g.globalAlpha = 0.9;
  g.beginPath();
  for (let x = 0; x < w; x++) {
    const lo = p[x * 2], hi = p[x * 2 + 1];
    g.moveTo(x + 0.5, h / 2 - hi * (h / 2 - 2));
    g.lineTo(x + 0.5, h / 2 - lo * (h / 2 - 2));
  }
  g.stroke();
}
function fmt(t) {
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
}
function draw() {
  const hit = document.getElementById('hit');
  const w = hit.clientWidth;
  const p = position();
  document.getElementById('playhead').style.left = `${(p / duration) * w}px`;
  document.getElementById('clock').textContent = `${fmt(p)} / ${fmt(duration)}`;
  const el = document.getElementById('loop');
  if (looping()) {
    el.style.display = 'block';
    el.style.left = `${(loop.a / duration) * w}px`;
    el.style.width = `${((loop.b - loop.a) / duration) * w}px`;
  } else {
    el.style.display = 'none';
  }
  document.getElementById('loopinfo').textContent =
    looping() ? `loop ${fmt(loop.a)} - ${fmt(loop.b)}` : '';
}
function frame() { draw(); requestAnimationFrame(frame); }

/* ---- wiring ------------------------------------------------------------ */
document.getElementById('play').onclick = toggle;
document.getElementById('stop').onclick = () => { pause(); offset = 0; draw(); };
document.getElementById('loopin').onclick = () => { loop.a = position(); normaliseLoop(); };
document.getElementById('loopout').onclick = () => { loop.b = position(); normaliseLoop(); };
document.getElementById('loopclear').onclick = () => { loop = { a: null, b: null }; restart(); };
function normaliseLoop() {
  if (loop.a !== null && loop.b !== null && loop.b < loop.a) {
    const t = loop.a; loop.a = loop.b; loop.b = t;
  }
  restart();
}
function restart() { if (playing) start(position()); draw(); }

document.querySelectorAll('[data-act]').forEach(b => {
  b.onclick = () => {
    const id = b.dataset.lane;
    if (b.dataset.act === 'solo') {
      solo.has(id) ? solo.delete(id) : solo.add(id);
    } else {
      muted[id] = !muted[id];
    }
    applyGains();
  };
});
document.getElementById('hit').onclick = e => {
  const r = e.currentTarget.getBoundingClientRect();
  seek(((e.clientX - r.left) / r.width) * duration);
};
window.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (k === ' ') { e.preventDefault(); toggle(); return; }
  if (k === '0') { soloOnly(['source']); return; }
  if (k >= '1' && k <= '9') {
    const lane = lanes.find(l => l.shortcut === k);
    if (lane) soloOnly([lane.id]);
    return;
  }
  if (k === 'a' || k === 'A') { soloOnly(stemIds); return; }
  if (k === 'm' || k === 'M') { if (buffers.reconstruction) soloOnly(['reconstruction']); return; }
  if (k === 'r' || k === 'R') { if (buffers.residual) soloOnly(['residual']); return; }
  if (k === '[') { loop.a = position(); normaliseLoop(); return; }
  if (k === ']') { loop.b = position(); normaliseLoop(); return; }
  if (k === 'ArrowLeft') { e.preventDefault(); seek(position() - 5); return; }
  if (k === 'ArrowRight') { e.preventDefault(); seek(position() + 5); return; }
  if (k === 'Escape') {
    solo.clear();
    lanes.forEach(l => { muted[l.id] = false; });
    solo.add('source');
    loop = { a: null, b: null };
    applyGains();
    restart();
  }
});
let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => lanes.forEach(drawLane), 120);
});

/* ---- load -------------------------------------------------------------- */
const status = document.getElementById('status');
(async () => {
  let done = 0;
  await Promise.all(lanes.map(async lane => {
    const response = await fetch(lane.url);
    if (!response.ok) throw new Error(`${lane.url}: ${response.status}`);
    const bytes = await response.arrayBuffer();
    buffers[lane.id] = await ctx.decodeAudioData(bytes);
    done += 1;
    status.textContent = `decoding… ${done}/${lanes.length}`;
    drawLane(lane);
  })).catch(err => { status.textContent = `failed: ${err.message}`; throw err; });
  duration = Math.max(...lanes.map(l => buffers[l.id].duration));
  status.textContent = '';
  status.style.display = 'none';
  applyGains();
  draw();
})();
frame();
</script>
</body>
</html>
"""
