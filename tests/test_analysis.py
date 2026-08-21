"""Tests for the deterministic analysis, against signals whose answer is known.

Every fixture here is synthesized in ``tmp_path`` and every assertion is about
*semantics* rather than about an implementation accident. A test that pinned
"the third frame's RMS is 0.0704" would pass forever and mean nothing; a test
that says "a burst between 0.5 s and 1.0 s produces an interval covering
0.5 s to 1.0 s" fails the day the rule stops meaning what it says.

The most important test in the file is the one about near-silent noise, because
it is the specific mistake this module was written to avoid. HTDemucs' `vocals`
output on this project's accepted separation came back at the separator's own
broadband noise floor. An activity detector that normalized each track by its
own peak would have found the loudest noise in it, called that a musical event,
and produced a confident timeline claim about nothing at all — and nobody would
have noticed, because the events would have looked exactly like real ones.
"""

from __future__ import annotations

import struct
import wave
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from spectral_loom.analysis import (
    ACTIVITY_ENTER_DBFS,
    ACTIVITY_EXIT_DBFS,
    ACTIVITY_HOP_SAMPLES,
    ACTIVITY_WINDOW_SAMPLES,
    SILENCE_FLOOR_DBFS,
    AnalysisError,
    Audio,
    dbfs,
    frame_count,
    hann_window,
    infer_intervals,
    infer_onsets,
    measure_activity,
    quantize,
    read_wav_mono,
    scalar_dbfs,
)

RATE = 8000
WINDOW_S = ACTIVITY_WINDOW_SAMPLES / RATE
HOP_S = ACTIVITY_HOP_SAMPLES / RATE


def audio_of(samples: np.ndarray, rate: int = RATE) -> Audio:
    values = np.asarray(samples, dtype=np.float64)
    return Audio(samples=values, sample_rate_hz=rate, channels=1, frames=values.size)


def seconds(count: float, rate: int = RATE) -> int:
    return round(count * rate)


def silence(duration_s: float) -> np.ndarray:
    return np.zeros(seconds(duration_s), dtype=np.float64)


def tone(duration_s: float, *, amplitude: float, hz: float = 220.0) -> np.ndarray:
    n = np.arange(seconds(duration_s), dtype=np.float64)
    return amplitude * np.sin(2.0 * np.pi * hz * n / RATE)


def place(total_s: float, spans: list[tuple[float, float]], *, amplitude: float) -> np.ndarray:
    """Silence with tone bursts placed at known times."""
    signal = silence(total_s)
    for begin, end in spans:
        piece = tone(end - begin, amplitude=amplitude)
        signal[seconds(begin) : seconds(begin) + piece.size] = piece
    return signal


def impulses_at(total_s: float, moments: list[float], *, amplitude: float = 0.8) -> np.ndarray:
    """Short decaying clicks, which is what a transient detector is for."""
    signal = silence(total_s)
    length = seconds(0.02)
    envelope = np.exp(-np.arange(length, dtype=np.float64) / (length / 4))
    click = (
        amplitude
        * envelope
        * np.sin(2.0 * np.pi * 900.0 * np.arange(length, dtype=np.float64) / RATE)
    )
    for moment in moments:
        start = seconds(moment)
        signal[start : start + length] = click
    return signal


# ---------------------------------------------------------------------------
# Framing and scales.
# ---------------------------------------------------------------------------


def test_only_whole_windows_are_analysed() -> None:
    """A padded final window would measure the padding and fake a fade-out."""
    assert frame_count(2048, 2048, 1024) == 1
    assert frame_count(3071, 2048, 1024) == 1
    assert frame_count(3072, 2048, 1024) == 2
    assert frame_count(2047, 2048, 1024) == 0


def test_a_window_larger_than_the_signal_produces_no_frames() -> None:
    measurement = measure_activity(audio_of(silence(0.05)))
    assert len(measurement) == 0
    assert infer_intervals(measurement) == []
    assert infer_onsets(audio_of(silence(0.05))).onsets == []


def test_frames_start_on_the_hop() -> None:
    measurement = measure_activity(audio_of(silence(2.0)))
    assert measurement.start_s[0] == 0.0
    assert measurement.start_s[1] == pytest.approx(HOP_S)
    assert measurement.start_s[5] == pytest.approx(5 * HOP_S)


