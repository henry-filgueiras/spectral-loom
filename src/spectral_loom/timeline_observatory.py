"""The Timeline Observatory: an instrument for falsifying a timeline by ear.

Gate 4 is passed by a human spot-checking events against the audio. That is the
whole reason this exists, and — as with the Stem Observatory — it is also the
whole reason it is small. A gate whose evidence is inconvenient to examine is a
gate that gets waved through, and "open the JSON, find an onset at 12.383 s,
seek a media player there, and try to remember what you heard" is inconvenient
enough to guarantee it.

**This is not roadmap gate 6.** The analytical projection is a general instrument
that will judge every later gate. This is one page with one job: make answering
*"is that actually an audible onset?"* cost a click and a keypress.

Four things it is careful about.

**The rule is visible, not implied.** The activity lane draws the measured level
curve with the enter and exit thresholds on it, so an interval's existence can be
read off the picture rather than reverse-engineered from a number. A person who
disagrees with an interval can see exactly which frame crossed which line.

**Nothing is styled as a probability.** Onset markers are all the same height,
because this detector produces no calibrated confidence and a marker whose height
varied would be read as one. The raw flux and the margin over threshold are
shown as numbers, beside the threshold they beat.

**Absence renders as absence of inference.** A track with no intervals says
"0 activity intervals inferred under this rule and these thresholds" — never
"silent". `principle:1` applied to a count instead of to a label.

**It cannot become an editor.** The page reads the timeline over HTTP and holds
no writer. The threshold explorer recomputes candidate intervals in the browser,
draws them dashed under a banner that calls them hypothetical, and writes nothing
anywhere; and because it re-implements a rule that lives in Python, it checks its
own arithmetic against the compiled intervals whenever the sliders are back at
the compiled values, and says so on screen if the two disagree.

What it shares with :mod:`spectral_loom.observatory` is the loopback server, its
fixed whitelist, and the helper that refuses to present a file whose hash has
changed. That is all they have in common and all they should: a socket, a table
of files, and no path to anything not in it.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spectral_loom.contracts import Provenance, SeparationManifest, SongTimeline
from spectral_loom.hashing import hash_file
from spectral_loom.observatory import ObservatoryError, verify
from spectral_loom.timeline import INTERVAL_STAGE, MEASURE_STAGE, ONSET_STAGE

#: The page lands beside the Stem Observatory's, under the same ignored
#: directory, with a name that says which instrument it is.
TIMELINE_PAGE = "timeline.html"

#: Where the compiled document is served from. The page reads the timeline
#: itself rather than a summary of it, so the record an inspector shows is the
#: record on disk and not a second rendering of it that could drift.
TIMELINE_URL = "/timeline.json"


@dataclass(frozen=True)
class TrackView:
    """One model output, as the page needs it: audio, and where its claims came from."""

    id: str
    model_output: str
    label: str
    url: str
    path: str
    hash: str
    shortcut: str


@dataclass(frozen=True)
class TimelineExhibit:
    """Everything the page is handed, and nothing it has to be trusted about."""

    specimen_id: str
    duration_s: float
    source_url: str
    source_path: str
    source_hash: str
    source_sample_rate_hz: int
    source_channels: int
    timeline_url: str
    timeline_hash: str
    tracks: list[TrackView]
    #: The interval rule's own thresholds, read off the provenance rather than
    #: restated, so the lines drawn on screen are the lines that ran.
    enter_dbfs: float
    exit_dbfs: float
    min_duration_s: float
    merge_gap_s: float
    provenance: list[tuple[str, str]]
    parameters: list[tuple[str, str]]
    files: dict[str, Path] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "specimen_id": self.specimen_id,
            "duration_s": self.duration_s,
            "timeline_url": self.timeline_url,
            "source": {
                "url": self.source_url,
                "path": self.source_path,
                "hash": self.source_hash,
            },
            "tracks": [
                {
                    "id": track.id,
                    "model_output": track.model_output,
                    "label": track.label,
                    "url": track.url,
                    "path": track.path,
                    "hash": track.hash,
                    "shortcut": track.shortcut,
                }
                for track in self.tracks
            ],
            "rule": {
                "enter_dbfs": self.enter_dbfs,
                "exit_dbfs": self.exit_dbfs,
                "min_duration_s": self.min_duration_s,
                "merge_gap_s": self.merge_gap_s,
            },
        }


def _stage(timeline: SongTimeline, name: str) -> Provenance:
    for entry in timeline.provenance:
        if entry.stage == name:
            return entry
    raise ObservatoryError(
        f"this timeline has no {name!r} stage in its provenance, so the page cannot show which "
        f"rule produced its events. It was written by a different compiler than this one."
    )


def _number(parameters: dict[str, Any], key: str, stage: str) -> float:
    value = parameters.get(key)
    if not isinstance(value, int | float):
        raise ObservatoryError(
            f"the {stage!r} stage does not record {key!r} as a number, and this page will not "
            f"draw a threshold it cannot read off the document"
        )
    return float(value)


def build_exhibit(
    timeline: SongTimeline,
    timeline_path: Path,
    manifest: SeparationManifest,
    repository_root: Path,
) -> TimelineExhibit:
    """Turn a compiled timeline into lanes, a whitelist, and the rule to draw.

    Pure apart from hashing the files it is about, which is the one thing it may
    not take on trust: "the onset lane is empty" and "the stem file is missing"
    must not look the same to somebody judging a gate.
    """
    interval_stage = _stage(timeline, INTERVAL_STAGE)
    _stage(timeline, MEASURE_STAGE)
    onset_stage = _stage(timeline, ONSET_STAGE)
    rule = dict(interval_stage.parameters)

    source = repository_root / manifest.source_path
    if not source.is_file():
        raise ObservatoryError(
            f"the recording this timeline is about is not at {manifest.source_path}. Every "
            f"event here is a time on that recording, and there is nothing to check them "
            f"against."
        )
    source_hash = hash_file(source)
    if source_hash != timeline.source_audio.hash:
        raise ObservatoryError(
            f"{manifest.source_path} hashes to {source_hash}, and this timeline is about "
            f"{timeline.source_audio.hash}. Checking events against different bytes than they "
            f"were measured from would be worse than not checking them."
        )

    files: dict[str, Path] = {"/audio/source": source, TIMELINE_URL: timeline_path}
    tracks: list[TrackView] = []
    by_output = {stem.model_output: stem for stem in manifest.stems}

    for index, track in enumerate(timeline.tracks, start=1):
        output = track.id.split(".")[-1]
        stem = by_output.get(output)
        if stem is None:
            raise ObservatoryError(
                f"timeline track {track.id!r} has no matching output in the separation "
                f"manifest, so its claims cannot be played against anything"
            )
        if stem.audio.path != track.source:
            raise ObservatoryError(
                f"timeline track {track.id!r} cites {track.source} and the separation manifest "
                f"puts that output at {stem.audio.path}"
            )
        files[f"/audio/{output}"] = verify(repository_root, stem.audio)
        tracks.append(
            TrackView(
                id=track.id,
                model_output=output,
                label=track.role or track.id,
                url=f"/audio/{output}",
                path=stem.audio.path,
                hash=stem.audio.hash,
                shortcut=str(index) if index <= 9 else "",
            )
        )

    return TimelineExhibit(
        specimen_id=timeline.specimen_id,
        duration_s=timeline.source_audio.duration_s,
        source_url="/audio/source",
        source_path=manifest.source_path,
        source_hash=source_hash,
        source_sample_rate_hz=timeline.source_audio.sample_rate_hz or 0,
        source_channels=timeline.source_audio.channels or 0,
        timeline_url=TIMELINE_URL,
        timeline_hash=hash_file(timeline_path),
        tracks=tracks,
        enter_dbfs=_number(rule, "enter_dbfs", INTERVAL_STAGE),
        exit_dbfs=_number(rule, "exit_dbfs", INTERVAL_STAGE),
        min_duration_s=_number(rule, "min_duration_s", INTERVAL_STAGE),
        merge_gap_s=_number(rule, "merge_gap_s", INTERVAL_STAGE),
        provenance=_provenance_rows(timeline, timeline_path, repository_root),
        parameters=_parameter_rows(interval_stage, onset_stage),
        files=files,
    )


def _provenance_rows(
    timeline: SongTimeline, timeline_path: Path, repository_root: Path
) -> list[tuple[str, str]]:
    """The lineage, flattened, so it is in reach without being what you look at."""
    rows: list[tuple[str, str]] = [
        ("specimen", timeline.specimen_id),
        ("timeline", str(timeline_path.relative_to(repository_root))),
        ("timeline sha256", hash_file(timeline_path)),
        ("schema", f"{timeline.schema_id} {timeline.schema_version}"),
        ("source sha256", timeline.source_audio.hash),
        (
            "source observed",
            f"{timeline.source_audio.duration_s:.2f} s · "
            f"{timeline.source_audio.sample_rate_hz} Hz · {timeline.source_audio.channels} ch",
        ),
        ("time unit", timeline.time_unit),
    ]
    for entry in timeline.provenance:
        rows.append(
            (
                f"stage {entry.stage}",
                f"{entry.truth_layer} · {entry.tool} · {entry.tool_revision}",
            )
        )
    return rows


def _parameter_rows(interval: Provenance, onset: Provenance) -> list[tuple[str, str]]:
    """Exactly the parameters that decided an interval or an onset."""
    rows: list[tuple[str, str]] = []
    for label, entry in (("activity.interval", interval), ("onset.spectral_flux", onset)):
        for key in sorted(entry.parameters):
            value = entry.parameters[key]
            rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
            rows.append((f"{label}.{key}", str(rendered)))
    return rows


# ---------------------------------------------------------------------------
# The page.
# ---------------------------------------------------------------------------

_EXHIBIT_TOKEN = "/*__EXHIBIT__*/"
_ROWS_TOKEN = "<!--__ROWS__-->"
_TITLE_TOKEN = "<!--__TITLE__-->"
_TRACKS_TOKEN = "<!--__TRACKS__-->"


def render(exhibit: TimelineExhibit) -> str:
    """The whole page: one HTML file, no external anything."""
    return (
        _TEMPLATE.replace(_TITLE_TOKEN, html.escape(exhibit.specimen_id))
        .replace(_TRACKS_TOKEN, _render_track_buttons(exhibit))
        .replace(_ROWS_TOKEN, _render_rows(exhibit))
        .replace(_EXHIBIT_TOKEN, json.dumps(exhibit.payload()))
    )


def _render_track_buttons(exhibit: TimelineExhibit) -> str:
    parts = ['<button data-track="__source__" id="pick-source"><kbd>0</kbd>source mix</button>']
    for track in exhibit.tracks:
        key = f"<kbd>{html.escape(track.shortcut)}</kbd>" if track.shortcut else ""
        parts.append(
            f'<button data-track="{html.escape(track.id)}">'
            f"{key}{html.escape(track.model_output)}</button>"
        )
    return "\n".join(parts)


def _render_rows(exhibit: TimelineExhibit) -> str:
    def table(title: str, rows: list[tuple[str, str]], note: str = "") -> str:
        if not rows:
            return ""
        body = "".join(
            f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in rows
        )
        caption = f'<p class="note">{html.escape(note)}</p>' if note else ""
        return f"<h3>{html.escape(title)}</h3>{caption}<table>{body}</table>"

    return table("Provenance", exhibit.provenance) + table(
        "Parameters that decided these events",
        exhibit.parameters,
        "Everything here is in the timeline and in its cache key. Changing any of it is a "
        "different question, not a better answer to this one.",
    )


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Timeline Observatory — <!--__TITLE__--></title>
<style>
:root {
  --bg: #0d1013; --panel: #14181d; --line: #232a31; --ink: #d7dee5;
  --dim: #8b97a3; --accent: #6fd0c0; --stem: #7aa7ff; --onset: #e0a76a;
  --interval: #7fd18a; --hypo: #c99bd8; --warn: #e0776a;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --labels: 300px;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 13px/1.5 var(--mono); -webkit-font-smoothing: antialiased;
}
header {
  position: sticky; top: 0; z-index: 6; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: 10px 18px;
}
h1 { margin: 0 0 2px; font-size: 14px; font-weight: 600; letter-spacing: .02em; }
h1 span { color: var(--accent); }
.sub { color: var(--dim); font-size: 12px; max-width: 100ch; }
.row { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.row .sep { width: 1px; height: 18px; background: var(--line); margin: 0 4px; }
button {
  font: inherit; background: #1b2229; color: var(--ink); border: 1px solid var(--line);
  border-radius: 4px; padding: 3px 9px; cursor: pointer;
}
button:hover { border-color: var(--accent); }
button.on { background: var(--accent); color: #06201c; border-color: var(--accent); }
button.on kbd { color: #06201c; border-color: #06201c; background: transparent; }
label.opt { color: var(--dim); display: inline-flex; align-items: center; gap: 5px; }
input[type=number] {
  font: inherit; width: 6.5ch; background: #10151a; color: var(--ink);
  border: 1px solid var(--line); border-radius: 3px; padding: 1px 4px;
}
.clock { font-variant-numeric: tabular-nums; color: var(--accent); min-width: 12ch; }
kbd {
  display: inline-block; min-width: 1.5em; text-align: center; border: 1px solid var(--line);
  border-bottom-width: 2px; border-radius: 3px; padding: 0 4px; margin-right: 6px;
  color: var(--dim); font-size: 11px; background: #10151a;
}
.keys { color: var(--dim); font-size: 11px; margin-top: 8px; }
.keys b { color: var(--ink); font-weight: 600; }
main { padding: 12px 18px 40px; }
#stack { position: relative; display: grid; grid-template-columns: var(--labels) 1fr; }
.lane { display: contents; }
.head { border-top: 1px solid var(--line); padding: 8px 14px 8px 0; }
.wave { border-top: 1px solid var(--line); display: flex; align-items: center; }
/* An explicit CSS height on every canvas. Without one a canvas with only
   `width: 100%` scales to preserve its attribute aspect ratio, which on a wide
   window makes a 72-pixel lane six hundred pixels tall and pushes the lane
   below it off the screen — and lanes you cannot see at once are lanes you
   cannot compare. The drawing code reads clientWidth/clientHeight, so these are
   the sizes it renders at. */
.wave canvas { display: block; width: 100%; height: 76px; }
.lane.activity .wave canvas { height: 118px; }
.lane.onsets .wave canvas { height: 84px; }
.name { font-weight: 600; }
.lane.source .name { color: var(--accent); }
.lane.stem .name { color: var(--stem); }
.lane.activity .name { color: var(--interval); }
.lane.onsets .name { color: var(--onset); }
.meta { color: var(--dim); font-size: 11px; margin-top: 2px; }
.caption { color: var(--dim); font-size: 11px; margin-top: 4px; max-width: 40ch; }
.empty { color: var(--warn); font-size: 11px; margin-top: 4px; max-width: 40ch; }
#overlay, #hit {
  position: absolute; top: 0; bottom: 0; left: var(--labels); right: 0; pointer-events: none;
}
#overlay { z-index: 3; }
#hit { z-index: 4; pointer-events: auto; cursor: crosshair; }
#playhead {
  position: absolute; top: 0; bottom: 0; width: 1px; background: var(--accent);
  box-shadow: 0 0 6px var(--accent); left: 0;
}
#loop {
  position: absolute; top: 0; bottom: 0; background: rgba(111,208,192,.10);
  border-left: 1px solid rgba(111,208,192,.55); border-right: 1px solid rgba(111,208,192,.55);
  display: none;
}
#inspector {
  margin-top: 18px; border: 1px solid var(--line); border-radius: 5px; background: var(--panel);
  padding: 12px 14px;
}
#inspector h2 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase;
  letter-spacing: .05em; color: var(--onset); }
#inspector table { width: 100%; }
#inspector .hint { color: var(--dim); }
details { margin-top: 22px; border-top: 1px solid var(--line); padding-top: 10px; }
details.raw { margin-top: 10px; border: 0; padding-top: 0; }
summary { cursor: pointer; color: var(--dim); }
summary:hover { color: var(--ink); }
pre { white-space: pre-wrap; word-break: break-all; color: var(--dim); font-size: 11px;
  max-height: 40vh; overflow: auto; }
h3 { font-size: 12px; margin: 16px 0 6px; color: var(--accent); letter-spacing: .04em;
     text-transform: uppercase; }
table { border-collapse: collapse; width: 100%; }
th, td {
  text-align: left; vertical-align: top; padding: 2px 12px 2px 0; font-weight: 400;
  border-bottom: 1px solid #1a2027; word-break: break-all;
}
th { color: var(--dim); width: 26ch; white-space: nowrap; }
.note { color: var(--dim); max-width: 92ch; margin: 4px 0 8px; }
#status { color: var(--warn); margin: 8px 0 0; }
#hypobanner { color: var(--hypo); margin: 6px 0 0; display: none; }
#hypobanner.bad { color: var(--warn); }
</style>
</head>
<body>
<header>
  <h1>Timeline Observatory — <span><!--__TITLE__--></span></h1>
  <div class="sub">
    Track names are the separator's own output labels, not verified instruments. An empty lane
    means this detector inferred nothing there, which is a statement about the detector and not
    about the recording.
  </div>
  <div class="row" id="tracks"><!--__TRACKS__--></div>
  <div class="row">
    <button id="play">play</button>
    <button id="stop">stop</button>
    <span class="clock" id="clock">0:00.00 / 0:00.00</span>
    <span class="sep"></span>
    <button id="listen">listening: stem</button>
    <span class="sep"></span>
    <button id="prevOnset">&#8592; onset</button>
    <button id="nextOnset">onset &#8594;</button>
    <button id="prevInterval">&#8592; interval</button>
    <button id="nextInterval">interval &#8594;</button>
    <span class="sep"></span>
    <button id="fit">fit</button>
    <button id="zoomOut">&#8722;</button>
    <button id="zoomIn">+</button>
    <span class="clock" id="viewinfo"></span>
  </div>
  <div class="row">
    <label class="opt">audition pre
      <input type="number" id="pre" value="250" step="50" min="0"> ms</label>
    <label class="opt">post
      <input type="number" id="post" value="400" step="50" min="0"> ms</label>
    <label class="opt">interval margin
      <input type="number" id="margin" value="250" step="50" min="0"> ms</label>
    <span class="sep"></span>
    <label class="opt"><input type="checkbox" id="hypo"> hypothetical thresholds</label>
    <label class="opt">enter <input type="number" id="hypoEnter" step="1"> dBFS</label>
    <label class="opt">exit <input type="number" id="hypoExit" step="1"> dBFS</label>
  </div>
  <div class="keys">
    <b>space</b> play/pause · <b>0</b> source · <b>1-4</b> model output · <b>S</b> swap stem/source
    · <b>N</b>/<b>P</b> next/previous onset · <b>I</b>/<b>shift-I</b> next/previous interval ·
    <b>enter</b> audition the selected claim · <b>[</b> <b>]</b> loop bounds · <b>F</b> fit ·
    <b>-</b>/<b>=</b> zoom · <b>&larr;</b> <b>&rarr;</b> seek 5 s · <b>esc</b> clear
  </div>
  <p id="hypobanner"></p>
  <p id="status">loading…</p>
</header>
<main>
  <div id="stack">
    <div class="lane source" data-lane="source">
      <div class="head">
        <div class="name">Source mix</div>
        <div class="meta" id="sourceMeta"></div>
        <div class="caption">The recording every event time refers to. The evidence.</div>
      </div>
      <div class="wave"><canvas data-canvas="source" height="72"></canvas></div>
    </div>
    <div class="lane stem" data-lane="stem">
      <div class="head">
        <div class="name" id="stemName">model output</div>
        <div class="meta" id="stemMeta"></div>
        <div class="caption">The artifact the events below were measured in.</div>
      </div>
      <div class="wave"><canvas data-canvas="stem" height="72"></canvas></div>
    </div>
    <div class="lane activity" data-lane="activity">
      <div class="head">
        <div class="name">activity.sample &amp; activity.interval</div>
        <div class="meta" id="activityMeta"></div>
        <div class="caption" id="activityCaption"></div>
        <div class="empty" id="activityEmpty"></div>
      </div>
      <div class="wave"><canvas data-canvas="activity" height="110"></canvas></div>
    </div>
    <div class="lane onsets" data-lane="onsets">
      <div class="head">
        <div class="name">onset</div>
        <div class="meta" id="onsetMeta"></div>
        <div class="caption">
          Markers are all the same height. This detector reports no calibrated confidence, and a
          marker whose height varied would be read as one. The dot is the raw flux value on a
          scale from zero to the largest in this track.
        </div>
        <div class="empty" id="onsetEmpty"></div>
      </div>
      <div class="wave"><canvas data-canvas="onsets" height="80"></canvas></div>
    </div>
    <div id="overlay"><div id="loop"></div><div id="playhead"></div></div>
    <div id="hit"></div>
  </div>

  <div id="inspector">
    <h2>Selected claim</h2>
    <div id="inspectorBody" class="hint">
      Click an onset marker or an interval to select it. <b>Enter</b> auditions the selection:
      it loops a short window around the claim so the stem and the source mix can be swapped
      with <b>S</b> while it repeats.
    </div>
    <details class="raw" id="rawWrap" style="display:none">
      <summary>show the raw event record</summary>
      <pre id="rawJson"></pre>
    </details>
  </div>

  <details>
    <summary>Provenance and parameters</summary>
    <!--__ROWS__-->
  </details>
</main>
<script>
const EXHIBIT = /*__EXHIBIT__*/;
const RULE = EXHIBIT.rule;
const ctx = new (window.AudioContext || window.webkitAudioContext)();
const master = ctx.createGain();
master.connect(ctx.destination);

const gains = {}, buffers = {};
const LANES = ['source'].concat(EXHIBIT.tracks.map(t => t.id));
LANES.forEach(id => {
  const g = ctx.createGain();
  g.gain.value = 0;
  g.connect(master);
  gains[id] = g;
});

let timeline = null;          // the compiled document, as it is on disk
let byTrack = {};             // track id -> { samples, intervals, onsets, window_s, hop_s }
let selectedTrack = EXHIBIT.tracks[0].id;
let listenTo = selectedTrack; // which buffer is audible
let listeningToSource = false;
let selection = null;         // { kind, event, index }
let duration = EXHIBIT.duration_s;
let view = { a: 0, b: EXHIBIT.duration_s };
let loop = { a: null, b: null };
let sources = [], playing = false, offset = 0, startedAt = 0;

/* ---- transport ---------------------------------------------------------- */
function looping() { return loop.a !== null && loop.b !== null && loop.b > loop.a; }
function stopSources() {
  sources.forEach(s => { try { s.stop(); } catch (e) {} });
  sources = [];
}
function applyGains() {
  const now = ctx.currentTime;
  LANES.forEach(id => gains[id].gain.setTargetAtTime(id === listenTo ? 1 : 0, now, 0.012));
  document.getElementById('listen').textContent =
    'listening: ' + (listeningToSource ? 'source mix' : shortName(selectedTrack));
  document.querySelectorAll('#tracks button').forEach(b => {
    const wanted = b.dataset.track === '__source__' ? listeningToSource
                                                    : (b.dataset.track === selectedTrack);
    b.classList.toggle('on', wanted);
  });
}
function shortName(id) {
  const t = EXHIBIT.tracks.find(t => t.id === id);
  return t ? t.model_output : id;
}
function start(at) {
  stopSources();
  if (looping()) at = (at < loop.a || at >= loop.b) ? loop.a : at;
  at = Math.max(0, Math.min(at, duration - 0.01));
  const when = ctx.currentTime + 0.04;
  sources = LANES.map(id => {
    const buf = buffers[id];
    if (!buf) return null;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    if (looping()) { src.loop = true; src.loopStart = loop.a; src.loopEnd = loop.b; }
    src.connect(gains[id]);
    src.start(when, at);
    return src;
  }).filter(Boolean);
  startedAt = when; offset = at; playing = true;
  document.getElementById('play').textContent = 'pause';
}
function pause() {
  offset = position(); stopSources(); playing = false;
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
function restart() { if (playing) start(position()); draw(); }

/* ---- view --------------------------------------------------------------- */
function setView(a, b) {
  const span = Math.max(0.05, b - a);
  view.a = Math.max(0, Math.min(a, duration - span));
  view.b = Math.min(duration, view.a + span);
  redraw();
}
function fitView() { setView(0, duration); }
function zoom(factor) {
  const centre = Math.max(view.a, Math.min(position(), view.b));
  const span = (view.b - view.a) * factor;
  setView(centre - span / 2, centre + span / 2);
}
function xOf(t, w) { return ((t - view.a) / (view.b - view.a)) * w; }
function tOf(x, w) { return view.a + (x / w) * (view.b - view.a); }

/* ---- reading the timeline ----------------------------------------------- */
function indexTimeline(doc) {
  const out = {};
  doc.tracks.forEach(track => {
    const samples = [], intervals = [], onsets = [];
    track.events.forEach(e => {
      if (e.type === 'activity.sample') samples.push(e);
      else if (e.type === 'activity.interval') intervals.push(e);
      else if (e.type === 'onset') onsets.push(e);
    });
    const window_s = samples.length ? samples[0].payload.analysis_window_s : 0;
    const hop_s = samples.length > 1 ? samples[1].start_s - samples[0].start_s : window_s;
    out[track.id] = { track, samples, intervals, onsets, window_s, hop_s };
  });
  return out;
}

/* ---- the interval rule, recomputed for the HYPOTHETICAL overlay only ------
   This re-implements a rule that lives in Python. Because it does, it checks
   itself: with the sliders at the compiled thresholds it must reproduce the
   compiled intervals exactly, and it says so on screen when it does not. */
function candidateIntervals(samples, enter, exit, minDuration, mergeGap, windowS, hopS) {
  const runs = [];
  let start = null;
  samples.forEach((s, i) => {
    const v = s.payload.rms_dbfs;
    if (start === null) { if (v >= enter) start = i; }
    else if (v < exit) { runs.push([start, i]); start = null; }
  });
  if (start !== null) runs.push([start, samples.length]);

  const merged = [];
  runs.forEach(([first, last]) => {
    const a = first * hopS, b = (last - 1) * hopS + windowS;
    if (merged.length && a - merged[merged.length - 1][1] <= mergeGap + 1e-9) {
      merged[merged.length - 1][1] = b;
    } else merged.push([a, b]);
  });
  return merged.filter(([a, b]) => b - a >= minDuration - 1e-9);
}
function checkOverlayAgainstDocument() {
  const banner = document.getElementById('hypobanner');
  const data = byTrack[selectedTrack];
  if (!data) return;
  const enter = Number(document.getElementById('hypoEnter').value);
  const exit = Number(document.getElementById('hypoExit').value);
  const on = document.getElementById('hypo').checked;
  if (!on) { banner.style.display = 'none'; return; }
  banner.style.display = 'block';
  banner.classList.remove('bad');
  banner.textContent =
    'HYPOTHETICAL OVERLAY — dashed spans are what the rule would produce at enter ' + enter +
    ' / exit ' + exit + ' dBFS. They are not in the timeline, nothing has been written, and the ' +
    'compiled thresholds stay drawn solid.';
  if (enter === RULE.enter_dbfs && exit === RULE.exit_dbfs) {
    const mine = candidateIntervals(data.samples, enter, exit, RULE.min_duration_s,
                                    RULE.merge_gap_s, data.window_s, data.hop_s);
    if (mine.length !== data.intervals.length) {
      banner.classList.add('bad');
      banner.textContent =
        'THIS PAGE DISAGREES WITH THE COMPILER: at the compiled thresholds it reconstructs ' +
        mine.length + ' intervals and the timeline records ' + data.intervals.length +
        '. Trust the timeline, not this overlay.';
    }
  }
}

/* ---- drawing ------------------------------------------------------------ */
function canvasFor(name) {
  const c = document.querySelector(`[data-canvas="${name}"]`);
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.floor(c.clientWidth));
  const h = Math.max(1, Math.floor(c.clientHeight));
  c.width = w * dpr; c.height = h * dpr;
  const g = c.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  return { g, w, h };
}
function drawWave(name, bufferId, colour) {
  const { g, w, h } = canvasFor(name);
  const buf = buffers[bufferId];
  g.strokeStyle = '#1d242b';
  g.beginPath(); g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke();
  if (!buf) return;
  const rate = buf.sampleRate;
  const chans = [];
  for (let c = 0; c < buf.numberOfChannels; c++) chans.push(buf.getChannelData(c));
  g.strokeStyle = colour; g.globalAlpha = 0.9; g.beginPath();
  for (let x = 0; x < w; x++) {
    const s = Math.max(0, Math.floor(tOf(x, w) * rate));
    const e = Math.min(buf.length, Math.max(s + 1, Math.floor(tOf(x + 1, w) * rate)));
    let lo = 0, hi = 0;
    for (const data of chans) {
      for (let i = s; i < e; i++) {
        const v = data[i];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    g.moveTo(x + 0.5, h / 2 - hi * (h / 2 - 2));
    g.lineTo(x + 0.5, h / 2 - lo * (h / 2 - 2));
  }
  g.stroke(); g.globalAlpha = 1;
}
const DB_TOP = 0, DB_BOTTOM = -70;
function yOfDb(db, h) {
  const clamped = Math.max(DB_BOTTOM, Math.min(DB_TOP, db));
  return h - ((clamped - DB_BOTTOM) / (DB_TOP - DB_BOTTOM)) * (h - 2) - 1;
}
function drawActivity() {
  const { g, w, h } = canvasFor('activity');
  const data = byTrack[selectedTrack];
  if (!data) return;

  // the compiled intervals, as filled spans
  g.fillStyle = 'rgba(127,209,138,.16)';
  data.intervals.forEach(e => {
    const x = xOf(e.start_s, w), x2 = xOf(e.end_s, w);
    if (x2 < 0 || x > w) return;
    g.fillRect(x, 0, Math.max(1, x2 - x), h);
    if (selection && selection.kind === 'interval' && selection.event === e) {
      g.strokeStyle = '#7fd18a'; g.lineWidth = 1.5;
      g.strokeRect(x + .5, 1, Math.max(1, x2 - x) - 1, h - 2);
      g.lineWidth = 1;
    }
  });

  // the thresholds that decided them, drawn where they actually are
  // Labels sit on opposite sides of their lines: six decibels is about ten
  // pixels here, and two labels both drawn above would overlap and be unreadable.
  [[RULE.enter_dbfs, '#7fd18a', 'enter', -4], [RULE.exit_dbfs, '#4f8a5c', 'exit', 11]].forEach(
    ([db, colour, label, dy]) => {
      const y = yOfDb(db, h);
      g.strokeStyle = colour; g.globalAlpha = .8; g.beginPath();
      g.moveTo(0, y); g.lineTo(w, y); g.stroke(); g.globalAlpha = 1;
      g.fillStyle = colour; g.font = '10px ui-monospace, monospace';
      g.fillText(label + ' ' + db.toFixed(0) + ' dBFS', 4, y + dy);
    });

  // the measurement itself
  g.strokeStyle = '#a9d8c9'; g.beginPath();
  let started = false;
  data.samples.forEach(e => {
    const centre = e.start_s + data.window_s / 2;
    if (centre < view.a - data.window_s || centre > view.b + data.window_s) return;
    const x = xOf(centre, w), y = yOfDb(e.payload.rms_dbfs, h);
    if (!started) { g.moveTo(x, y); started = true; } else g.lineTo(x, y);
  });
  g.stroke();

  // the hypothetical overlay, unmistakably not the document
  if (document.getElementById('hypo').checked) {
    const enter = Number(document.getElementById('hypoEnter').value);
    const exit = Number(document.getElementById('hypoExit').value);
    const spans = candidateIntervals(data.samples, enter, exit, RULE.min_duration_s,
                                     RULE.merge_gap_s, data.window_s, data.hop_s);
    g.save();
    g.setLineDash([4, 3]); g.strokeStyle = '#c99bd8';
    spans.forEach(([a, b]) => {
      const x = xOf(a, w), x2 = xOf(b, w);
      if (x2 < 0 || x > w) return;
      g.strokeRect(x + .5, 2.5, Math.max(1, x2 - x) - 1, h - 5);
    });
    [[enter, '#c99bd8'], [exit, '#8d6b9a']].forEach(([db, colour]) => {
      const y = yOfDb(db, h);
      g.strokeStyle = colour; g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
    });
    g.restore();
  }
}
function drawOnsets() {
  const { g, w, h } = canvasFor('onsets');
  const data = byTrack[selectedTrack];
  if (!data) return;
  const top = h - 22;
  const maxFlux = data.onsets.reduce((m, e) => Math.max(m, e.payload.flux), 1);

  g.strokeStyle = '#1d242b'; g.beginPath();
  g.moveTo(0, top + .5); g.lineTo(w, top + .5); g.stroke();

  data.onsets.forEach(e => {
    const x = xOf(e.start_s, w);
    if (x < -2 || x > w + 2) return;
    const chosen = selection && selection.kind === 'onset' && selection.event === e;
    // Uniform height. No probability exists, so nothing here encodes one.
    g.strokeStyle = chosen ? '#ffffff' : '#e0a76a';
    g.lineWidth = chosen ? 2 : 1;
    g.beginPath(); g.moveTo(x, 2); g.lineTo(x, top); g.stroke();
    g.lineWidth = 1;
    // The raw statistic, as a dot, clearly separate from the marker.
    const y = top + 18 - (e.payload.flux / maxFlux) * 16;
    g.fillStyle = chosen ? '#ffffff' : 'rgba(224,167,106,.75)';
    g.beginPath(); g.arc(x, y, chosen ? 3 : 2, 0, Math.PI * 2); g.fill();
  });
}
function redraw() {
  drawWave('source', 'source', '#6fd0c0');
  drawWave('stem', selectedTrack, '#7aa7ff');
  drawActivity();
  drawOnsets();
  draw();
}
function fmt(t) {
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
}
function draw() {
  const hit = document.getElementById('hit');
  const w = hit.clientWidth;
  const p = position();
  const head = document.getElementById('playhead');
  const x = xOf(p, w);
  head.style.display = (x < 0 || x > w) ? 'none' : 'block';
  head.style.left = `${x}px`;
  document.getElementById('clock').textContent = `${fmt(p)} / ${fmt(duration)}`;
  const el = document.getElementById('loop');
  if (looping()) {
    el.style.display = 'block';
    el.style.left = `${xOf(loop.a, w)}px`;
    el.style.width = `${Math.max(1, xOf(loop.b, w) - xOf(loop.a, w))}px`;
  } else el.style.display = 'none';
  const loopText = looping() ? `  loop ${fmt(loop.a)} - ${fmt(loop.b)}` : '';
  document.getElementById('viewinfo').textContent =
    (view.b - view.a >= duration - 0.01)
      ? 'whole file' + loopText
      : `view ${fmt(view.a)} - ${fmt(view.b)}` + loopText;
}
function frame() { draw(); requestAnimationFrame(frame); }

/* ---- selection and audition --------------------------------------------- */
function describe(kind, event) {
  const rows = [];
  const add = (k, v) => rows.push([k, v]);
  add('type', event.type);
  add('start_s', event.start_s.toFixed(6));
  add('end_s', event.end_s === undefined || event.end_s === null
        ? 'absent (an instant)' : event.end_s.toFixed(6));
  add('confidence', event.confidence === undefined || event.confidence === null
        ? 'absent — this producer reports no calibrated confidence'
        : String(event.confidence));
  Object.keys(event.payload).sort().forEach(k => add('payload.' + k, String(event.payload[k])));
  add('evidence.artifact', event.evidence.artifact);
  add('evidence.artifact_hash', event.evidence.artifact_hash);
  add('evidence.stage', event.evidence.stage);
  const stage = timeline.provenance.find(p => p.stage === event.evidence.stage);
  if (stage) {
    add('stage.truth_layer', stage.truth_layer);
    add('stage.tool', stage.tool + ' ' + stage.tool_revision);
    Object.keys(stage.parameters).sort().forEach(
      k => add('parameter.' + k, JSON.stringify(stage.parameters[k])));
  }
  return rows;
}
function select(kind, event, index) {
  selection = { kind, event, index };
  const rows = describe(kind, event);
  document.getElementById('inspectorBody').innerHTML =
    '<table>' + rows.map(([k, v]) =>
      `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(v)}</td></tr>`).join('') + '</table>' +
    '<p class="hint">Press <b>enter</b> to audition this claim, or <b>S</b> to swap between the ' +
    'model output and the source mix while it loops.</p>';
  document.getElementById('rawWrap').style.display = 'block';
  document.getElementById('rawJson').textContent = JSON.stringify(event, null, 2);
  redraw();
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function audition() {
  if (!selection) return;
  const e = selection.event;
  if (selection.kind === 'onset') {
    const pre = Number(document.getElementById('pre').value) / 1000;
    const post = Number(document.getElementById('post').value) / 1000;
    loop = { a: Math.max(0, e.start_s - pre), b: Math.min(duration, e.start_s + post) };
  } else {
    const m = Number(document.getElementById('margin').value) / 1000;
    loop = { a: Math.max(0, e.start_s - m), b: Math.min(duration, e.end_s + m) };
  }
  const pad = Math.max(0.4, (loop.b - loop.a) * 0.8);
  setView(loop.a - pad, loop.b + pad);
  if (ctx.state === 'suspended') ctx.resume();
  start(loop.a);
  draw();
}
function step(kind, direction) {
  const data = byTrack[selectedTrack];
  if (!data) return;
  const list = kind === 'onset' ? data.onsets : data.intervals;
  if (!list.length) return;
  const from = selection && selection.kind === kind ? selection.index : null;
  let index;
  if (from !== null) index = Math.max(0, Math.min(list.length - 1, from + direction));
  else {
    const now = position();
    index = direction > 0 ? list.findIndex(e => e.start_s > now)
                          : [...list].reverse().findIndex(e => e.start_s < now);
    if (index < 0) index = direction > 0 ? 0 : list.length - 1;
    else if (direction < 0) index = list.length - 1 - index;
  }
  select(kind, list[index], index);
  audition();
}
function pickAt(time, kind) {
  const data = byTrack[selectedTrack];
  if (!data) return false;
  const tolerance = (view.b - view.a) * 0.01;
  if (kind === 'onset') {
    let best = null, bestIndex = -1;
    data.onsets.forEach((e, i) => {
      const d = Math.abs(e.start_s - time);
      if (d <= tolerance && (best === null || d < Math.abs(best.start_s - time))) {
        best = e; bestIndex = i;
      }
    });
    if (best) { select('onset', best, bestIndex); return true; }
    return false;
  }
  const i = data.intervals.findIndex(e => time >= e.start_s && time <= e.end_s);
  if (i >= 0) { select('interval', data.intervals[i], i); return true; }
  return false;
}

/* ---- wiring ------------------------------------------------------------- */
function selectTrack(id) {
  selectedTrack = id;
  if (!listeningToSource) listenTo = id;
  const t = EXHIBIT.tracks.find(t => t.id === id);
  const data = byTrack[id];
  document.getElementById('stemName').textContent = t.label;
  document.getElementById('stemMeta').textContent = t.path + '  ' + t.hash;
  document.getElementById('activityMeta').textContent =
    data ? `${data.samples.length} samples · window ${(data.window_s * 1000).toFixed(1)} ms · ` +
           `hop ${(data.hop_s * 1000).toFixed(1)} ms · ${data.intervals.length} intervals` : '';
  document.getElementById('activityCaption').textContent =
    `Measured level, with the rule that produced the spans: enter at or above ` +
    `${RULE.enter_dbfs} dBFS, leave below ${RULE.exit_dbfs} dBFS, merge gaps under ` +
    `${(RULE.merge_gap_s * 1000).toFixed(0)} ms, discard anything under ` +
    `${(RULE.min_duration_s * 1000).toFixed(0)} ms.`;
  document.getElementById('activityEmpty').textContent =
    data && data.intervals.length === 0
      ? '0 activity intervals inferred under this rule and these thresholds. That is a statement ' +
        'about the detector, not about the recording.'
      : '';
  document.getElementById('onsetMeta').textContent =
    data ? `${data.onsets.length} hypotheses` : '';
  document.getElementById('onsetEmpty').textContent =
    data && data.onsets.length === 0
      ? '0 onset hypotheses produced here at these parameters. Nothing was found; nothing has ' +
        'been established about what is in the recording.'
      : '';
  selection = null;
  document.getElementById('rawWrap').style.display = 'none';
  applyGains();
  checkOverlayAgainstDocument();
  redraw();
}
document.getElementById('play').onclick = toggle;
document.getElementById('stop').onclick = () => { pause(); offset = 0; draw(); };
document.getElementById('fit').onclick = fitView;
document.getElementById('zoomIn').onclick = () => zoom(0.5);
document.getElementById('zoomOut').onclick = () => zoom(2);
document.getElementById('listen').onclick = swapListening;
document.getElementById('nextOnset').onclick = () => step('onset', +1);
document.getElementById('prevOnset').onclick = () => step('onset', -1);
document.getElementById('nextInterval').onclick = () => step('interval', +1);
document.getElementById('prevInterval').onclick = () => step('interval', -1);
function swapListening() {
  listeningToSource = !listeningToSource;
  listenTo = listeningToSource ? 'source' : selectedTrack;
  applyGains();
}
document.querySelectorAll('#tracks button').forEach(b => {
  b.onclick = () => {
    if (b.dataset.track === '__source__') {
      listeningToSource = true; listenTo = 'source'; applyGains();
    } else {
      listeningToSource = false; selectTrack(b.dataset.track);
    }
  };
});
['hypo', 'hypoEnter', 'hypoExit'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => {
    checkOverlayAgainstDocument(); redraw();
  });
});
document.getElementById('hit').onclick = e => {
  const r = e.currentTarget.getBoundingClientRect();
  const t = tOf(e.clientX - r.left, r.width);
  const laneTop = document.querySelector('[data-canvas="onsets"]').getBoundingClientRect();
  const onOnsetLane = e.clientY >= laneTop.top && e.clientY <= laneTop.bottom;
  if (onOnsetLane && pickAt(t, 'onset')) { audition(); return; }
  const actTop = document.querySelector('[data-canvas="activity"]').getBoundingClientRect();
  if (e.clientY >= actTop.top && e.clientY <= actTop.bottom && pickAt(t, 'interval')) {
    audition(); return;
  }
  seek(t);
};
window.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.target.tagName === 'INPUT') return;
  const k = e.key;
  if (k === ' ') { e.preventDefault(); toggle(); return; }
  if (k === '0') { listeningToSource = true; listenTo = 'source'; applyGains(); return; }
  if (k >= '1' && k <= '9') {
    const t = EXHIBIT.tracks.find(t => t.shortcut === k);
    if (t) { listeningToSource = false; selectTrack(t.id); }
    return;
  }
  if (k === 's' || k === 'S') { swapListening(); return; }
  if (k === 'n') { step('onset', +1); return; }
  if (k === 'p' || k === 'P') { step('onset', -1); return; }
  if (k === 'i') { step('interval', +1); return; }
  if (k === 'I') { step('interval', -1); return; }
  if (k === 'N') { step('onset', -1); return; }
  if (k === 'Enter') { audition(); return; }
  if (k === '[') { loop.a = position(); normaliseLoop(); return; }
  if (k === ']') { loop.b = position(); normaliseLoop(); return; }
  if (k === 'f' || k === 'F') { fitView(); return; }
  if (k === '-' || k === '_') { zoom(2); return; }
  if (k === '=' || k === '+') { zoom(0.5); return; }
  if (k === 'ArrowLeft') { e.preventDefault(); seek(position() - 5); return; }
  if (k === 'ArrowRight') { e.preventDefault(); seek(position() + 5); return; }
  if (k === 'Escape') {
    loop = { a: null, b: null };
    selection = null;
    document.getElementById('rawWrap').style.display = 'none';
    document.getElementById('inspectorBody').innerHTML =
      '<span class="hint">Click an onset marker or an interval to select it.</span>';
    fitView(); restart();
  }
});
function normaliseLoop() {
  if (loop.a !== null && loop.b !== null && loop.b < loop.a) {
    const t = loop.a; loop.a = loop.b; loop.b = t;
  }
  restart();
}
let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(redraw, 120);
});

/* ---- load --------------------------------------------------------------- */
const status = document.getElementById('status');
(async () => {
  status.textContent = 'reading the timeline…';
  const response = await fetch(EXHIBIT.timeline_url);
  if (!response.ok) throw new Error(EXHIBIT.timeline_url + ': ' + response.status);
  timeline = await response.json();
  byTrack = indexTimeline(timeline);

  const wanted = [{ id: 'source', url: EXHIBIT.source.url }]
    .concat(EXHIBIT.tracks.map(t => ({ id: t.id, url: t.url })));
  let done = 0;
  await Promise.all(wanted.map(async item => {
    const r = await fetch(item.url);
    if (!r.ok) throw new Error(item.url + ': ' + r.status);
    buffers[item.id] = await ctx.decodeAudioData(await r.arrayBuffer());
    done += 1;
    status.textContent = `decoding… ${done}/${wanted.length}`;
  })).catch(err => { status.textContent = 'failed: ' + err.message; throw err; });

  duration = Math.max(EXHIBIT.duration_s, ...Object.values(buffers).map(b => b.duration));
  view = { a: 0, b: duration };
  document.getElementById('sourceMeta').textContent =
    EXHIBIT.source.path + '  ' + EXHIBIT.source.hash;
  document.getElementById('hypoEnter').value = RULE.enter_dbfs;
  document.getElementById('hypoExit').value = RULE.exit_dbfs;
  status.style.display = 'none';
  selectTrack(selectedTrack);
})();
frame();
</script>
</body>
</html>
"""
