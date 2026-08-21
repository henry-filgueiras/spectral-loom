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


The page itself is `pages/timeline_observatory.html`, a real file rather than a string in
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spectral_loom.analysis import (
    ONSET_FLUX_FLOOR,
    ONSET_MIN_GAP_S,
    AnalysisError,
    infer_onsets,
    quantize,
    read_wav_mono,
)
from spectral_loom.contracts import Provenance, SeparationManifest, SongTimeline
from spectral_loom.hashing import hash_file
from spectral_loom.observatory import (
    REVIEW_DIRNAME,
    ObservatoryError,
    page_url,
    verify,
)
from spectral_loom.separate import DERIVED_DIRNAME
from spectral_loom.timeline import INTERVAL_STAGE, MEASURE_STAGE, ONSET_PARAMETERS, ONSET_STAGE

#: The page lands beside the Stem Observatory's, under the same ignored
#: directory, with a name that says which instrument it is.
TIMELINE_PAGE = "timeline.html"

#: Where the compiled document is served from. The page reads the timeline
#: itself rather than a summary of it, so the record an inspector shows is the
#: record on disk and not a second rendering of it that could drift.
TIMELINE_URL = "/timeline.json"

#: The novelty curves and the peaks the rule declined, recomputed for review.
#:
#: **Not a semantic artifact and never one.** A rejected candidate is not an
#: event, it is not in `song.timeline.json`, and it never will be — it exists so
#: that a detector can be judged on what it turned down as well as on what it
#: claimed. The file says so inside itself, because a JSON document found on
#: disk months later will be read without its context.
#:
#: Recomputed by :mod:`spectral_loom.analysis` — the same functions, at the same
#: parameters, that produced the accepted onsets — rather than by a second
#: implementation. That is the whole reason it is built in Python and handed to
#: the page rather than derived in the browser.
NOVELTY_URL = "/novelty.json"
NOVELTY_FILENAME = "review-novelty.json"


PAGE_TEMPLATE = "timeline_observatory.html"


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
    #: The absolute flux floor, so the page can say what it is not showing.
    flux_floor: float
    files: dict[str, Path] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "specimen_id": self.specimen_id,
            "duration_s": self.duration_s,
            "timeline_url": page_url(self.timeline_url),
            "source": {
                "url": page_url(self.source_url),
                "path": self.source_path,
                "hash": self.source_hash,
            },
            "tracks": [
                {
                    "id": track.id,
                    "model_output": track.model_output,
                    "label": track.label,
                    "url": page_url(track.url),
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
            "novelty_url": page_url(NOVELTY_URL),
            "flux_floor": self.flux_floor,
        }


def novelty_path(repository_root: Path, specimen_id: str) -> Path:
    """Where the recomputed review data lands: beside the page, ignored with it."""
    return repository_root / DERIVED_DIRNAME / specimen_id / REVIEW_DIRNAME / NOVELTY_FILENAME


def build_novelty(
    tracks: list[TrackView], repository_root: Path, timeline_hash: str, specimen_id: str
) -> dict[str, Any]:
    """Recompute the novelty curve and the declined peaks for every model output.

    By calling :func:`spectral_loom.analysis.infer_onsets` — the *same* function,
    at the same parameters, that produced the accepted onsets in the timeline —
    rather than reimplementing the rule. The page then draws arrays. That is the
    difference between a review surface that can disagree with the compiler and
    one that cannot: the threshold explorer already re-implements the interval
    rule in JavaScript and needs a self-check because of it, and this deliberately
    does not repeat that.

    The curves are rounded to two decimal places. They are drawn, not decided on;
    the numbers a decision was made on travel with each candidate at the
    compiler's own precision.
    """
    document: dict[str, Any] = {
        "_what_this_is": (
            "Recomputed for review by spectral_loom.analysis, at the parameters recorded in the "
            "timeline. NOT a semantic artifact. A rejected candidate is NOT an event, is not in "
            "song.timeline.json, and must never be read as one: it is a peak in the novelty "
            "curve that this rule declined, kept so the detector can be judged on what it turned "
            "down as well as on what it claimed."
        ),
        "specimen_id": specimen_id,
        "timeline_sha256": timeline_hash,
        "tool": "spectral_loom.analysis.infer_onsets",
        "parameters": dict(ONSET_PARAMETERS),
        "flux_floor": ONSET_FLUX_FLOOR,
        "min_gap_s": ONSET_MIN_GAP_S,
        "tracks": {},
    }
    for track in tracks:
        try:
            audio = read_wav_mono(repository_root / track.path)
        except AnalysisError as exc:
            raise ObservatoryError(str(exc)) from exc
        analysis = infer_onsets(audio)
        # Every local maximum the rule chose from, with the *adaptive* half of the
        # threshold it faced. The floor is a constant added to that half, so a
        # review surface can ask what this same rule would have done at another
        # floor with one comparison per peak — and without re-deriving the
        # novelty, the running median, or the peak picking, which are the parts
        # worth duplicating badly.
        peaks = analysis.peak_frames
        document["tracks"][track.id] = {
            "hop_s": quantize(analysis.resolution_s, 6),
            "frames": int(analysis.flux.size),
            "flux_max": quantize(float(analysis.flux.max()) if analysis.flux.size else 0.0, 2),
            "flux": [round(float(v), 2) for v in analysis.flux],
            "threshold": [round(float(v), 2) for v in analysis.threshold],
            "peak_t": [round(i * analysis.resolution_s, 6) for i in peaks],
            "peak_flux": [round(float(analysis.flux[i]), 6) for i in peaks],
            "peak_adaptive": [
                round(float(analysis.threshold[i]) - ONSET_FLUX_FLOOR, 6) for i in peaks
            ],
            "peak_dbfs": [round(float(analysis.frame_rms_dbfs[i]), 3) for i in peaks],
            "accepted": len(analysis.onsets),
            "accepted_t": [o.start_s for o in analysis.onsets],
            "rejected": [
                {
                    "start_s": c.start_s,
                    "flux": c.flux,
                    "threshold": c.threshold,
                    "margin": c.margin,
                    "local_median": c.local_median,
                    "frame_rms_dbfs": c.frame_rms_dbfs,
                    "reason": c.reason,
                }
                for c in analysis.rejected
            ],
            "rejected_below_floor": analysis.rejected_below_floor,
        }
    return document


def write_novelty(repository_root: Path, specimen_id: str, document: dict[str, Any]) -> Path:
    target = novelty_path(repository_root, specimen_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


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

    # Written here rather than by the caller so that the whitelist never names a
    # file that does not exist yet. This builder already reads and hashes every
    # artifact it is about; writing one review asset into the ignored review
    # directory beside the page is the same kind of act.
    document = build_novelty(
        tracks, repository_root, hash_file(timeline_path), timeline.specimen_id
    )
    files[NOVELTY_URL] = write_novelty(repository_root, timeline.specimen_id, document)

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
        flux_floor=ONSET_FLUX_FLOOR,
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
        load_page(PAGE_TEMPLATE)
        .replace(_TITLE_TOKEN, html.escape(exhibit.specimen_id))
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