def test_silence_has_a_floor_rather_than_an_infinity() -> None:
    assert scalar_dbfs(0.0) == SILENCE_FLOOR_DBFS
    assert dbfs(np.array([0.0, 1.0])).tolist() == [SILENCE_FLOOR_DBFS, 0.0]
    assert np.isfinite(dbfs(np.zeros(4))).all()


def test_negative_zero_is_normalized_away() -> None:
    """Two values that compare equal must not serialize differently."""
    assert quantize(-0.0001, 3) == 0.0
    assert not str(quantize(-0.0001, 3)).startswith("-")


def test_the_hann_window_is_the_periodic_one() -> None:
    """`np.hanning` is symmetric, which is the wrong window for overlap."""
    window = hann_window(8)
    assert window[0] == pytest.approx(0.0)
    assert not np.allclose(window, np.hanning(8))


# ---------------------------------------------------------------------------
# activity.sample: a measurement, and it had better measure.
# ---------------------------------------------------------------------------


def test_measured_level_matches_a_known_amplitude() -> None:
    """A full-window sine of amplitude a has RMS a/sqrt(2), and no opinion."""
    measurement = measure_activity(audio_of(tone(2.0, amplitude=0.5)))
    # Not exact: 2048 samples at 8 kHz is 56.3 cycles of a 220 Hz sine, so the
    # window ends part-way through one. A tolerance, not a fudge.
    assert measurement.rms.min() == pytest.approx(0.5 / np.sqrt(2), rel=5e-3)
    assert measurement.peak.max() == pytest.approx(0.5, rel=1e-2)
    assert measurement.rms_dbfs.max() == pytest.approx(20 * np.log10(0.5 / np.sqrt(2)), abs=0.05)


def test_measured_activity_corresponds_to_the_windows_it_covers() -> None:
    """The loud frames are the ones whose window overlaps the loud audio."""
    signal = place(3.0, [(1.0, 2.0)], amplitude=0.5)
    measurement = measure_activity(audio_of(signal))
    loud = measurement.rms_dbfs > -20
    for index, is_loud in enumerate(loud):
        start = index * HOP_S
        overlaps = start < 2.0 and start + WINDOW_S > 1.0
        if is_loud:
            assert overlaps, f"frame at {start:.3f}s is loud and does not overlap the burst"


# ---------------------------------------------------------------------------
# activity.interval: an explicit rule, with explicit consequences.
# ---------------------------------------------------------------------------


def test_a_burst_becomes_an_interval_covering_it() -> None:
    signal = place(4.0, [(1.0, 2.5)], amplitude=0.4)
    intervals = infer_intervals(measure_activity(audio_of(signal)))
    assert len(intervals) == 1
    # The framing cannot resolve better than one window, so the interval starts
    # no later than the burst and ends no earlier, within that window.
    assert intervals[0].start_s <= 1.0
    assert intervals[0].start_s > 1.0 - WINDOW_S
    assert intervals[0].end_s >= 2.5
    assert intervals[0].end_s < 2.5 + WINDOW_S


def test_digital_silence_is_never_active() -> None:
    assert infer_intervals(measure_activity(audio_of(silence(4.0)))) == []


def test_near_silent_noise_does_not_become_maximally_active() -> None:
    """The `vocals` lesson, as a test.

    A track whose whole content sits at about -61 dBFS is the separator's noise
    floor. A per-track normalizing detector would find its loudest moment and
    call that an event. An absolute threshold leaves it alone.
    """
    generator = np.random.default_rng(20260820)
    noise = generator.normal(0.0, 0.0009, seconds(4.0))
    measurement = measure_activity(audio_of(noise))

    assert measurement.rms_dbfs.max() < ACTIVITY_ENTER_DBFS
    assert infer_intervals(measurement) == []
    assert infer_onsets(audio_of(noise)).onsets == []


def test_a_quiet_track_and_a_loud_track_are_not_made_equal() -> None:
    """The same shape at two levels must not produce the same answer.

    This is the property that a normalizing implementation would break while
    every other test in this file kept passing.
    """
    shape = place(4.0, [(1.0, 2.5)], amplitude=0.4)
    loud = infer_intervals(measure_activity(audio_of(shape)))
    quiet = infer_intervals(measure_activity(audio_of(shape * 0.0005)))
    assert len(loud) == 1
    assert quiet == []


