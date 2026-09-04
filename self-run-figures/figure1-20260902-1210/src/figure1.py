"""Deterministic loaders, diagnostics, and plotting for StructBeat Figure 1."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


CASES = ("smc_221", "smc_117")
METHODS = ("direct", "fixed_semimarkov", "dbn", "casm")
METHOD_LABELS = {
    "direct": "Direct",
    "fixed_semimarkov": "Fixed Semi-Markov",
    "dbn": "DBN (adjusted)",
    "casm": "CASM",
}
COLORS = {
    "activation": "#2bb8b2",
    "direct": "#409eff",
    "fixed_semimarkov": "#ff7a3d",
    "dbn": "#59c879",
    "casm": "#9270ed",
    "groundtruth": "#242629",
    "grid": "#d9dde2",
    "muted": "#777b80",
}
MARKERS = {
    "direct": "D",
    "fixed_semimarkov": "s",
    "dbn": "^",
    "casm": "o",
}


def sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    result = np.empty_like(values)
    positive = values >= 0
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_values = np.exp(values[~positive])
    result[~positive] = exp_values / (1.0 + exp_values)
    return result


def _paths(root: Path, case: str) -> dict[str, Path]:
    if case not in CASES:
        raise ValueError(f"Unknown case {case!r}; choose one of {CASES}.")
    return {
        "cache": root / "data" / "raw_cache" / f"{case}_beat_this_oof.npz",
        "payload": root / "data" / "figure_payloads" / f"{case}.json",
        "spectrogram": root / "data" / "spectrograms" / f"{case}_spectrogram.npy",
    }


def load_case(root: str | Path, case: str) -> dict:
    """Load one case and verify that every source refers to the same frames."""
    root = Path(root).resolve()
    paths = _paths(root, case)
    with np.load(paths["cache"], allow_pickle=False) as cache:
        raw = {key: np.asarray(cache[key]).copy() for key in cache.files}
    payload = json.loads(paths["payload"].read_text(encoding="utf-8"))
    spectrogram = np.load(paths["spectrogram"], allow_pickle=False)

    beat_probability = sigmoid(raw["beat_logits"])
    downbeat_probability = sigmoid(raw["downbeat_logits"])
    payload_beat = np.asarray(payload["beat_probability"], dtype=np.float64)
    payload_downbeat = np.asarray(payload["downbeat_probability"], dtype=np.float64)
    truth_beat = np.asarray(payload["truth"]["beat_times"], dtype=np.float64)
    truth_downbeat = np.asarray(payload["truth"]["downbeat_times"], dtype=np.float64)

    if raw["piece"].item() != payload["piece"]:
        raise AssertionError("OOF cache and figure payload piece identifiers differ.")
    if spectrogram.shape[0] != raw["beat_logits"].shape[0]:
        raise AssertionError("Spectrogram and activation frame counts differ.")
    if not np.allclose(raw["truth_beat"], truth_beat, atol=5e-7, rtol=0):
        raise AssertionError("Ground-truth beat arrays differ between source files.")
    if not np.allclose(raw["truth_downbeat"], truth_downbeat, atol=5e-7, rtol=0):
        raise AssertionError("Ground-truth downbeat arrays differ between source files.")
    beat_rounding_error = float(np.max(np.abs(beat_probability - payload_beat)))
    downbeat_rounding_error = float(
        np.max(np.abs(downbeat_probability - payload_downbeat))
    )
    if beat_rounding_error > 5.1e-6 or downbeat_rounding_error > 5.1e-6:
        raise AssertionError("Payload probabilities are not five-decimal logits transforms.")

    return {
        "root": root,
        "case": case,
        "paths": paths,
        "raw": raw,
        "payload": payload,
        "spectrogram": spectrogram,
        "beat_probability_raw": beat_probability,
        "downbeat_probability_raw": downbeat_probability,
        "rounding_error": {
            "beat_probability_max_abs": beat_rounding_error,
            "downbeat_probability_max_abs": downbeat_rounding_error,
        },
    }


def interval_rows(events: Iterable[float], start: float, end: float) -> np.ndarray:
    """Match the browser figure: keep events within a three-second halo."""
    selected = np.asarray(
        [time for time in events if start - 3 <= time <= end + 3], dtype=np.float64
    )
    if selected.size < 2:
        return np.empty((0, 2), dtype=np.float64)
    rows = np.column_stack(((selected[:-1] + selected[1:]) / 2, np.diff(selected)))
    return rows[(rows[:, 0] >= start) & (rows[:, 0] <= end)]


def interval_curve_mae(reference: np.ndarray, prediction: np.ndarray) -> float:
    """Midpoint-aligned IBI MAE used only as an explanatory window diagnostic."""
    if reference.size == 0 or prediction.shape[0] < 2:
        return float("nan")
    mask = (reference[:, 0] >= prediction[0, 0]) & (
        reference[:, 0] <= prediction[-1, 0]
    )
    if not np.any(mask):
        return float("nan")
    estimate = np.interp(reference[mask, 0], prediction[:, 0], prediction[:, 1])
    return float(np.mean(np.abs(reference[mask, 1] - estimate)))


def matched_flags(events: np.ndarray, truth: np.ndarray, tolerance: float = 0.07) -> np.ndarray:
    if truth.size == 0:
        return np.zeros(events.size, dtype=bool)
    return np.asarray(
        [np.any(np.abs(truth - event) <= tolerance) for event in events], dtype=bool
    )


def metric_rows(bundle: dict) -> list[list[str]]:
    payload = bundle["payload"]
    rows = []
    for method in METHODS:
        metric = payload["decoders"][method]["beat_metrics"]
        rows.append(
            [
                METHOD_LABELS[method],
                f"{100 * metric['fmeasure']:.1f}",
                f"{100 * metric['cmlt']:.1f}",
                f"{100 * metric['amlt']:.1f}",
                str(metric["event_count"]),
            ]
        )
    return rows


def window_data(bundle: dict, start: float, duration: float) -> dict:
    payload = bundle["payload"]
    end = min(float(payload["duration_seconds"]), float(start + duration))
    truth = np.asarray(payload["truth"]["beat_times"], dtype=np.float64)
    truth_downbeat = np.asarray(payload["truth"]["downbeat_times"], dtype=np.float64)
    method_events = {
        method: np.asarray(payload["decoders"][method]["beat_times"], dtype=np.float64)
        for method in METHODS
    }
    method_intervals = {
        method: interval_rows(events, start, end)
        for method, events in method_events.items()
    }
    reference_intervals = interval_rows(truth, start, end)
    candidates = np.asarray(payload["casm_analysis"]["candidate_times"], dtype=float)
    periods = np.asarray(payload["casm_analysis"]["period_seconds"], dtype=float)
    reliability = np.asarray(
        payload["casm_analysis"]["reliability_proxy"], dtype=float
    )
    mask = (candidates >= start) & (candidates <= end)
    local_prior = np.column_stack((candidates[mask], periods[mask], reliability[mask]))
    return {
        "start": float(start),
        "end": end,
        "truth": truth,
        "truth_downbeat": truth_downbeat,
        "method_events": method_events,
        "reference_intervals": reference_intervals,
        "method_intervals": method_intervals,
        "local_prior": local_prior,
        "window_mae": {
            method: interval_curve_mae(reference_intervals, rows)
            for method, rows in method_intervals.items()
        },
    }


def plot_figure(
    bundle: dict,
    start: float | None = None,
    duration: float | None = None,
    *,
    probability_source: str = "payload",
    show_local_tau: bool = True,
    output_path: str | Path | None = None,
    dpi: int = 180,
):
    """Reproduce the selected-case Figure 1 as a publication-ready static plot."""
    payload = bundle["payload"]
    start = float(payload["recommended_window_start"] if start is None else start)
    duration = float(payload["window_seconds"] if duration is None else duration)
    data = window_data(bundle, start, duration)
    start, end = data["start"], data["end"]

    if probability_source not in {"payload", "raw_logits"}:
        raise ValueError("probability_source must be 'payload' or 'raw_logits'.")
    probability = (
        np.asarray(payload["beat_probability"], dtype=float)
        if probability_source == "payload"
        else bundle["beat_probability_raw"]
    )
    fps = float(payload["fps"])
    first = max(0, int(np.floor(start * fps)))
    last = min(probability.size - 1, int(np.ceil(end * fps)))
    frame_times = np.arange(first, last + 1) / fps

    fig = plt.figure(figsize=(15, 18), constrained_layout=False, facecolor="white")
    grid = fig.add_gridspec(
        8,
        1,
        height_ratios=(1.55, 2.1, 1.85, 1, 1, 1, 1, 1),
        hspace=0.10,
        left=0.13,
        right=0.97,
        top=0.955,
        bottom=0.055,
    )
    ax_table = fig.add_subplot(grid[0])
    ax_activation = fig.add_subplot(grid[1])
    ax_events = fig.add_subplot(grid[2], sharex=ax_activation)
    ibi_axes = [fig.add_subplot(grid[index], sharex=ax_activation) for index in range(3, 8)]

    case_label = bundle["case"].replace("smc_", "SMC ")
    fig.suptitle(
        "Real case: four beat decoders diverge on the same activation",
        x=0.03,
        y=0.989,
        ha="left",
        va="top",
        fontsize=19,
        fontweight="bold",
    )
    subtitle = (
        f"{case_label} | {payload['protocol']['role']} | Beat This "
        f"{payload['protocol']['fold']} OOF | {payload['duration_seconds']:.2f} s"
    )
    fig.text(0.03, 0.968, subtitle, ha="left", fontsize=11, color=COLORS["muted"])

    ax_table.axis("off")
    table = ax_table.table(
        cellText=metric_rows(bundle),
        colLabels=("Decoder", "F1", "CMLt", "AMLt", "Events"),
        cellLoc="right",
        colLoc="right",
        colWidths=(0.42, 0.145, 0.145, 0.145, 0.145),
        bbox=(0.0, 0.08, 1.0, 0.78),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#e4e7eb")
        cell.set_linewidth(0.6)
        cell.set_facecolor("white")
        if row == 0:
            cell.get_text().set_weight("bold")
        if col == 0:
            cell.get_text().set_ha("left")
            if row > 0:
                cell.get_text().set_color(COLORS[METHODS[row - 1]])
    periods = np.sort(np.asarray(payload["casm_analysis"]["period_seconds"]))
    q10, q90 = np.quantile(periods, (0.1, 0.9))
    fixed_tau = float(payload["fixed_semimarkov"]["period_seconds"])
    ax_table.text(
        0,
        0.94,
        f"Global fixed tau = {fixed_tau:.2f} s; CASM local tau 10-90% = {q10:.2f}-{q90:.2f} s.",
        transform=ax_table.transAxes,
        fontsize=10.5,
        color=COLORS["muted"],
        va="top",
    )

    for axis in (ax_activation, ax_events, *ibi_axes):
        axis.set_xlim(start, end)
        axis.grid(axis="x", color=COLORS["grid"], linewidth=0.7, alpha=0.75)
        axis.spines[["top", "right"]].set_visible(False)
        axis.spines[["left", "bottom"]].set_color("#cfd4da")

    ax_activation.plot(
        frame_times,
        probability[first : last + 1],
        color=COLORS["activation"],
        linewidth=1.7,
    )
    ax_activation.set_ylim(0, 1.02)
    ax_activation.set_ylabel("beat activation\nprobability", fontsize=10)
    ax_activation.set_yticks((0, 0.5, 1.0))
    ax_activation.tick_params(axis="x", labelbottom=False)

    visible_truth = data["truth"][(data["truth"] >= start) & (data["truth"] <= end)]
    visible_downbeats = data["truth_downbeat"][
        (data["truth_downbeat"] >= start) & (data["truth_downbeat"] <= end)
    ]
    for event in visible_truth:
        is_downbeat = bool(np.any(np.abs(visible_downbeats - event) <= 0.07))
        for axis in (ax_activation, ax_events):
            axis.axvline(
                event,
                color=COLORS["groundtruth"],
                linestyle=(0, (3, 4)),
                linewidth=0.9 if not is_downbeat else 1.2,
                alpha=0.22 if not is_downbeat else 0.38,
                zorder=0,
            )

    lane_keys = ("groundtruth", *METHODS)
    lane_y = {key: 4 - index for index, key in enumerate(lane_keys)}
    for key in lane_keys:
        ax_events.axhline(lane_y[key], color="#e5e7ea", linewidth=0.8, zorder=0)

    for event in visible_truth:
        is_downbeat = bool(np.any(np.abs(visible_downbeats - event) <= 0.07))
        ax_events.scatter(
            event,
            lane_y["groundtruth"],
            marker="D",
            s=45 if is_downbeat else 34,
            facecolors=COLORS["groundtruth"] if is_downbeat else "white",
            edgecolors=COLORS["groundtruth"],
            linewidths=1.2,
            zorder=4,
        )
    for method in METHODS:
        events = data["method_events"][method]
        events = events[(events >= start) & (events <= end)]
        matched = matched_flags(events, visible_truth)
        for event, is_matched in zip(events, matched):
            if is_matched:
                ax_events.vlines(
                    event,
                    lane_y[method] - 0.28,
                    lane_y[method] + 0.28,
                    color=COLORS[method],
                    linewidth=3,
                    zorder=3,
                )
            else:
                ax_events.scatter(
                    event,
                    lane_y[method],
                    marker="x",
                    s=25,
                    color=COLORS[method],
                    linewidths=1.2,
                    zorder=3,
                )
    ax_events.set_ylim(-0.55, 4.55)
    ax_events.set_yticks([lane_y[key] for key in lane_keys])
    ax_events.set_yticklabels(
        ["GroundTruth", *[METHOD_LABELS[key] for key in METHODS]], fontsize=9.5
    )
    for tick, key in zip(ax_events.get_yticklabels(), lane_keys):
        tick.set_color(COLORS.get(key, COLORS["groundtruth"]))
    ax_events.tick_params(axis="x", labelbottom=False)

    interval_arrays = [data["reference_intervals"]]
    interval_arrays.extend(data["method_intervals"].values())
    values = [fixed_tau]
    for rows in interval_arrays:
        if rows.size:
            values.extend(rows[:, 1].tolist())
    if data["local_prior"].size:
        values.extend(data["local_prior"][:, 1].tolist())
    low, high = min(values), max(values)
    pad = max(0.12, (high - low) * 0.12)
    limits = (max(0, low - pad), high + pad)

    labels = ("GroundTruth IBI", "Direct", "Fixed Semi-Markov", "DBN", "CASM")
    row_sets = (
        data["reference_intervals"],
        data["method_intervals"]["direct"],
        data["method_intervals"]["fixed_semimarkov"],
        data["method_intervals"]["dbn"],
        data["method_intervals"]["casm"],
    )
    row_colors = (
        COLORS["groundtruth"],
        COLORS["direct"],
        COLORS["fixed_semimarkov"],
        COLORS["dbn"],
        COLORS["casm"],
    )
    row_markers = ("o", "D", "s", "^", "o")
    for index, (axis, label, rows, color, marker) in enumerate(
        zip(ibi_axes, labels, row_sets, row_colors, row_markers)
    ):
        axis.set_ylim(*limits)
        axis.set_ylabel(label, rotation=0, ha="right", va="center", fontsize=9.5)
        axis.tick_params(axis="x", labelbottom=index == len(ibi_axes) - 1)
        axis.tick_params(axis="y", labelsize=8)
        if rows.size:
            axis.plot(rows[:, 0], rows[:, 1], color=color, linewidth=1, alpha=0.72)
            axis.scatter(rows[:, 0], rows[:, 1], color=color, marker=marker, s=28, zorder=3)
        if index > 0:
            method = METHODS[index - 1]
            mae = data["window_mae"][method]
            if np.isfinite(mae):
                axis.text(
                    0.995,
                    0.82,
                    f"window IBI MAE {mae:.3f} s",
                    transform=axis.transAxes,
                    ha="right",
                    va="top",
                    color=color,
                    fontsize=9,
                )

    ibi_axes[2].axhline(
        fixed_tau,
        color=COLORS["fixed_semimarkov"],
        linestyle=(0, (5, 4)),
        linewidth=1.7,
    )
    ibi_axes[2].text(
        0.008,
        0.76,
        f"global tau = {fixed_tau:.2f} s",
        transform=ibi_axes[2].transAxes,
        color=COLORS["fixed_semimarkov"],
        fontsize=9,
    )
    if show_local_tau and data["local_prior"].size:
        ibi_axes[4].plot(
            data["local_prior"][:, 0],
            data["local_prior"][:, 1],
            color=COLORS["casm"],
            linestyle=(0, (4, 3)),
            linewidth=1.7,
        )
        ibi_axes[4].text(
            0.008,
            0.82,
            "local tau(t), dashed",
            transform=ibi_axes[4].transAxes,
            color=COLORS["casm"],
            fontsize=9,
        )
    ibi_axes[-1].set_xlabel("time (s)", ha="right", x=1.0)
    ibi_axes[0].set_title(
        "separated duration / decoded IBI panels (s, shared scale)",
        loc="left",
        fontsize=10,
        pad=7,
    )

    legend = [
        Line2D([0], [0], color=COLORS["activation"], lw=1.8, label="beat activation"),
        Line2D([0], [0], marker="D", markerfacecolor="white", markeredgecolor=COLORS["groundtruth"], color="none", label="GroundTruth beat"),
        Line2D([0], [0], marker="D", markerfacecolor=COLORS["groundtruth"], markeredgecolor=COLORS["groundtruth"], color="none", label="GroundTruth downbeat"),
        Line2D([0], [0], color=COLORS["groundtruth"], ls=(0, (3, 4)), lw=1, alpha=.5, label="alignment guide"),
        Line2D([0], [0], color=COLORS["casm"], marker="|", lw=0, markersize=12, label="matched prediction"),
        Line2D([0], [0], color=COLORS["casm"], marker="x", lw=0, label="false positive"),
    ]
    ax_activation.legend(
        handles=legend,
        loc="lower left",
        bbox_to_anchor=(0, 1.01),
        ncol=6,
        frameon=False,
        fontsize=8.5,
        handlelength=1.5,
        columnspacing=1.1,
    )

    params = payload["dbn_tuning"]["parameters"]
    fig.text(
        0.03,
        0.012,
        "Illustration-only selection. Fixed Semi-Markov is a global-period mechanism replay. "
        "DBN uses the shared illustration setting: "
        f"min/max BPM {params['min_bpm']:.0f}/{params['max_bpm']:.0f}, "
        f"transition lambda {params['transition_lambda']:.0f}, observation lambda "
        f"{params['observation_lambda']:.0f}, threshold {params['threshold']:.2f}. "
        "IBI MAE is an explanatory diagnostic, not a benchmark metric.",
        ha="left",
        va="bottom",
        fontsize=8.5,
        color=COLORS["muted"],
        wrap=True,
    )

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    return fig, data


def plot_spectrogram(bundle: dict, start: float, duration: float):
    """Show the exact Beat This input frames aligned to the selected window."""
    payload = bundle["payload"]
    end = min(float(payload["duration_seconds"]), start + duration)
    fps = float(payload["fps"])
    first = max(0, int(np.floor(start * fps)))
    last = min(bundle["spectrogram"].shape[0] - 1, int(np.ceil(end * fps)))
    figure, axis = plt.subplots(figsize=(15, 4.2), constrained_layout=True)
    axis.imshow(
        bundle["spectrogram"][first : last + 1].T,
        origin="lower",
        aspect="auto",
        extent=(first / fps, last / fps, 0, bundle["spectrogram"].shape[1]),
        cmap="magma",
        interpolation="nearest",
    )
    axis.set(xlabel="time (s)", ylabel="spectrogram bin", title="Beat This input spectrogram")
    return figure


def save_audio_segment(
    audio_path: str | Path,
    start: float,
    duration: float,
    output_path: str | Path | None = None,
):
    """Read a user-supplied waveform and return exactly the selected interval."""
    import soundfile as sf

    audio_path = Path(audio_path).expanduser().resolve()
    info = sf.info(audio_path)
    first = max(0, int(round(start * info.samplerate)))
    frames = max(0, int(round(duration * info.samplerate)))
    audio, sample_rate = sf.read(audio_path, start=first, frames=frames, always_2d=False)
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, audio, sample_rate)
    return audio, sample_rate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_case_tables(bundle: dict, output_dir: str | Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    case = bundle["case"]
    payload = bundle["payload"]
    written = []

    events_path = output_dir / f"{case}_events.csv"
    with events_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("case", "source", "event_type", "time_seconds"))
        for time in payload["truth"]["beat_times"]:
            writer.writerow((case, "GroundTruth", "beat", f"{time:.9f}"))
        for time in payload["truth"]["downbeat_times"]:
            writer.writerow((case, "GroundTruth", "downbeat", f"{time:.9f}"))
        for method in (*METHODS, "dbn_original"):
            for event_type in ("beat", "downbeat"):
                for time in payload["decoders"][method][f"{event_type}_times"]:
                    writer.writerow((case, METHOD_LABELS.get(method, "DBN original"), event_type, f"{time:.9f}"))
    written.append(events_path)

    ibi_path = output_dir / f"{case}_ibi.csv"
    with ibi_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("case", "source", "midpoint_seconds", "ibi_seconds"))
        event_sets = {"GroundTruth": payload["truth"]["beat_times"]}
        event_sets.update(
            {METHOD_LABELS[method]: payload["decoders"][method]["beat_times"] for method in METHODS}
        )
        event_sets["DBN original"] = payload["decoders"]["dbn_original"]["beat_times"]
        for source, events in event_sets.items():
            events = np.asarray(events, dtype=float)
            if events.size < 2:
                continue
            for left, right in zip(events[:-1], events[1:]):
                writer.writerow((case, source, f"{(left + right) / 2:.9f}", f"{right - left:.9f}"))
    written.append(ibi_path)

    prior_path = output_dir / f"{case}_priors.csv"
    with prior_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("case", "time_seconds", "casm_local_tau_seconds", "tempo_bpm", "reliability_proxy", "fixed_global_tau_seconds"))
        analysis = payload["casm_analysis"]
        for row in zip(
            analysis["candidate_times"],
            analysis["period_seconds"],
            analysis["tempo_bpm"],
            analysis["reliability_proxy"],
        ):
            writer.writerow((case, *(f"{value:.9f}" for value in row), f"{payload['fixed_semimarkov']['period_seconds']:.9f}"))
    written.append(prior_path)
    return written


def build_manifest(root: str | Path) -> dict:
    root = Path(root).resolve()
    files = []
    for path in sorted((root / "data").rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append(
                {
                    "path": str(path.relative_to(root)),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    cases = {}
    for case in CASES:
        bundle = load_case(root, case)
        cases[case] = {
            "piece": bundle["payload"]["piece"],
            "fold": bundle["payload"]["protocol"]["fold"],
            "fps": bundle["payload"]["fps"],
            "duration_seconds": bundle["payload"]["duration_seconds"],
            "recommended_window_start": bundle["payload"]["recommended_window_start"],
            "recommended_window_seconds": bundle["payload"]["window_seconds"],
            "logit_frames": int(bundle["raw"]["beat_logits"].size),
            "spectrogram_shape": list(bundle["spectrogram"].shape),
            "spectrogram_dtype": str(bundle["spectrogram"].dtype),
            "probability_rounding_error": bundle["rounding_error"],
        }
    manifest = {
        "bundle": "StructBeat Figure 1 exact-data reproduction",
        "cases": cases,
        "dbn_configuration": {
            "min_bpm": 35.0,
            "max_bpm": 160.0,
            "transition_lambda": 50.0,
            "observation_lambda": 8.0,
            "threshold": 0.03,
            "beats_per_bar": [3, 4],
            "warning": "Illustration-tuned on the displayed cases; not an aggregate benchmark setting.",
        },
        "audio": {
            "bundled_waveform": False,
            "reason": "The Beat This distribution used here provides precomputed spectrograms and annotations, not redistributable SMC waveform audio.",
            "override": "Set AUDIO_OVERRIDE in the notebook to an authorized local WAV/FLAC/OGG file.",
        },
        "files": files,
    }
    path = root / "data" / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
