"""Tests for the Timeline Observatory's document-to-page transformation.

The page's real properties — that a click loops the right 650 milliseconds and
that the lanes stay aligned on one clock — cannot be asserted from Python and are
not attempted here. What can be asserted is everything the page *says*, and that
is where the risk lives: a browser that drifts a few milliseconds is annoying,
whereas a page that drew an onset marker with a height proportional to its flux
would quietly teach a reader that this detector reports a confidence.

So these check the honesty of the rendering, the refusals when the artifacts on
disk are not the ones the timeline was measured from, and the shape of the
server's file whitelist. No audio is decoded and no socket is opened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spectral_loom.contracts import SongTimeline
from spectral_loom.hashing import hash_file
from spectral_loom.observatory import ObservatoryError
from spectral_loom.timeline import ONSET_PARAMETERS, CompilePlan, compile_timeline, plan
from spectral_loom.timeline_observatory import (
    NOVELTY_URL,
    TIMELINE_URL,
    TimelineExhibit,
    build_exhibit,
    novelty_path,
    render,
)
from tests.test_timeline import SHAPES, SPECIMEN, build_repository


def exhibit_for(root: Path) -> tuple[TimelineExhibit, CompilePlan, SongTimeline]:
    manifest = build_repository(root)
    prepared = plan(SPECIMEN, root)
    timeline, _, _ = compile_timeline(prepared)
    return build_exhibit(timeline, prepared.timeline_path, manifest, root), prepared, timeline


# ---------------------------------------------------------------------------
# The whitelist.
# ---------------------------------------------------------------------------


def test_the_whitelist_holds_the_source_the_stems_and_the_document(tmp_path: Path) -> None:
    exhibit, prepared, _ = exhibit_for(tmp_path)
    assert set(exhibit.files) == {"/audio/source", TIMELINE_URL, NOVELTY_URL} | {
        f"/audio/{name}" for name in SHAPES
    }
    assert exhibit.files[TIMELINE_URL] == prepared.timeline_path
    assert all(path.is_file() for path in exhibit.files.values())


def test_the_page_serves_the_timeline_itself_not_a_summary_of_it(tmp_path: Path) -> None:
    """The inspector must quote the record on disk, not a second rendering."""
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    served = exhibit.files[TIMELINE_URL]
    assert hash_file(served) == exhibit.timeline_hash
    assert json.loads(served.read_text())["schema_id"] == "spectral-loom/song-timeline"


def test_nothing_outside_the_repository_is_reachable(tmp_path: Path) -> None:
    exhibit, _, _ = exhibit_for(tmp_path)
    for path in exhibit.files.values():
        assert path.resolve().is_relative_to(tmp_path.resolve())


# ---------------------------------------------------------------------------
# Refusals.
# ---------------------------------------------------------------------------


def test_a_stem_that_changed_since_the_timeline_is_refused(tmp_path: Path) -> None:
    manifest = build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    timeline, _, _ = compile_timeline(prepared)
    stem = tmp_path / "corpus/derived" / SPECIMEN / "separation/bass.wav"
    stem.write_bytes(stem.read_bytes() + b"\x00\x00")

    with pytest.raises(ObservatoryError, match="hashes to"):
        build_exhibit(timeline, prepared.timeline_path, manifest, tmp_path)


def test_a_missing_stem_is_refused_rather_than_shown_as_an_empty_lane(tmp_path: Path) -> None:
    """An empty onset lane and a missing file must not look the same."""
    manifest = build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    timeline, _, _ = compile_timeline(prepared)
    (tmp_path / "corpus/derived" / SPECIMEN / "separation/vocals.wav").unlink()

    with pytest.raises(ObservatoryError, match="not on disk"):
        build_exhibit(timeline, prepared.timeline_path, manifest, tmp_path)


def test_a_source_that_is_not_the_one_the_timeline_is_about_is_refused(tmp_path: Path) -> None:
    manifest = build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    timeline, _, _ = compile_timeline(prepared)
    source = tmp_path / "corpus/generated" / SPECIMEN / "source.wav"
    source.write_bytes(source.read_bytes() + b"\x00\x00")

    with pytest.raises(ObservatoryError, match="worse than not checking them"):
        build_exhibit(timeline, prepared.timeline_path, manifest, tmp_path)


def test_a_timeline_without_the_rule_in_its_provenance_is_refused(tmp_path: Path) -> None:
    """The page draws thresholds it read off the document, or it does not draw."""
    manifest = build_repository(tmp_path)
    prepared = plan(SPECIMEN, tmp_path)
    timeline, _, _ = compile_timeline(prepared)
    stripped = timeline.model_copy(
        update={"provenance": [p for p in timeline.provenance if p.stage != "activity.interval"]}
    )
    with pytest.raises(ObservatoryError, match="different compiler"):
        build_exhibit(stripped, prepared.timeline_path, manifest, tmp_path)


# ---------------------------------------------------------------------------
# What the page draws, and what it must never draw.
# ---------------------------------------------------------------------------


def test_the_thresholds_drawn_are_the_ones_the_compiler_used(tmp_path: Path) -> None:
    """Read off the provenance, not restated, so the lines are the lines that ran."""
    exhibit, _, timeline = exhibit_for(tmp_path)
    rule = next(p for p in timeline.provenance if p.stage == "activity.interval").parameters
    assert exhibit.enter_dbfs == rule["enter_dbfs"]
    assert exhibit.exit_dbfs == rule["exit_dbfs"]
    assert exhibit.min_duration_s == rule["min_duration_s"]
    assert exhibit.merge_gap_s == rule["merge_gap_s"]
    assert exhibit.payload()["rule"]["enter_dbfs"] == rule["enter_dbfs"]


def test_lanes_are_labelled_as_model_outputs(tmp_path: Path) -> None:
    exhibit, _, _ = exhibit_for(tmp_path)
    assert [track.model_output for track in exhibit.tracks] == list(SHAPES)
    for track in exhibit.tracks:
        assert "model output" in track.label
    page = render(exhibit)
    assert "not verified instruments" in page


def test_the_page_says_an_empty_lane_is_a_statement_about_the_detector(tmp_path: Path) -> None:
    """The single most important sentence on the page."""
    exhibit, _, _ = exhibit_for(tmp_path)
    page = render(exhibit)
    assert "inferred nothing there" in page
    assert "0 activity intervals inferred under this rule and these thresholds" in page
    assert "not about the recording" in page


def test_onset_markers_are_not_styled_as_probabilities(tmp_path: Path) -> None:
    """A marker whose height varied with flux would be read as a confidence."""
    page = render(exhibit_for(tmp_path)[0])
    assert "Markers are all the same height" in page
    assert "no calibrated confidence" in page
    # And the drawing code says so where it draws.
    assert "No probability exists, so nothing here encodes one." in page


def test_the_hypothetical_overlay_is_labelled_and_writes_nothing(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "HYPOTHETICAL OVERLAY" in page
    assert "nothing has been written" in page
    # The page holds no writer of any kind.
    assert "method: 'POST'" not in page
    assert "XMLHttpRequest" not in page
    assert "sendBeacon" not in page
    assert "localStorage" not in page


def test_the_overlay_checks_its_own_arithmetic_against_the_compiler(tmp_path: Path) -> None:
    """It re-implements a Python rule in JavaScript, so it has to be checkable."""
    page = render(exhibit_for(tmp_path)[0])
    assert "THIS PAGE DISAGREES WITH THE COMPILER" in page
    assert "Trust the timeline, not this overlay." in page


def test_the_page_has_no_external_reference_of_any_kind(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path)[0])
    for forbidden in ("<script src", "<link ", "<img ", "<iframe", "http://", "https://", "//cdn"):
        assert forbidden not in page, forbidden


def test_the_provenance_carries_the_whole_lineage(tmp_path: Path) -> None:
    exhibit, _, _ = exhibit_for(tmp_path)
    labels = {key for key, _ in exhibit.provenance}
    assert "stage generate" in labels
    assert "stage separate" in labels
    assert "stage activity.measure" in labels
    assert "stage onset.spectral_flux" in labels
    assert "timeline sha256" in labels


def test_the_parameters_shown_are_the_ones_that_decided_an_event(tmp_path: Path) -> None:
    exhibit, _, _ = exhibit_for(tmp_path)
    keys = {key for key, _ in exhibit.parameters}
    assert "activity.interval.enter_dbfs" in keys
    assert "activity.interval.merge_gap_s" in keys
    assert "onset.spectral_flux.flux_floor" in keys
    assert "onset.spectral_flux.median_multiplier" in keys


def test_the_payload_is_valid_json_inside_the_page(tmp_path: Path) -> None:
    exhibit, _, _ = exhibit_for(tmp_path)
    page = render(exhibit)
    marker = "const EXHIBIT = "
    start = page.index(marker) + len(marker)
    end = page.index(";\n", start)
    assert json.loads(page[start:end]) == exhibit.payload()


def test_the_page_names_the_specimen_and_escapes_it(tmp_path: Path) -> None:
    exhibit, _, _ = exhibit_for(tmp_path)
    page = render(exhibit)
    assert f"Timeline Observatory — {SPECIMEN}" in page
    assert "<!--__TITLE__-->" not in page
    assert "/*__EXHIBIT__*/" not in page


# ---------------------------------------------------------------------------
# The peaks the rule declined.
# ---------------------------------------------------------------------------


def test_the_novelty_sidecar_is_written_beside_the_page(tmp_path: Path) -> None:
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    target = novelty_path(tmp_path, SPECIMEN)
    assert exhibit.files[NOVELTY_URL] == target
    assert target.is_file()
    assert target.parent.name == "review"


def test_the_sidecar_says_inside_itself_that_it_is_not_a_semantic_artifact(
    tmp_path: Path,
) -> None:
    """It will be found on disk months later without any of this context."""
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    document = json.loads(exhibit.files[NOVELTY_URL].read_text())
    explanation = document["_what_this_is"]
    assert "NOT a semantic artifact" in explanation
    assert "is not in song.timeline.json" in explanation
    assert document["timeline_sha256"].startswith("sha256:")


def test_the_sidecar_is_computed_by_the_compiler_s_own_analysis(tmp_path: Path) -> None:
    """Not a second implementation of the rule, which is the whole point."""
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    document = json.loads(exhibit.files[NOVELTY_URL].read_text())
    assert document["tool"] == "spectral_loom.analysis.infer_onsets"
    assert document["parameters"]["median_multiplier"] == ONSET_PARAMETERS["median_multiplier"]
    assert document["parameters"]["flux_floor"] == ONSET_PARAMETERS["flux_floor"]


def test_the_sidecar_agrees_with_the_timeline_about_what_was_accepted(tmp_path: Path) -> None:
    exhibit, _prepared, timeline = exhibit_for(tmp_path)
    document = json.loads(exhibit.files[NOVELTY_URL].read_text())
    for track in timeline.tracks:
        accepted = [e for e in track.events if e.type == "onset"]
        assert document["tracks"][track.id]["accepted"] == len(accepted)


def test_no_declined_peak_coincides_with_an_accepted_onset(tmp_path: Path) -> None:
    """A candidate must never be mistakable for a claim, starting with its time."""
    exhibit, _prepared, timeline = exhibit_for(tmp_path)
    document = json.loads(exhibit.files[NOVELTY_URL].read_text())
    for track in timeline.tracks:
        accepted = {e.start_s for e in track.events if e.type == "onset"}
        declined = {c["start_s"] for c in document["tracks"][track.id]["rejected"]}
        assert not accepted & declined


def test_the_page_says_a_declined_peak_is_not_a_claim(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "This is not a claim." in page
    assert "A DECLINED PEAK — not an event, and not in the timeline" in page
    assert "not events, not in the" in page


def test_the_page_says_what_it_is_not_drawing(tmp_path: Path) -> None:
    """A count for the below-floor peaks, so their absence is stated not implied."""
    page = render(exhibit_for(tmp_path)[0])
    assert "rejected_below_floor" in page
    assert "counted rather than drawn" in page


def test_the_novelty_axis_is_labelled_and_its_crossings_are_claimed_exact(
    tmp_path: Path,
) -> None:
    """A log axis is fine; an unlabelled one that hides the rule is not."""
    page = render(exhibit_for(tmp_path)[0])
    assert "log axis" in page
    assert "crossings are exact" in page
    assert "largest in view" in page


# ---------------------------------------------------------------------------
# Moving the floor hypothetically.
# ---------------------------------------------------------------------------


def test_the_sidecar_ships_the_candidate_set_the_rule_chose_from(tmp_path: Path) -> None:
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    document = json.loads(exhibit.files[NOVELTY_URL].read_text())
    for track in document["tracks"].values():
        n = len(track["peak_t"])
        assert n
        assert len(track["peak_flux"]) == n
        assert len(track["peak_adaptive"]) == n
        assert len(track["peak_dbfs"]) == n
    assert document["min_gap_s"] > 0


def test_the_shipped_adaptive_term_plus_the_floor_is_the_threshold(tmp_path: Path) -> None:
    """What makes the page's derivation exact rather than an approximation."""
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    document = json.loads(exhibit.files[NOVELTY_URL].read_text())
    floor = document["flux_floor"]
    for track in document["tracks"].values():
        hop = track["hop_s"]
        for t, adaptive in zip(track["peak_t"], track["peak_adaptive"], strict=True):
            frame = round(t / hop)
            assert adaptive + floor == pytest.approx(track["threshold"][frame], abs=0.02)