def test_hysteresis_keeps_a_dipping_signal_in_one_interval() -> None:
    """A level between the two thresholds continues an interval, never starts one."""
    between = 10 ** ((ACTIVITY_ENTER_DBFS - 2) / 20) * np.sqrt(2)
    above = 10 ** ((ACTIVITY_ENTER_DBFS + 6) / 20) * np.sqrt(2)
    signal = np.concatenate(
        [
            tone(1.0, amplitude=above),
            tone(1.0, amplitude=between),
            tone(1.0, amplitude=above),
        ]
    )
    intervals = infer_intervals(measure_activity(audio_of(signal)), merge_gap_s=0.0)
    assert len(intervals) == 1

    # And the same middle level cannot begin one on its own.
    alone = np.concatenate([silence(1.0), tone(2.0, amplitude=between)])
    assert infer_intervals(measure_activity(audio_of(alone)), merge_gap_s=0.0) == []


def test_the_merge_rule_decides_whether_two_bursts_are_one_interval() -> None:
    """One signal, two rules, so the difference is the rule and nothing else."""
    signal = place(6.0, [(0.5, 1.5), (3.0, 4.0)], amplitude=0.4)
    measurement = measure_activity(audio_of(signal))

    kept = infer_intervals(measurement, merge_gap_s=0.1)
    assert len(kept) == 2
    assert [interval.merged_gaps for interval in kept] == [0, 0]

    merged = infer_intervals(measurement, merge_gap_s=2.0)
    assert len(merged) == 1
    assert merged[0].merged_gaps == 1
    assert merged[0].start_s == kept[0].start_s
    assert merged[0].end_s == kept[1].end_s


def test_an_interval_shorter_than_the_minimum_is_discarded() -> None:
    signal = place(4.0, [(1.0, 1.02)], amplitude=0.4)
    assert infer_intervals(measure_activity(audio_of(signal)), min_duration_s=1.0) == []


def test_an_interval_carries_the_levels_that_justified_it() -> None:
    signal = place(4.0, [(1.0, 2.5)], amplitude=0.4)
    interval = infer_intervals(measure_activity(audio_of(signal)))[0]
    assert interval.min_rms_dbfs <= interval.mean_rms_dbfs <= interval.max_rms_dbfs
    assert interval.max_rms_dbfs >= ACTIVITY_ENTER_DBFS
    assert interval.frames > 0


def test_thresholds_that_are_not_hysteresis_are_refused() -> None:
    measurement = measure_activity(audio_of(tone(2.0, amplitude=0.4)))
    with pytest.raises(AnalysisError, match="that is not hysteresis"):
        infer_intervals(measurement, enter_dbfs=-60.0, exit_dbfs=-40.0)


def test_the_default_thresholds_are_a_pair_with_room_between_them() -> None:
    assert ACTIVITY_ENTER_DBFS > ACTIVITY_EXIT_DBFS


# ---------------------------------------------------------------------------
# onset: hypotheses, with the numbers that produced them.
# ---------------------------------------------------------------------------


def test_one_impulse_produces_one_onset_at_about_the_right_time() -> None:
    analysis = infer_onsets(audio_of(impulses_at(3.0, [1.5])))
    assert len(analysis.onsets) == 1
    # No onset is more precise than one hop; the window that first contains the
    # attack is the one that can report it, so the tolerance is a window.
    assert abs(analysis.onsets[0].start_s - 1.5) <= analysis.fft_samples / RATE


def test_repeated_impulses_produce_one_onset_each() -> None:
    moments = [0.6, 1.2, 1.8, 2.4, 3.0]
    analysis = infer_onsets(audio_of(impulses_at(4.0, moments)))
    assert len(analysis.onsets) == len(moments)
    for onset, expected in zip(analysis.onsets, moments, strict=True):
        assert abs(onset.start_s - expected) <= analysis.fft_samples / RATE


def test_onsets_are_in_time_order_and_respect_the_minimum_gap() -> None:
    analysis = infer_onsets(audio_of(impulses_at(4.0, [0.6, 1.2, 1.8, 2.4, 3.0])))
    times = [onset.start_s for onset in analysis.onsets]
    assert times == sorted(times)
    assert all(b - a >= 0.05 for a, b in pairwise(times))


