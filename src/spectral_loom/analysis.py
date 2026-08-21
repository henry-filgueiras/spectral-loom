"""Deterministic signal analysis: the transparent half of the compiler.

Three things are measured or inferred here and nothing else, because gate 4 of
``docs/roadmap.md`` admits exactly three event types:

``activity.sample``
    Short-time RMS and peak over a fixed window and hop. A **measurement**: any
    two people holding the same file and the same window get the same numbers,
    which is why the timeline files it under ``observed``.

``activity.interval``
    Where a track is "active", from an explicit hysteresis rule over those
    measurements. An **inference**, and a shallow one — it is a threshold with a
    memory, stated in full so that anybody can disagree with it precisely.

``onset``
    Where something starts, from a half-wave-rectified spectral flux novelty
    function with adaptive peak picking. Also an inference, and the least
    certain thing in the module.

The point of this stage is not detection accuracy. It is to establish an
attributable pipeline **whose mistakes a human can find**, which is why every
number below is a documented parameter rather than a library default, and why
none of it is a model. A model here would be a second unexamined opinion stacked
on top of the separator's.

Two design commitments are worth stating before the code, because both were
chosen against an easier alternative.

**Levels are absolute, and never normalized per track.** The obvious
implementation of "is this track active" normalizes each track by its own peak
and thresholds the result. On this project's first specimen that would have been
catastrophic in a way nobody would have noticed: HTDemucs' ``vocals`` output came
back at the separator's broadband noise floor, about -61 dBFS, and per-track
normalization would have found the loudest noise in it and called that a musical
event. Every threshold here is in dBFS against full scale, shared by every track,
so a track that is quiet stays quiet. The same commitment shapes the onset
detector: spectral flux is summed magnitude in the signal's own amplitude units,
so its floor is absolute too.

**Silence has a floor, not an infinity.** The RMS of digital silence is zero and
its level in dB is negative infinity, which JSON cannot represent and which no reader wants.
:data:`SILENCE_FLOOR_DBFS` is where the scale stops, it is a recorded parameter,
and it is far enough below anything this project has measured to be a floor
rather than a threshold in disguise.

Nothing here reads a manifest, writes a file, or knows what a timeline is. It
takes arrays and returns dataclasses, so it can be tested against synthesized
signals whose correct answer is known by construction.
"""

from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

Signal = npt.NDArray[np.float64]

#: Where the decibel scale stops. Digital silence has no level, and negative infinity is not a
#: number a document can carry. Chosen far below anything measurable in 16-bit
#: PCM at this project's levels: one least-significant bit of a 16-bit sample is
#: about -90 dBFS, so nothing real can approach this and it can never act as a
#: threshold by accident.
SILENCE_FLOOR_DBFS: Final = -120.0

#: How many decimal places survive into the timeline. Not cosmetic: the timeline
#: must be byte-identical across recompilations, and rounding is what keeps a
#: last-bit difference in a floating-point sum from becoming a different
#: document. Times are rounded to microseconds because the finest hop here is
#: eleven milliseconds; levels to a thousandth of a decibel, which is far below
#: audibility and far above float noise.
TIME_PLACES: Final = 6
DB_PLACES: Final = 3
AMPLITUDE_PLACES: Final = 6
FLUX_PLACES: Final = 6


class AnalysisError(Exception):
    """Audio could not be read, or a parameter makes no sense for it."""


def quantize(value: float, places: int) -> float:
    """Round for the document, normalizing negative zero away.

    ``-0.0`` and ``0.0`` are equal and serialize differently, which is exactly
    the kind of difference that turns a deterministic compiler into a
    nondeterministic one.
    """
    rounded = round(value, places)
    return 0.0 if rounded == 0 else rounded