def test_the_candidate_set_reproduces_the_accepted_onsets_at_the_compiled_floor(
    tmp_path: Path,
) -> None:
    """The invariant the page checks itself against, asserted here so CI holds it too.

    If this ever fails, the floor control in the browser is deriving something
    the compiler did not, and the page's own self-check would be the only thing
    standing between a reviewer and a fabricated event.
    """
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    document = json.loads(exhibit.files[NOVELTY_URL].read_text())
    floor, min_gap = document["flux_floor"], document["min_gap_s"]

    for track in document["tracks"].values():
        derived: list[float] = []
        last = -1e9
        for t, flux, adaptive in zip(
            track["peak_t"], track["peak_flux"], track["peak_adaptive"], strict=True
        ):
            if flux < adaptive + floor or t - last < min_gap:
                continue
            last = t
            derived.append(t)
        assert derived == pytest.approx(track["accepted_t"], abs=1e-6)


def test_lowering_the_floor_can_only_add_and_raising_it_can_only_remove(
    tmp_path: Path,
) -> None:
    """The control must not be quietly one-sided; the page draws both directions."""
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    document = json.loads(exhibit.files[NOVELTY_URL].read_text())
    track = max(document["tracks"].values(), key=lambda t: len(t["accepted_t"]))

    def accept(floor: float) -> set[float]:
        out: set[float] = set()
        last = -1e9
        for t, flux, adaptive in zip(
            track["peak_t"], track["peak_flux"], track["peak_adaptive"], strict=True
        ):
            if flux < adaptive + floor or t - last < document["min_gap_s"]:
                continue
            last = t
            out.add(t)
        return out

    compiled = accept(document["flux_floor"])
    assert accept(document["flux_floor"] * 3) <= compiled
    assert compiled <= accept(0.0)