def test_a_sustained_tone_is_not_a_stream_of_onsets() -> None:
    """Only increases count. A note that is merely continuing is not an attack."""
    analysis = infer_onsets(audio_of(tone(4.0, amplitude=0.4)))
    assert len(analysis.onsets) <= 1


def test_an_onset_carries_no_confidence_and_reports_its_own_numbers() -> None:
    """Spectral flux is not a probability, so no probability is invented."""
    onset = infer_onsets(audio_of(impulses_at(3.0, [1.5]))).onsets[0]
    assert not hasattr(onset, "confidence")
    assert onset.flux > onset.threshold
    assert onset.margin == pytest.approx(onset.flux - onset.threshold, abs=1e-6)
    assert onset.frame_rms_dbfs > SILENCE_FLOOR_DBFS


def test_the_first_frame_cannot_be_an_onset() -> None:
    """It has no predecessor, and its flux is zero by definition."""
    analysis = infer_onsets(audio_of(impulses_at(3.0, [0.0])))
    assert all(onset.start_s > 0 for onset in analysis.onsets)


# ---------------------------------------------------------------------------
# Reading.
# ---------------------------------------------------------------------------


def write_wav(path: Path, signal: np.ndarray, *, rate: int = RATE, channels: int = 1) -> Path:
    frames = np.clip(signal, -1.0, 1.0)
    data = (frames * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(data)
    return path


def test_a_stereo_file_is_read_as_the_channel_mean(tmp_path: Path) -> None:
    left = tone(0.5, amplitude=0.5)
    right = -left
    interleaved = np.empty(left.size * 2, dtype=np.float64)
    interleaved[0::2] = left
    interleaved[1::2] = right
    audio = read_wav_mono(write_wav(tmp_path / "s.wav", interleaved, channels=2))

    assert audio.channels == 2
    assert audio.frames == left.size
    # The mean of a signal and its inverse is silence, which is exactly what a
    # channel-mean downmix does and exactly why it is a recorded parameter.
    assert np.abs(audio.samples).max() < 1e-3


def test_a_read_file_reports_its_own_duration(tmp_path: Path) -> None:
    audio = read_wav_mono(write_wav(tmp_path / "s.wav", tone(1.25, amplitude=0.3)))
    assert audio.sample_rate_hz == RATE
    assert audio.duration_s == pytest.approx(1.25, abs=1e-3)


def test_a_width_this_stage_does_not_read_is_a_refusal_naming_it(tmp_path: Path) -> None:
    path = tmp_path / "eight.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(RATE)
        handle.writeframes(struct.pack("<128B", *([128] * 128)))
    with pytest.raises(AnalysisError, match="8-bit PCM"):
        read_wav_mono(path)


def test_something_that_is_not_a_wav_is_a_refusal_naming_the_path(tmp_path: Path) -> None:
    path = tmp_path / "not-audio.wav"
    path.write_bytes(b"this is not a RIFF header")
    with pytest.raises(AnalysisError, match=r"not-audio\.wav"):
        read_wav_mono(path)


# ---------------------------------------------------------------------------
# Determinism.
# ---------------------------------------------------------------------------


def test_the_same_signal_analysed_twice_gives_identical_numbers() -> None:
    signal = place(4.0, [(0.5, 1.5), (2.0, 3.0)], amplitude=0.4)
    first = infer_intervals(measure_activity(audio_of(signal)))
    second = infer_intervals(measure_activity(audio_of(signal.copy())))
    assert first == second

    left = infer_onsets(audio_of(impulses_at(3.0, [0.5, 1.5]))).onsets
    right = infer_onsets(audio_of(impulses_at(3.0, [0.5, 1.5]))).onsets
    assert left == right


@pytest.fixture
def tone_file(tmp_path: Path) -> Callable[..., Path]:
    def _write(name: str, signal: np.ndarray, **kwargs: int) -> Path:
        return write_wav(tmp_path / name, signal, **kwargs)

    return _write


def test_reading_and_analysing_a_written_file_agrees_with_the_array(
    tone_file: Callable[..., Path],
) -> None:
    signal = place(4.0, [(1.0, 2.5)], amplitude=0.4)
    from_disk = infer_intervals(measure_activity(read_wav_mono(tone_file("a.wav", signal))))
    in_memory = infer_intervals(measure_activity(audio_of(signal)))
    assert len(from_disk) == len(in_memory) == 1
    assert from_disk[0].start_s == in_memory[0].start_s