# ---------------------------------------------------------------------------
# Reading.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Audio:
    """One decoded file, downmixed to mono for analysis.

    The downmix is a parameter, not a convenience: analysing the channel mean
    is a decision that changes results for anything panned, and it is recorded
    in the provenance of every stage that consumed this.
    """

    samples: Signal
    sample_rate_hz: int
    channels: int
    frames: int

    @property
    def duration_s(self) -> float:
        return self.frames / self.sample_rate_hz


def read_wav_mono(path: Path) -> Audio:
    """Decode a 16-bit PCM WAV into mono float64 in [-1, 1).

    Deliberately the standard library rather than ``soundfile``: this stage
    lives in the default environment, which has no cabinet in it, and the only
    audio it ever reads is written by this project as ``PCM_16``. A format it
    cannot read is a refusal that names the format rather than a silent
    misinterpretation of the bytes.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.getnframes()
            raw = handle.readframes(frames)
    except (OSError, wave.Error) as exc:
        raise AnalysisError(f"cannot read {path} as a WAV file: {exc}") from exc

    if width != 2:
        raise AnalysisError(
            f"{path} is {width * 8}-bit PCM, and this stage reads 16-bit. Every file this "
            f"project writes is PCM_16; a different width means the input did not come from "
            f"where this stage assumes it did."
        )
    if frames == 0 or rate <= 0:
        raise AnalysisError(f"{path} contains {frames} frames at {rate} Hz")

    interleaved = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if interleaved.size != frames * channels:
        raise AnalysisError(
            f"{path} declares {frames} frames of {channels} channels and holds "
            f"{interleaved.size} samples; the file is truncated"
        )
    mono = interleaved.reshape(-1, channels).mean(axis=1)
    return Audio(samples=mono, sample_rate_hz=rate, channels=channels, frames=frames)


# ---------------------------------------------------------------------------
# Framing, shared by both analyses.
# ---------------------------------------------------------------------------


def frame_count(length: int, window: int, hop: int) -> int:
    """How many whole windows fit. A partial trailing window is not analysed.

    Dropping it rather than zero-padding it, because a padded final window
    measures the padding: its RMS would fall for a reason that has nothing to do
    with the recording, and the timeline would end with a fade nobody performed.
    """
    if window <= 0 or hop <= 0:
        raise AnalysisError(f"window and hop must be positive, got window={window} hop={hop}")
    if length < window:
        return 0
    return 1 + (length - window) // hop


def frames_of(signal: Signal, window: int, hop: int) -> Signal:
    """A (frames, window) view of the signal, without copying it per frame."""
    count = frame_count(signal.size, window, hop)
    if count == 0:
        return np.empty((0, window), dtype=np.float64)
    indices = np.arange(window)[None, :] + hop * np.arange(count)[:, None]
    framed: Signal = signal[indices]
    return framed


def dbfs(amplitude: Signal) -> Signal:
    """Amplitude to dBFS, floored rather than allowed to reach negative infinity."""
    out = np.full(amplitude.shape, SILENCE_FLOOR_DBFS, dtype=np.float64)
    positive = amplitude > 0
    out[positive] = 20.0 * np.log10(amplitude[positive])
    return np.maximum(out, SILENCE_FLOOR_DBFS)


def scalar_dbfs(amplitude: float) -> float:
    """The one-value form, so a report and an event agree on the floor."""
    if amplitude <= 0:
        return SILENCE_FLOOR_DBFS
    return max(20.0 * math.log10(amplitude), SILENCE_FLOOR_DBFS)


# ---------------------------------------------------------------------------
# activity.sample — a measurement.
# ---------------------------------------------------------------------------

#: Window and hop for the activity measurement, **in samples at the analysed
#: rate**. In samples rather than seconds because a hop that does not land on a
#: whole sample accumulates drift across a forty-five second file, and a
#: timeline whose event times drift is a timeline that cannot be spot-checked.
#:
#: 2048 and 1024 at 44.1 kHz are 46.44 ms and 23.22 ms. Long enough that the
#: measurement is a level rather than a waveform, short enough that a note decay
#: is several frames. Arbitrary within an order of magnitude, and recorded as a
#: parameter so that changing it is a cache invalidation rather than a footnote.
ACTIVITY_WINDOW_SAMPLES: Final = 2048
ACTIVITY_HOP_SAMPLES: Final = 1024


@dataclass(frozen=True)
class ActivityMeasurement:
    """Short-time level over one track. Observed, and recomputable by anyone."""

    start_s: Signal
    rms: Signal
    rms_dbfs: Signal
    peak: Signal
    window_samples: int
    hop_samples: int
    sample_rate_hz: int

    @property
    def window_s(self) -> float:
        return self.window_samples / self.sample_rate_hz

    @property
    def hop_s(self) -> float:
        return self.hop_samples / self.sample_rate_hz

    def __len__(self) -> int:
        return int(self.start_s.size)


def measure_activity(
    audio: Audio,
    *,
    window_samples: int = ACTIVITY_WINDOW_SAMPLES,
    hop_samples: int = ACTIVITY_HOP_SAMPLES,
) -> ActivityMeasurement:
    """Root-mean-square and peak amplitude per window. No thresholds, no opinion."""
    windows = frames_of(audio.samples, window_samples, hop_samples)
    if windows.shape[0] == 0:
        empty = np.empty(0, dtype=np.float64)
        return ActivityMeasurement(
            start_s=empty,
            rms=empty,
            rms_dbfs=empty,
            peak=empty,
            window_samples=window_samples,
            hop_samples=hop_samples,
            sample_rate_hz=audio.sample_rate_hz,
        )

    rms = np.sqrt(np.mean(np.square(windows), axis=1))
    peak = np.max(np.abs(windows), axis=1)
    starts = np.arange(windows.shape[0], dtype=np.float64) * hop_samples / audio.sample_rate_hz
    return ActivityMeasurement(
        start_s=starts,
        rms=rms,
        rms_dbfs=dbfs(rms),
        peak=peak,
        window_samples=window_samples,
        hop_samples=hop_samples,
        sample_rate_hz=audio.sample_rate_hz,
    )


# ---------------------------------------------------------------------------
# activity.interval — an inference.
# ---------------------------------------------------------------------------

#: The hysteresis pair, in **absolute dBFS**, shared by every track.
#:
#: Chosen by measuring this project's accepted separation rather than by taste,
#: and the measurement is the argument. All four HTDemucs outputs sit on a
#: broadband noise floor near -61 dBFS; the loudest frame in the near-silent
#: ``vocals`` output reaches -54.0 dBFS and its 99th percentile is -59.3. Musical
#: material in the other three outputs lives between -40 and -12 dBFS.
#:
#: -50 dBFS to enter is eleven decibels clear of that noise floor and four clear
#: of anything in ``vocals``; -56 dBFS to leave lets a note decay finish without
#: chattering. Sweeping the pair from (-45, -52) to (-55, -58) moved inferred
#: coverage by three percentage points and never gave ``vocals`` a single
#: interval, so these sit on a plateau rather than on a fitted point.
#:
#: The exit threshold cannot start an interval on its own — that is what makes
#: the pair hysteresis rather than two thresholds — so a track that never
#: reaches -50 dBFS is never active, however close to -56 it hovers.
ACTIVITY_ENTER_DBFS: Final = -50.0
ACTIVITY_EXIT_DBFS: Final = -56.0

#: Intervals shorter than this are discarded, and gaps shorter than this are
#: closed. Both are arbitrary round numbers at the scale of a short musical
#: note, chosen so that a single stray window neither creates an interval nor
#: splits one, and recorded so that a later specimen can argue with them.
ACTIVITY_MIN_DURATION_S: Final = 0.10
ACTIVITY_MERGE_GAP_S: Final = 0.10


@dataclass(frozen=True)
class ActivityInterval:
    """One span a rule called active, with the evidence for calling it that."""

    start_s: float
    end_s: float
    frames: int
    min_rms_dbfs: float
    max_rms_dbfs: float
    mean_rms_dbfs: float
    merged_gaps: int

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class _Span:
    """A run of active frames while it is still being merged with its neighbours."""

    start_s: float
    end_s: float
    first_frame: int
    last_frame: int
    joins: int


def infer_intervals(
    measurement: ActivityMeasurement,
    *,
    enter_dbfs: float = ACTIVITY_ENTER_DBFS,
    exit_dbfs: float = ACTIVITY_EXIT_DBFS,
    min_duration_s: float = ACTIVITY_MIN_DURATION_S,
    merge_gap_s: float = ACTIVITY_MERGE_GAP_S,
) -> list[ActivityInterval]:
    """Threshold the measurement with hysteresis, then merge and filter.

    In four stated steps, in this order, because the order changes the answer:

    1. A run begins at the first frame at or above ``enter_dbfs``.
    2. It ends at the first frame below ``exit_dbfs``. Between the two the
       track stays active, which is what stops a decaying note from chattering
       into a dozen intervals.
    3. Runs separated by less than ``merge_gap_s`` become one, and the number of
       joins is carried on the result so that a suspiciously long interval can
       be traced to the rule that made it.
    4. What remains shorter than ``min_duration_s`` is discarded.

    An interval spans from the start of its first window to the **end** of its
    last, because the last window's level is evidence about the audio underneath
    the whole window rather than about its first sample.
    """
    if enter_dbfs < exit_dbfs:
        raise AnalysisError(
            f"the enter threshold ({enter_dbfs} dBFS) is below the exit threshold "
            f"({exit_dbfs} dBFS); that is not hysteresis, it is a rule that can never leave "
            f"a state it entered"
        )
    if len(measurement) == 0:
        return []

    levels = measurement.rms_dbfs
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, level in enumerate(levels):
        if start is None:
            if level >= enter_dbfs:
                start = index
        elif level < exit_dbfs:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(levels)))

    window_s = measurement.window_s
    hop_s = measurement.hop_s

    merged: list[_Span] = []
    for first, last in runs:
        begin = first * hop_s
        finish = (last - 1) * hop_s + window_s
        if merged and begin - merged[-1].end_s <= merge_gap_s:
            merged[-1].end_s = finish
            merged[-1].last_frame = last
            merged[-1].joins += 1
        else:
            merged.append(_Span(begin, finish, first, last, 0))

    intervals: list[ActivityInterval] = []
    for span in merged:
        if span.end_s - span.start_s < min_duration_s:
            continue
        window = levels[span.first_frame : span.last_frame]
        intervals.append(
            ActivityInterval(
                start_s=quantize(span.start_s, TIME_PLACES),
                end_s=quantize(span.end_s, TIME_PLACES),
                frames=span.last_frame - span.first_frame,
                min_rms_dbfs=quantize(float(window.min()), DB_PLACES),
                max_rms_dbfs=quantize(float(window.max()), DB_PLACES),
                mean_rms_dbfs=quantize(float(window.mean()), DB_PLACES),
                merged_gaps=span.joins,
            )
        )
    return intervals


# ---------------------------------------------------------------------------
# onset — an inference, and the least certain thing here.
# ---------------------------------------------------------------------------

#: The onset analysis has its own framing, finer than the activity one, because
#: the questions differ: a level wants a window long enough to be a level, and a
#: transient wants a hop short enough to place it. 2048 and 512 at 44.1 kHz are
#: a 46.44 ms window every 11.61 ms, and **11.61 ms is the temporal resolution
#: of every onset this project reports**. No event is more precise than that,
#: whatever its decimal places suggest.
ONSET_FFT_SAMPLES: Final = 2048
ONSET_HOP_SAMPLES: Final = 512

#: Peak picking, in frames at the hop above.
#:
#: ``median_radius`` = 9 is ±104 ms of local context: long enough to describe the
#: background the peak stands out from, short enough not to average across a bar.
#: ``peak_radius`` = 3 is ±35 ms, inside which only the largest flux value can be
#: an onset. ``min_gap_s`` then refuses a second onset within 50 ms of the last,
#: which is faster than this project has any evidence a part is played.
ONSET_MEDIAN_RADIUS_FRAMES: Final = 9
ONSET_PEAK_RADIUS_FRAMES: Final = 3
ONSET_MIN_GAP_S: Final = 0.05

#: The threshold rule: ``flux >= median_multiplier * local_median + flux_floor``.
#:
#: The multiplier is relative and adapts to how busy the track is around the
#: peak. The floor is **absolute**, in the same summed-magnitude units the flux
#: is measured in, and it is what keeps a near-silent track unclaimed: on this
#: project's accepted separation the ``vocals`` output's largest flux value in
#: the whole file is 4.7, against a floor of 20, while ``bass``, ``drums`` and
#: ``other`` reach 326, 1397 and 223. Normalizing per track would have erased
#: exactly that distinction.
#:
#: Sweeping the multiplier from 1.5 to 3.0 and the floor from 5 to 20 moved
#: ``drums`` between 153 and 180 events and never gave ``vocals`` one, so these
#: also sit on a plateau. They are still a baseline, not a calibration.
ONSET_MEDIAN_MULTIPLIER: Final = 2.0
ONSET_FLUX_FLOOR: Final = 20.0


@dataclass(frozen=True)
class Onset:
    """One onset hypothesis, with the numbers that produced it.

    Deliberately without a confidence. Spectral flux is not a probability and
    has no calibration, and dividing it by something to make it land in [0, 1]
    would manufacture a confidence out of arithmetic. What is carried instead is
    the raw statistic, the threshold it beat, and by how much — which is what a
    person needs in order to disagree.
    """

    start_s: float
    flux: float
    threshold: float
    margin: float
    local_median: float
    frame_rms_dbfs: float


@dataclass(frozen=True)
class OnsetAnalysis:
    """The novelty curve and the events picked off it."""

    start_s: Signal
    flux: Signal
    threshold: Signal
    frame_rms_dbfs: Signal
    onsets: list[Onset]
    fft_samples: int
    hop_samples: int
    sample_rate_hz: int

    @property
    def resolution_s(self) -> float:
        """The finest distinction this analysis can draw between two times."""
        return self.hop_samples / self.sample_rate_hz


def hann_window(size: int) -> Signal:
    """A periodic Hann window, written out rather than named.

    ``np.hanning`` is the *symmetric* window, which differs from this one and is
    the wrong choice for overlapping analysis. Spelling the formula out means the
    document's parameters describe the window that actually ran.
    """
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(size, dtype=np.float64) / size)


def spectral_flux(
    audio: Audio, *, fft_samples: int, hop_samples: int
) -> tuple[Signal, Signal, Signal]:
    """Half-wave-rectified magnitude difference between successive spectra.

    Returns frame start times, the flux, and each frame's own RMS level in dBFS.

    Only *increases* count. A note ending is a spectral change too, and counting
    it would make every release an onset — so the difference is rectified before
    it is summed, which is the whole idea and is one line.

    The first frame's flux is zero by definition: it has no predecessor. An
    attack in the very first window can therefore only be reported one hop
    later, and that boundary is a property of the method rather than of the
    audio.
    """
    windows = frames_of(audio.samples, fft_samples, hop_samples)
    if windows.shape[0] == 0:
        empty = np.empty(0, dtype=np.float64)
        return empty, empty, empty

    spectra = np.abs(np.fft.rfft(windows * hann_window(fft_samples), axis=1))
    rising = np.maximum(np.diff(spectra, axis=0), 0.0).sum(axis=1)
    flux = np.concatenate([[0.0], rising])
    starts = np.arange(windows.shape[0], dtype=np.float64) * hop_samples / audio.sample_rate_hz
    level = dbfs(np.sqrt(np.mean(np.square(windows), axis=1)))
    return starts, flux, level


def rolling_median(values: Signal, radius: int) -> Signal:
    """Median over a centred window, edges extended rather than shortened.

    Extending rather than shrinking the window keeps the threshold defined for
    every frame. The alternative — a shorter window at the edges — makes the
    first and last frames easier to trigger for no reason to do with the music.
    """
    if radius <= 0:
        return values.copy()
    padded = np.pad(values, (radius, radius), mode="edge")
    indices = np.arange(values.size)[:, None] + np.arange(2 * radius + 1)[None, :]
    medians: Signal = np.median(padded[indices], axis=1)
    return medians


def infer_onsets(
    audio: Audio,
    *,
    fft_samples: int = ONSET_FFT_SAMPLES,
    hop_samples: int = ONSET_HOP_SAMPLES,
    median_radius_frames: int = ONSET_MEDIAN_RADIUS_FRAMES,
    peak_radius_frames: int = ONSET_PEAK_RADIUS_FRAMES,
    median_multiplier: float = ONSET_MEDIAN_MULTIPLIER,
    flux_floor: float = ONSET_FLUX_FLOOR,
    min_gap_s: float = ONSET_MIN_GAP_S,
) -> OnsetAnalysis:
    """Spectral flux, an adaptive threshold, and local-maximum peak picking.

    A frame is an onset when all four hold:

    1. its flux is the largest within ``peak_radius_frames`` either side;
    2. its flux is at least ``median_multiplier`` times the local median plus
       ``flux_floor``;
    3. it is at least ``min_gap_s`` after the previous accepted onset;
    4. — there is no fourth. Condition 2's floor is absolute, so it *is* the
       level gate, and adding a second one in dBFS would say the same thing
       twice.
    """
    starts, flux, level = spectral_flux(audio, fft_samples=fft_samples, hop_samples=hop_samples)
    if flux.size == 0:
        empty = np.empty(0, dtype=np.float64)
        return OnsetAnalysis(
            start_s=empty,
            flux=empty,
            threshold=empty,
            frame_rms_dbfs=empty,
            onsets=[],
            fft_samples=fft_samples,
            hop_samples=hop_samples,
            sample_rate_hz=audio.sample_rate_hz,
        )

    local_median = rolling_median(flux, median_radius_frames)
    threshold = median_multiplier * local_median + flux_floor

    if peak_radius_frames > 0:
        padded = np.pad(
            flux, (peak_radius_frames, peak_radius_frames), mode="constant", constant_values=-1.0
        )
        indices = np.arange(flux.size)[:, None] + np.arange(2 * peak_radius_frames + 1)[None, :]
        is_peak = flux >= padded[indices].max(axis=1)
    else:
        is_peak = np.ones(flux.size, dtype=bool)

    onsets: list[Onset] = []
    last = -math.inf
    for index in np.flatnonzero(is_peak & (flux >= threshold)):
        moment = float(starts[index])
        if moment - last < min_gap_s:
            continue
        last = moment
        onsets.append(
            Onset(
                start_s=quantize(moment, TIME_PLACES),
                flux=quantize(float(flux[index]), FLUX_PLACES),
                threshold=quantize(float(threshold[index]), FLUX_PLACES),
                margin=quantize(float(flux[index] - threshold[index]), FLUX_PLACES),
                local_median=quantize(float(local_median[index]), FLUX_PLACES),
                frame_rms_dbfs=quantize(float(level[index]), DB_PLACES),
            )
        )

    return OnsetAnalysis(
        start_s=starts,
        flux=flux,
        threshold=threshold,
        frame_rms_dbfs=level,
        onsets=onsets,
        fft_samples=fft_samples,
        hop_samples=hop_samples,
        sample_rate_hz=audio.sample_rate_hz,
    )