def test_the_page_carries_the_rule_controls_and_says_they_are_hypothetical(
    tmp_path: Path,
) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "hypothetical onset floor" in page
    assert "multiplier" in page
    # The banner names the whole rule, since either half can now be moved.
    assert "HYPOTHETICAL RULE — flux >= " in page
    assert "nothing has been written" in page
    assert "reproduces the compiler exactly" in page
    assert "THIS PAGE DISAGREES WITH THE COMPILER at the compiled floor" in page


# ---------------------------------------------------------------------------
# The cross-output raster, and the notebook.
# ---------------------------------------------------------------------------


def test_the_raster_refuses_to_let_coincidence_read_as_a_finding(tmp_path: Path) -> None:
    """Parts played together coincide; so does leakage. The lane must say so."""
    page = render(exhibit_for(tmp_path)[0])
    assert "all outputs" in page
    assert "Coincidence establishes nothing on its own" in page
    assert "says where to look, never what is true" in page


def test_the_notebook_says_it_writes_nothing_and_offers_the_way_out(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "Review marks" in page
    assert "the page writes nothing" in page
    assert "copy them out before you close it" in page
    assert "copy marks as text" in page


def test_the_page_still_has_no_writer_of_any_kind(tmp_path: Path) -> None:
    """Marking a claim must not have become a way to acquire one."""
    page = render(exhibit_for(tmp_path)[0])
    for forbidden in (
        "XMLHttpRequest",
        "sendBeacon",
        "localStorage",
        "sessionStorage",
        "method: 'POST'",
        'method: "POST"',
        "indexedDB",
    ):
        assert forbidden not in page, forbidden


def test_the_payload_hands_the_page_relative_urls(tmp_path: Path) -> None:
    """The whitelist stays absolute; what the page fetches does not."""
    exhibit, _prepared, _timeline = exhibit_for(tmp_path)
    payload = exhibit.payload()

    assert not payload["timeline_url"].startswith("/")
    assert not payload["novelty_url"].startswith("/")
    assert not payload["source"]["url"].startswith("/")
    assert all(not t["url"].startswith("/") for t in payload["tracks"])

    # ...and every one of them still names a route the server actually serves.
    for relative in [payload["timeline_url"], payload["novelty_url"], payload["source"]["url"]] + [
        t["url"] for t in payload["tracks"]
    ]:
        assert "/" + relative in exhibit.files


# ---------------------------------------------------------------------------
# The click track.
# ---------------------------------------------------------------------------


def test_the_page_can_sonify_its_own_markers(tmp_path: Path) -> None:
    """Judging a marker against an attack by eye asks for tens of milliseconds
    of visual resolution against a waveform. Hearing it is how onset detection
    has always actually been evaluated."""
    page = render(exhibit_for(tmp_path)[0])
    assert "click on events" in page
    assert "CLICK_TONE" in page
    assert "Sonify the markers" in page


def test_the_click_track_mirrors_what_the_marker_lane_draws(tmp_path: Path) -> None:
    """Three pitches, so which kind is sounding needs no glance at the screen."""
    page = render(exhibit_for(tmp_path)[0])
    for kind in ("accepted", "declined", "whatif"):
        assert f"{kind}:" in page.split("CLICK_TONE")[1][:200], kind


def test_the_click_lane_is_additive_rather_than_something_you_switch_to(
    tmp_path: Path,
) -> None:
    """The whole point is hearing it over the selected output, not instead of it."""
    page = render(exhibit_for(tmp_path)[0])
    assert "The click lane is additive" in page
    assert "if (id === CLICK_LANE) return;" in page


def test_the_clicks_ride_the_same_transport_as_the_audio(tmp_path: Path) -> None:
    """A separately scheduled click would have to re-derive loop wrapping and
    would drift; a buffer started by the same call cannot."""
    page = render(exhibit_for(tmp_path)[0])
    assert "just another buffer on the same clock" in page
    assert "CLICK_LANE = '__clicks__'" in page


def test_a_mark_can_carry_a_note_and_the_note_travels_with_it(tmp_path: Path) -> None:
    """Batching marks only helps if a row can say what was heard at it."""
    page = render(exhibit_for(tmp_path)[0])
    assert 'placeholder="what you heard"' in page
    assert "| time | output | what | note | numbers |" in page
    # A pipe inside a note would split the row it is describing.
    assert "replace(/\\|/g" in page


def test_typing_a_note_does_not_fire_the_keyboard_shortcuts(tmp_path: Path) -> None:
    """`c`, `m` and space are all letters someone will type into a note."""
    page = render(exhibit_for(tmp_path)[0])
    assert "if (e.target.tagName === 'INPUT') return;" in page


def test_a_note_is_written_onto_the_mark_without_re_rendering_the_list(
    tmp_path: Path,
) -> None:
    """Re-rendering per keystroke would take the cursor away mid-word."""
    page = render(exhibit_for(tmp_path)[0])
    assert "would take the cursor away mid-word" in page


def test_setting_a_loop_in_point_starts_a_new_selection(tmp_path: Path) -> None:
    """The ratchet: while a loop is active playback is confined to it, so the
    playhead can never be outside it, so setting either bound from the playhead
    could only ever shrink the window. Clearing the out point releases the
    confinement."""
    page = render(exhibit_for(tmp_path)[0])
    assert "one-way ratchet" in page
    assert "loop = { a: position(), b: null };" in page


def test_an_out_point_with_no_in_point_means_from_the_beginning(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "if (loop.a === null) loop.a = 0;" in page
    assert "never a surprise" in page


def test_a_pending_in_point_is_visible(tmp_path: Path) -> None:
    """Otherwise pressing `[` looks like nothing happened."""
    page = render(exhibit_for(tmp_path)[0])
    assert "loopin-mark" in page
    assert "press ] for the out point" in page


def test_the_selected_interval_gets_audible_boundaries(tmp_path: Path) -> None:
    """Auditioning an interval plays a margin either side; without an audible
    edge there is no telling whether a sound at the start of the loop is inside
    the span, spilling from the one before, or claimed by nothing."""
    page = render(exhibit_for(tmp_path)[0])
    assert "edge_in" in page and "edge_out" in page
    assert "spilling over from the one before it" in page
    assert "every interval edge" in page


def test_marking_does_not_type_its_own_shortcut_into_the_note(tmp_path: Path) -> None:
    """The keydown focuses the field, and the default action then types the 'm'."""
    page = render(exhibit_for(tmp_path)[0])
    assert "the browser's own\n    // default action then types the 'm' into it" in page


def test_both_halves_of_the_onset_rule_are_reachable(tmp_path: Path) -> None:
    """The shipped adaptive term is multiplier x median, so another multiplier
    is that same term scaled — no re-derivation of novelty, median or peaks."""
    page = render(exhibit_for(tmp_path)[0])
    assert 'id="multiplier"' in page
    assert "scale = multiplier / compiledMultiplier()" in page
    assert "function ruleIsCompiled()" in page


def test_the_self_check_covers_both_parameters(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "acceptAt(track, compiledFloor(), compiledMultiplier())" in page
    assert "THIS PAGE DISAGREES WITH THE COMPILER" in page


def test_the_view_pages_rather_than_scrolling_continuously(tmp_path: Path) -> None:
    """Every redraw recomputes peaks for five canvases; following at frame rate
    would cost more than it is worth."""
    page = render(exhibit_for(tmp_path)[0])
    assert "function followPlayhead()" in page
    assert "Page the view along rather than scrolling it continuously" in page
    # and the guard against re-triggering forever at the end of the file
    assert "re-triggers every\n    // frame" in page


def test_an_audition_loop_inside_the_view_does_not_page(tmp_path: Path) -> None:
    """Which is what lets auditioning a claim and following a passage coexist."""
    page = render(exhibit_for(tmp_path)[0])
    assert "A loop that fits inside the view never pages" in page


def test_a_loop_region_can_be_dragged_out(tmp_path: Path) -> None:
    """Specifying a region visually beats four keystrokes, and on a track that
    is one long interval it is the only way to work at all."""
    page = render(exhibit_for(tmp_path)[0])
    assert "pointerdown" in page and "pointerup" in page
    assert "setPointerCapture" in page
    assert "so a finger works the same as a" in page


def test_a_drag_and_a_click_are_separated_by_distance(tmp_path: Path) -> None:
    """They arrive as the same event sequence; only the distance differs."""
    page = render(exhibit_for(tmp_path)[0])
    assert "const DRAG_SLOP = 4;" in page
    assert "the click that follows the release is suppressed" in page


def test_the_suppression_flag_cannot_outlive_its_gesture(tmp_path: Path) -> None:
    """A release outside the strip produces no click, and a flag left standing
    would swallow the next legitimate one."""
    page = render(exhibit_for(tmp_path)[0])
    assert "would swallow the" in page
    assert "suppressClick = false;\n  drag = {" in page


def test_a_selection_in_progress_looks_different_from_a_committed_loop(
    tmp_path: Path,
) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "dragsel" in page
    assert "letting go is visibly the thing that commits it" in page
    assert "selecting ${Math.abs(drag.to - drag.from).toFixed(2)} s" in page


def test_fit_fits_the_loop_and_the_whole_file_is_its_own_action(tmp_path: Path) -> None:
    """Zooming out to the whole song is rarely what "fit" was wanted for."""
    page = render(exhibit_for(tmp_path)[0])
    assert "function loopFitBounds()" in page
    assert "function fitWholeFile()" in page
    assert "if (fit) setView(fit.a, fit.b); else setView(0, duration);" in page


def test_the_loop_extent_is_a_detent_in_both_zoom_directions(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "before the view becomes a microscope on the way in" in page
    assert "crossingIn" in page and "crossingOut" in page


def test_the_detent_tolerates_landing_near_it_and_cannot_stick(tmp_path: Path) -> None:
    """A strict crossing test leaves a press that travels three percent."""
    page = render(exhibit_for(tmp_path)[0])
    assert '"near enough" counts' in page
    assert "It cannot stick" in page


def test_the_overlay_is_clipped(tmp_path: Path) -> None:
    """Zoomed inside a loop, the loop's own box sits at a negative offset and
    would otherwise paint across the label column."""
    page = render(exhibit_for(tmp_path)[0])
    assert "#overlay { z-index: 3; overflow: hidden; }" in page
    assert "run out across the" in page


def test_a_control_hands_focus_back_after_it_is_used(tmp_path: Path) -> None:
    """A focused checkbox swallows the space bar, so play/pause stops working."""
    page = render(exhibit_for(tmp_path)[0])
    assert "swallows the shortcuts" in page
    assert "if (!typed) el.blur();" in page


def test_a_field_you_type_into_keeps_focus(tmp_path: Path) -> None:
    """Where the space bar means a space."""
    page = render(exhibit_for(tmp_path)[0])
    assert "el.type === 'text' || el.type === 'number'" in page


def test_a_mark_is_drawn_across_every_lane(tmp_path: Path) -> None:
    """So a claim already looked at is not looked at twice."""
    page = render(exhibit_for(tmp_path)[0])
    assert "markmarks" in page
    assert "is not\n   looked at twice" in page
    assert "function positionMarkLines" in page


def test_mark_lines_are_positioned_rather_than_rebuilt_each_frame(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path)[0])
    assert "marks change\n   rarely and the view changes often" in page
    assert "elsewhere" in page
