#!/usr/bin/env python3
"""Create paper-grade CASM mechanism figures from frozen-cache experiments."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D


BLUE = "#2563A6"
BLUE_LIGHT = "#9BC4E2"
ORANGE = "#D97706"
GOLD = "#C7A43A"
OLIVE = "#708238"
CHARCOAL = "#252A30"
GREY = "#7B828A"
LIGHT_GREY = "#D9DEE3"
PALE = "#F4F6F8"

PANEL_ORDER = [
    "bt_smc_oof",
    "mscnn_smc_oof",
    "tcn_smc_final0",
    "bt_gtzan_seed0",
    "mscnn_gtzan",
]

PANEL_SHORT = {
    "bt_smc_oof": "Beat This\nSMC OOF",
    "mscnn_smc_oof": "MSCNN-lite\nSMC OOF",
    "tcn_smc_final0": "TCN\nSMC final0",
    "bt_gtzan_seed0": "Beat This\nGTZAN seed0",
    "mscnn_gtzan": "MSCNN-lite\nGTZAN",
}

PANEL_LINE = {
    "bt_smc_oof": (BLUE, "-"),
    "mscnn_smc_oof": (BLUE, "--"),
    "tcn_smc_final0": (ORANGE, "-."),
    "bt_gtzan_seed0": (GOLD, "-"),
    "mscnn_gtzan": (OLIVE, "--"),
}

PANEL_TINY = {
    "bt_smc_oof": "BT\nSMC",
    "mscnn_smc_oof": "MSCNN\nSMC",
    "tcn_smc_final0": "TCN\nSMC",
    "bt_gtzan_seed0": "BT\nGTZAN",
    "mscnn_gtzan": "MSCNN\nGTZAN",
}

METHOD_LABEL = {
    "direct": "Direct",
    "casm_full": "CASM",
    "local_target_fixed": "Local target\nfixed precision",
    "strength_only": "Strength only",
    "width_only": "Width only",
    "one_sided": "One endpoint",
    "no_safeguard": "No safeguards",
    "dbn_default": "DBN",
    "dbn_matched_30_300": "DBN 30–300",
    "plpdp": "PLPDP",
}


def setup_style() -> None:
    sns.set_theme(style="ticks", context="paper")
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.0,
            "axes.titlesize": 9.0,
            "axes.labelsize": 8.0,
            "xtick.labelsize": 7.2,
            "ytick.labelsize": 7.2,
            "legend.fontsize": 7.0,
            "figure.titlesize": 10.0,
            "axes.edgecolor": CHARCOAL,
            "axes.linewidth": 0.65,
            "grid.color": LIGHT_GREY,
            "grid.linewidth": 0.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.hashsalt": "casm-mechanism-20260904",
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
        }
    )


def save_all(fig: plt.Figure, directory: Path, stem: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / f"{stem}.png", dpi=320)
    fig.savefig(directory / f"{stem}.pdf")
    fig.savefig(directory / f"{stem}.svg")
    plt.close(fig)


def ecdf(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(np.asarray(values, dtype=float))
    return x, np.arange(1, len(x) + 1) / len(x)


def figure_input_conditioning(data: Path, figures: Path, frozen: dict[str, object]) -> None:
    edges = pd.read_csv(data / "mechanism_edges.csv.gz")
    pieces = pd.read_csv(data / "mechanism_piece_summary.csv")
    lam = float(frozen["duration_weight"])
    sigma0 = float(frozen["duration_sigma"])
    sigmau = float(frozen["uncertain_sigma"])

    fig = plt.figure(figsize=(7.15, 4.15))
    grid = fig.add_gridspec(2, 2, height_ratios=[1.15, 0.82])
    axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, :])]
    fig.subplots_adjust(wspace=0.34, hspace=0.55, top=0.84, bottom=0.14, left=0.11, right=0.97)

    ax = axes[0]
    c = np.linspace(0.0, 1.0, 1001)
    sigma = sigma0 + (1.0 - c) * sigmau
    coefficient = lam * c / (2.0 * sigma * sigma)
    empirical_limit = float(edges.edge_margin.quantile(0.995))
    ax.axvspan(0, empirical_limit, color=BLUE_LIGHT, alpha=0.24, lw=0)
    ax.plot(c, coefficient, color=BLUE, lw=1.8)
    ax.axvline(empirical_limit, color=GREY, lw=0.8, ls="--")
    ax.text(empirical_limit, 72, "99.5% of\nobserved edges", color=GREY, ha="left", va="center", fontsize=6.7)
    ax.scatter([0.1, 0.5, 1.0], [lam * x / (2 * (sigma0 + (1 - x) * sigmau) ** 2) for x in (0.1, 0.5, 1.0)], s=12, color=ORANGE, zorder=3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 145)
    ax.set_xlabel("Period margin $c$")
    ax.set_ylabel("Effective coefficient $w(c)$")
    ax.set_title("(a) Fixed response law", loc="left", fontweight="bold")
    ax.grid(axis="y")

    ax = axes[1]
    for panel in PANEL_ORDER:
        group = edges[edges.panel == panel]
        x, y = ecdf(group.edge_margin.to_numpy())
        color, style = PANEL_LINE[panel]
        short_label = {
            "bt_smc_oof": "BT / SMC",
            "mscnn_smc_oof": "MSCNN / SMC",
            "tcn_smc_final0": "TCN / SMC",
            "bt_gtzan_seed0": "BT / GTZAN",
            "mscnn_gtzan": "MSCNN / GTZAN",
        }[panel]
        ax.plot(x, y, color=color, ls=style, lw=1.2, label=short_label)
    ax.set_xlim(0, max(0.62, edges.edge_margin.quantile(0.999)))
    ax.set_ylim(0, 1)
    ax.set_xlabel("Observed edge margin $c_{ij}$")
    ax.set_ylabel("Cumulative fraction")
    ax.set_title("(b) Real edge margins", loc="left", fontweight="bold")
    ax.grid()
    ax.legend(frameon=False, loc="lower right", handlelength=2.1, labelspacing=0.2, borderaxespad=0.2)

    ax = axes[2]
    box_data = [pieces.loc[pieces.panel == panel, "edge_coefficient_median"].dropna().to_numpy() for panel in PANEL_ORDER]
    positions = np.arange(len(PANEL_ORDER))
    box = ax.boxplot(
        box_data,
        vert=False,
        positions=positions,
        widths=0.6,
        showfliers=False,
        patch_artist=True,
        medianprops={"color": CHARCOAL, "lw": 1.0},
        whiskerprops={"color": GREY, "lw": 0.7},
        capprops={"color": GREY, "lw": 0.7},
        boxprops={"facecolor": BLUE_LIGHT, "edgecolor": BLUE, "lw": 0.8},
    )
    for patch, panel in zip(box["boxes"], PANEL_ORDER):
        color, _ = PANEL_LINE[panel]
        patch.set_facecolor(mpl.colors.to_rgba(color, 0.28))
        patch.set_edgecolor(color)
    for y, panel in zip(positions, PANEL_ORDER):
        rate = 100 * pieces.loc[pieces.panel == panel, "beat_fallback"].mean()
        ax.text(32, y, f"fallback {rate:.1f}%", va="center", ha="right", fontsize=6.8, color=GREY)
    ax.set_xscale("log")
    ax.set_xlim(0.08, 38)
    ax.set_yticks(
        positions,
        [
            {
                "bt_smc_oof": "BT / SMC",
                "mscnn_smc_oof": "MSCNN / SMC",
                "tcn_smc_final0": "TCN / SMC",
                "bt_gtzan_seed0": "BT / GTZAN",
                "mscnn_gtzan": "MSCNN / GTZAN",
            }[panel]
            for panel in PANEL_ORDER
        ],
    )
    ax.invert_yaxis()
    ax.set_xlabel("Per-piece median $w(c_{ij})$ (log scale)")
    ax.set_title("(c) Input-specific operating points", loc="left", fontweight="bold")
    ax.grid(axis="x", which="both")

    fig.suptitle("Input-conditioned duration stiffness under one Frozen-4F configuration", x=0.02, y=0.975, ha="left", fontweight="bold")
    fig.text(
        0.02,
        0.02,
        "All values are derived from real decoded edges; the shaded region marks the empirical 99.5th percentile of $c_{ij}$. "
        "SMC panels contain 217 tracks; GTZAN panels contain 993 tracks.",
        fontsize=6.4,
        color=GREY,
    )
    save_all(fig, figures, "fig01_input_conditioned_stiffness")


def event_matches(reference: np.ndarray, estimate: np.ndarray, tolerance: float = 0.07) -> int:
    reference = np.sort(np.asarray(reference, dtype=float))
    estimate = np.sort(np.asarray(estimate, dtype=float))
    i = j = matches = 0
    while i < len(reference) and j < len(estimate):
        delta = reference[i] - estimate[j]
        if abs(delta) <= tolerance:
            matches += 1
            i += 1
            j += 1
        elif delta < 0:
            i += 1
        else:
            j += 1
    return matches


def choose_window(trace: dict[str, np.ndarray], role: str, width: float = 12.0) -> tuple[float, float]:
    duration = len(trace["beat_prob"]) / float(trace["fps"])
    starts = np.arange(5.0, max(5.01, duration - width), 0.25)
    if not len(starts):
        return 0.0, duration
    truth = trace["truth_beat"]
    direct = trace["direct_beat"]
    casm = trace["casm_beat"]
    candidate_times = trace["candidates"] / float(trace["fps"])
    confidence = trace["confidence"]
    scores = []
    for start in starts:
        end = start + width
        tr = truth[(truth >= start) & (truth <= end)]
        dr = direct[(direct >= start) & (direct <= end)]
        ca = casm[(casm >= start) & (casm <= end)]
        mask = (candidate_times >= start) & (candidate_times <= end)
        local_c = float(np.mean(confidence[mask])) if np.any(mask) else 1.0
        if role == "ambiguous":
            score = -local_c + 0.01 * min(len(tr), 12)
        else:
            score = (
                event_matches(tr, ca) - event_matches(tr, dr)
                + 0.15 * (abs(len(dr) - len(tr)) - abs(len(ca) - len(tr)))
                + 0.01 * min(len(tr), 12)
            )
        scores.append(score)
    start = float(starts[int(np.argmax(scores))])
    return start, min(start + width, duration)


def load_trace(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def trace_metrics(representatives: list[dict[str, object]], panel: str, role: str) -> dict[str, object]:
    return next(row for row in representatives if row["panel"] == panel and row["role"] == role)


def plot_event_raster(ax: plt.Axes, values: np.ndarray, y: float, color: str, marker: str, label: str, start: float, end: float) -> None:
    values = np.asarray(values, dtype=float)
    values = values[(values >= start) & (values <= end)]
    if marker == "|":
        ax.vlines(values, y - 0.025, y + 0.025, color=color, lw=1.0, label=label)
    else:
        ax.scatter(values, np.full(len(values), y), s=10, marker=marker, color=color, linewidths=0.7, label=label, zorder=5)


def figure_real_traces(data: Path, figures: Path, frozen: dict[str, object]) -> None:
    representatives = json.loads((data / "representatives.json").read_text())
    selections = [("improvement", "Mechanism-visible improvement"), ("ambiguous", "Ambiguous evidence; CASM defers")]
    fig, axes = plt.subplots(3, 2, figsize=(7.15, 5.0), gridspec_kw={"height_ratios": [1.4, 1.0, 0.9]})
    fig.subplots_adjust(wspace=0.25, hspace=0.2, top=0.78, bottom=0.13)

    for column, (role, heading) in enumerate(selections):
        trace = load_trace(data / "representative_traces" / f"bt_smc_oof__{role}.npz")
        meta = trace_metrics(representatives, "bt_smc_oof", role)
        fps = float(trace["fps"])
        start, end = choose_window(trace, role)
        frame_start = max(0, int(math.floor(start * fps)))
        frame_end = min(len(trace["beat_prob"]), int(math.ceil(end * fps)) + 1)
        times = np.arange(frame_start, frame_end) / fps

        ax = axes[0, column]
        ax.fill_between(times, trace["beat_prob"][frame_start:frame_end], color=LIGHT_GREY, alpha=0.65, lw=0)
        ax.plot(times, trace["beat_prob"][frame_start:frame_end], color=GREY, lw=0.75)
        plot_event_raster(ax, trace["truth_beat"], -0.05, CHARCOAL, "|", "Reference", start, end)
        plot_event_raster(ax, trace["direct_beat"], -0.12, ORANGE, "x", "Direct", start, end)
        plot_event_raster(ax, trace["casm_beat"], -0.19, BLUE, "|", "CASM", start, end)
        plot_event_raster(ax, trace["dbn_matched_beat"], -0.26, GREY, ".", "DBN 30–300", start, end)
        plot_event_raster(ax, trace["plpdp_beat"], -0.33, OLIVE, "+", "PLPDP", start, end)
        ax.set_xlim(start, end)
        ax.set_ylim(-0.38, 1.03)
        ax.set_yticks([0, 0.5, 1.0])
        ax.set_ylabel("Beat activation" if column == 0 else "")
        ax.set_title(
            f"{heading}\n{str(trace['piece'].item()).replace('/track.npy', '')}",
            fontsize=8.3,
            fontweight="bold",
        )
        ax.grid(axis="y")
        if column == 0:
            handles, labels = ax.get_legend_handles_labels()
            fig.legend(
                handles,
                labels,
                frameon=False,
                ncol=5,
                loc="upper center",
                bbox_to_anchor=(0.5, 0.885),
                handlelength=1.0,
                columnspacing=1.2,
            )

        ax = axes[1, column]
        candidate_times = trace["candidates"] / fps
        mask = (candidate_times >= start) & (candidate_times <= end)
        target_bpm = 60.0 * fps / trace["periods"]
        sc = ax.scatter(
            candidate_times[mask],
            target_bpm[mask],
            c=trace["confidence"][mask],
            cmap=mpl.colors.LinearSegmentedColormap.from_list("casm_c", [LIGHT_GREY, BLUE]),
            vmin=0,
            vmax=max(0.5, float(np.max(trace["confidence"]))),
            s=9,
            linewidths=0,
            label="CASM local target",
        )
        truth = trace["truth_beat"]
        truth_bpm = 60.0 / np.diff(truth)
        truth_times = 0.5 * (truth[:-1] + truth[1:])
        truth_mask = (truth_times >= start) & (truth_times <= end)
        ax.plot(truth_times[truth_mask], truth_bpm[truth_mask], color=CHARCOAL, lw=1.0, marker=".", ms=2.5, label="Reference IBI")
        ax.set_yscale("log")
        ax.set_ylim(30, 300)
        ax.yaxis.set_major_locator(mpl.ticker.FixedLocator([30, 60, 120, 240]))
        ax.yaxis.set_major_formatter(mpl.ticker.FixedFormatter(["30", "60", "120", "240"]))
        ax.yaxis.set_minor_formatter(mpl.ticker.NullFormatter())
        ax.set_xlim(start, end)
        ax.set_ylabel("Local tempo (BPM)" if column == 0 else "")
        ax.grid(which="both", axis="y")
        if column == 0:
            ax.legend(frameon=False, loc="upper left", ncol=2)

        ax = axes[2, column]
        confidence = trace["confidence"][mask]
        ctime = candidate_times[mask]
        sigma0 = float(frozen["duration_sigma"])
        sigmau = float(frozen["uncertain_sigma"])
        lam = float(frozen["duration_weight"])
        coefficient = lam * confidence / (2 * (sigma0 + (1 - confidence) * sigmau) ** 2)
        ax.fill_between(ctime, confidence, color=BLUE_LIGHT, alpha=0.65, step="mid")
        ax.plot(ctime, confidence, color=BLUE, lw=0.8)
        ax.set_ylim(0, max(0.5, float(np.max(trace["confidence"])) * 1.08))
        ax.set_xlim(start, end)
        ax.set_ylabel("Margin $c_i$" if column == 0 else "")
        ax.set_xlabel("Time (s)")
        ax.grid(axis="y")
        twin = ax.twinx()
        twin.plot(ctime, coefficient, color=ORANGE, lw=0.8, alpha=0.9)
        twin.set_ylim(0, max(4.0, float(np.max(coefficient)) * 1.12))
        twin.set_ylabel("$w(c_i)$" if column == 1 else "", color=ORANGE)
        twin.tick_params(axis="y", colors=ORANGE)
        ax.text(
            0.01,
            0.92,
            f"ΔF1 {100*float(meta['delta_fmeasure']):+.1f} pp · ΔCMLt {100*float(meta['delta_cmlt']):+.1f} pp",
            transform=ax.transAxes,
            va="top",
            fontsize=6.7,
            color=CHARCOAL,
        )

    for ax in axes[:2].flat:
        ax.tick_params(labelbottom=False)
    fig.suptitle("CASM behavior on real Beat This OOF activations from SMC", x=0.02, y=0.985, ha="left", fontweight="bold")
    fig.text(
        0.02,
        0.02,
        "Windows were selected post hoc for mechanism visualization, not for performance estimation. "
        "Every CASM beat remains on a retained activation maximum.",
        fontsize=6.4,
        color=GREY,
    )
    save_all(fig, figures, "fig02_real_track_mechanism")


def aggregate_lookup(aggregate: pd.DataFrame, panel: str, method: str, metric: str) -> float:
    row = aggregate[(aggregate.panel == panel) & (aggregate.method == method)]
    if len(row) != 1:
        raise RuntimeError((panel, method, metric, len(row)))
    return float(row.iloc[0][metric])


def figure_ablation(data: Path, figures: Path) -> None:
    aggregate = pd.read_csv(data / "aggregate_metrics.csv")
    methods = ["casm_full", "local_target_fixed", "strength_only", "width_only", "one_sided", "no_safeguard"]
    metrics = [("beat_fmeasure", "Beat F1"), ("beat_cmlt", "CMLt"), ("beat_amlt", "AMLt")]
    matrices = []
    for metric, _ in metrics:
        matrix = np.asarray(
            [
                [
                    100 * (
                        aggregate_lookup(aggregate, panel, method, metric)
                        - aggregate_lookup(aggregate, panel, "direct", metric)
                    )
                    for panel in PANEL_ORDER
                ]
                for method in methods
            ]
        )
        matrices.append(matrix)
    bound = max(5.0, math.ceil(max(np.max(np.abs(matrix)) for matrix in matrices)))
    cmap = mpl.colors.LinearSegmentedColormap.from_list("signed", [ORANGE, "#FFF9F0", "white", "#EDF5FC", BLUE])
    norm = mpl.colors.TwoSlopeNorm(vmin=-bound, vcenter=0, vmax=bound)

    fig, axes = plt.subplots(1, 3, figsize=(7.15, 3.55), sharey=True)
    fig.subplots_adjust(wspace=0.08, top=0.78, bottom=0.34, left=0.2, right=0.98)
    for index, (ax, matrix, (_, title)) in enumerate(zip(axes, matrices, metrics)):
        image = ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")
        for row in range(matrix.shape[0]):
            for col in range(matrix.shape[1]):
                value = matrix[row, col]
                ax.text(col, row, f"{value:+.1f}", ha="center", va="center", fontsize=6.6, color=CHARCOAL)
        ax.set_xticks(np.arange(len(PANEL_ORDER)), [PANEL_TINY[p] for p in PANEL_ORDER])
        ax.set_title(f"({chr(97+index)}) Δ {title}", loc="left", fontweight="bold")
        ax.tick_params(length=0)
    axes[0].set_yticks(np.arange(len(methods)), [METHOD_LABEL[m] for m in methods])
    for ax in axes[1:]:
        ax.tick_params(labelleft=False)
    cbar_axis = fig.add_axes([0.28, 0.105, 0.52, 0.035])
    cbar = fig.colorbar(image, cax=cbar_axis, orientation="horizontal")
    cbar.set_label("Paired macro change from Direct (percentage points)")
    cbar.ax.xaxis.set_label_position("top")
    fig.suptitle("CASM mechanism ablations on fixed activation panels", x=0.02, ha="left", fontweight="bold")
    fig.text(
        0.015,
        0.02,
        "Positive values favor the listed decoder. SMC panels contain 217 tracks; GTZAN panels contain 993 tracks. "
        "TCN final0 is a mechanism panel, not the paper's OOF estimate.",
        fontsize=6.4,
        color=GREY,
    )
    save_all(fig, figures, "fig03_ablation_matrix")


def figure_operating_points(data: Path, figures: Path) -> None:
    aggregate = pd.read_csv(data / "aggregate_metrics.csv")
    methods = ["direct", "casm_full", "dbn_default", "dbn_matched_30_300", "plpdp"]
    colors = {"direct": GREY, "casm_full": BLUE, "dbn_default": ORANGE, "dbn_matched_30_300": GOLD, "plpdp": OLIVE}
    markers = {"direct": "o", "casm_full": "s", "dbn_default": "^", "dbn_matched_30_300": "v", "plpdp": "D"}
    fig, axes = plt.subplots(2, 3, figsize=(7.15, 4.35))
    fig.subplots_adjust(wspace=0.34, hspace=0.5, top=0.82, bottom=0.14)
    for ax, panel in zip(axes.flat, PANEL_ORDER):
        group = aggregate[(aggregate.panel == panel) & (aggregate.method.isin(methods))].set_index("method")
        x = 100 * group.loc[methods, "beat_fmeasure"].to_numpy()
        y = 100 * group.loc[methods, "beat_amlt"].to_numpy()
        ax.annotate(
            "",
            xy=(x[1], y[1]),
            xytext=(x[0], y[0]),
            arrowprops={"arrowstyle": "->", "color": BLUE, "lw": 0.9, "alpha": 0.75},
        )
        for method, xx, yy in zip(methods, x, y):
            ax.scatter(xx, yy, s=30, marker=markers[method], color=colors[method], edgecolor="white", linewidth=0.5, zorder=3)
            label = METHOD_LABEL[method].replace("\n", " ")
            offset = (3, 3) if method != "dbn_matched_30_300" else (3, -9)
            ax.annotate(label, (xx, yy), xytext=offset, textcoords="offset points", fontsize=6.1, color=colors[method])
        xpad = max(0.6, 0.12 * (x.max() - x.min()))
        ypad = max(0.8, 0.12 * (y.max() - y.min()))
        ax.set_xlim(x.min() - xpad, x.max() + 2.2 * xpad)
        ax.set_ylim(y.min() - ypad, y.max() + ypad)
        ax.set_title(PANEL_SHORT[panel].replace("\n", " / "), fontweight="bold")
        ax.set_xlabel("Beat F1 (%)")
        ax.set_ylabel("Beat AMLt (%)")
        ax.grid()
    axes.flat[-1].axis("off")
    fig.suptitle("Beat F1–continuity operating points on identical activations", x=0.02, ha="left", fontweight="bold")
    fig.text(
        0.02,
        0.02,
        "Axes use focused, panel-specific ranges; points are macro means. The blue arrow shows Direct → CASM. "
        "DBN 30–300 changes only the tempo support of the conventional DBN baseline.",
        fontsize=6.4,
        color=GREY,
    )
    save_all(fig, figures, "fig04_decoder_operating_points")


def figure_calibration_scale(data: Path, figures: Path) -> None:
    table = pd.read_csv(data / "calibration_fixed_panel.csv")
    selected = table[table.tuning_size.isin([1, 2, 4, 7])].copy()
    selected["scale"] = selected.tuning_size.astype(int).astype(str) + "F"
    order = ["1F", "2F", "4F", "7F"]
    metric_specs = [
        ("beat_fmeasure", "Beat F1"),
        ("beat_cmlt", "CMLt"),
        ("beat_amlt", "AMLt"),
    ]
    panels = [("smc", "SMC fold0"), ("gtzan", "GTZAN final0")]
    direct = table[table.family == "direct"].iloc[0]
    fig, axes = plt.subplots(2, 3, figsize=(7.15, 4.05), sharex=True)
    fig.subplots_adjust(wspace=0.24, hspace=0.34, top=0.82, bottom=0.16)
    rng = np.random.default_rng(20260904)
    for row_index, (prefix, panel_label) in enumerate(panels):
        for column_index, (metric, metric_label) in enumerate(metric_specs):
            ax = axes[row_index, column_index]
            column = f"{prefix}_{metric}"
            direct_value = 100 * float(direct[column])
            ax.axhline(direct_value, color=GREY, lw=0.9, ls="--", label="Direct")
            values_by_scale = []
            for position, scale in enumerate(order):
                values = 100 * selected.loc[selected.scale == scale, column].dropna().to_numpy()
                values_by_scale.append(values)
                jitter = rng.uniform(-0.12, 0.12, size=len(values))
                ax.scatter(np.full(len(values), position) + jitter, values, s=9, facecolor="white", edgecolor=BLUE, linewidth=0.55, alpha=0.9)
            ax.boxplot(
                values_by_scale,
                positions=np.arange(len(order)),
                widths=0.5,
                showfliers=False,
                patch_artist=True,
                medianprops={"color": CHARCOAL, "lw": 0.9},
                whiskerprops={"color": GREY, "lw": 0.6},
                capprops={"color": GREY, "lw": 0.6},
                boxprops={"facecolor": BLUE_LIGHT, "edgecolor": BLUE, "alpha": 0.35, "lw": 0.7},
            )
            ax.set_xticks(np.arange(len(order)), order)
            if row_index == 0:
                ax.set_title(f"({chr(97+column_index)}) {metric_label}", loc="left", fontweight="bold")
            if column_index == 0:
                ax.set_ylabel(f"{panel_label}\nScore (%)")
            ax.grid(axis="y")
            if row_index == 0 and column_index == 2:
                ax.legend(frameon=False, loc="best")
    fig.suptitle("Calibration-fold scale and sensitivity to fold composition", x=0.02, ha="left", fontweight="bold")
    fig.text(
        0.02,
        0.02,
        "Each point is one selected configuration: 7 one-fold, 21 two-fold, 35 four-fold, and one seven-fold result. "
        "All configurations are evaluated on the same fixed panels; distributions are descriptive.",
        fontsize=6.4,
        color=GREY,
    )
    save_all(fig, figures, "fig05_calibration_scale")


def figure_gain_risk(data: Path, figures: Path) -> None:
    table = pd.read_csv(data / "all_piece_metrics.csv.gz")
    method_specs = [
        ("local_target_fixed", "Fixed precision", "o", "white"),
        ("no_safeguard", "No safeguards", "X", None),
        ("casm_full", "CASM", "s", None),
    ]
    metric_specs = [
        ("beat_fmeasure", "Beat F1"),
        ("beat_amlt", "AMLt"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 3.15))
    fig.subplots_adjust(wspace=0.30, top=0.69, bottom=0.23)
    for column_index, (metric, label) in enumerate(metric_specs):
        ax = axes[column_index]
        for panel in PANEL_ORDER:
            panel_table = table[table.panel == panel].pivot(index="piece", columns="method", values=metric)
            color = PANEL_LINE[panel][0]
            coordinates: dict[str, tuple[float, float]] = {}
            for method, _, marker, face in method_specs:
                delta = 100 * (panel_table[method] - panel_table["direct"])
                x = 100 * float((delta < -5.0).mean())
                y = float(delta.mean())
                coordinates[method] = (x, y)
                ax.scatter(
                    x,
                    y,
                    s=34,
                    marker=marker,
                    facecolor=color if face is None else face,
                    edgecolor=color,
                    linewidth=1.0,
                    zorder=3,
                )
            start = coordinates["no_safeguard"]
            end = coordinates["casm_full"]
            ax.annotate(
                "",
                xy=end,
                xytext=start,
                arrowprops={"arrowstyle": "->", "color": color, "lw": 1.0, "alpha": 0.78},
                zorder=2,
            )
        ax.axvline(0.0, color=GREY, lw=0.6)
        ax.axhline(0.0, color=GREY, lw=0.6)
        ax.set_title(f"({chr(97 + column_index)}) {label}", loc="left", fontweight="bold")
        ax.set_xlabel("Tracks degraded by >5 pp (%)  ← lower risk")
        ax.set_ylabel("Mean change from Direct (pp)")
        ax.grid(True)
    method_handles = [
        Line2D([0], [0], marker=marker, linestyle="none", markerfacecolor=CHARCOAL if face is None else face,
               markeredgecolor=CHARCOAL, markersize=5.5, label=label)
        for _, label, marker, face in method_specs
    ]
    panel_handles = [
        Line2D([0], [0], color=PANEL_LINE[panel][0], lw=2, label=PANEL_SHORT[panel].replace("\n", " / "))
        for panel in PANEL_ORDER
    ]
    fig.legend(
        handles=method_handles + panel_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.885),
        frameon=False,
        ncol=4,
        fontsize=6.2,
    )
    fig.suptitle("Safeguards trade peak correction for lower per-track regression risk", x=0.02, ha="left", fontweight="bold")
    fig.text(
        0.02,
        0.025,
        "Each point uses the same paired activation panel; arrows show No safeguards → CASM. "
        "Risk is the fraction of tracks whose score falls by more than five percentage points relative to Direct. "
        "TCN final0 is exploratory rather than OOF.",
        fontsize=6.2,
        color=GREY,
    )
    save_all(fig, figures, "fig06_gain_risk")


def bootstrap_mean_difference(diff: np.ndarray, rng: np.random.Generator, repetitions: int = 5000) -> tuple[float, float, float, float]:
    diff = np.asarray(diff, dtype=float)
    diff = diff[np.isfinite(diff)]
    means = np.empty(repetitions, dtype=float)
    block = 250
    for start in range(0, repetitions, block):
        count = min(block, repetitions - start)
        indices = rng.integers(0, len(diff), size=(count, len(diff)))
        means[start : start + count] = diff[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(diff.mean()), float(low), float(high), float(np.mean(means > 0))


def write_bootstrap(data: Path) -> None:
    table = pd.read_csv(data / "all_piece_metrics.csv.gz")
    comparisons = [
        ("casm_full", "direct"),
        ("casm_full", "local_target_fixed"),
        ("casm_full", "strength_only"),
        ("casm_full", "width_only"),
        ("casm_full", "one_sided"),
        ("casm_full", "no_safeguard"),
        ("casm_full", "plpdp"),
        ("dbn_matched_30_300", "dbn_default"),
    ]
    metrics = ["beat_fmeasure", "beat_cmlt", "beat_amlt"]
    rng = np.random.default_rng(20260904)
    rows = []
    for panel in PANEL_ORDER:
        panel_table = table[table.panel == panel]
        for left, right in comparisons:
            left_table = panel_table[panel_table.method == left].set_index("piece")
            right_table = panel_table[panel_table.method == right].set_index("piece")
            common = left_table.index.intersection(right_table.index)
            for metric in metrics:
                diff = left_table.loc[common, metric].to_numpy() - right_table.loc[common, metric].to_numpy()
                mean, low, high, probability = bootstrap_mean_difference(diff, rng)
                rows.append(
                    {
                        "panel": panel,
                        "left": left,
                        "right": right,
                        "metric": metric,
                        "piece_count": int(np.isfinite(diff).sum()),
                        "mean_difference": mean,
                        "ci95_low": low,
                        "ci95_high": high,
                        "bootstrap_probability_gt_zero": probability,
                        "repetitions": 5000,
                        "seed": 20260904,
                    }
                )
    pd.DataFrame(rows).to_csv(data / "paired_bootstrap.csv", index=False)


def write_numeric_summary(data: Path, frozen: dict[str, object]) -> None:
    aggregate = pd.read_csv(data / "aggregate_metrics.csv")
    pieces = pd.read_csv(data / "mechanism_piece_summary.csv")
    edges = pd.read_csv(data / "mechanism_edges.csv.gz")
    payload: dict[str, object] = {
        "frozen_parameters": frozen,
        "observed_edge_margin_global_quantiles": {
            str(q): float(edges.edge_margin.quantile(q)) for q in (0.0, 0.1, 0.5, 0.9, 0.99, 1.0)
        },
        "observed_edge_coefficient_global_quantiles": {
            str(q): float(edges.edge_coefficient.quantile(q)) for q in (0.0, 0.1, 0.5, 0.9, 0.99, 1.0)
        },
        "panels": {},
    }
    for panel in PANEL_ORDER:
        panel_piece = pieces[pieces.panel == panel]
        panel_edge = edges[edges.panel == panel]
        direct = aggregate[(aggregate.panel == panel) & (aggregate.method == "direct")].iloc[0]
        casm = aggregate[(aggregate.panel == panel) & (aggregate.method == "casm_full")].iloc[0]
        payload["panels"][panel] = {
            "piece_count": len(panel_piece),
            "edge_count": len(panel_edge),
            "fallback_rate": float(panel_piece.beat_fallback.mean()),
            "direct_casm_agreement_mean": float(panel_piece.direct_casm_agreement.mean()),
            "edge_margin_median": float(panel_edge.edge_margin.median()),
            "edge_coefficient_median": float(panel_edge.edge_coefficient.median()),
            "casm_minus_direct_percentage_points": {
                metric: 100 * float(casm[metric] - direct[metric])
                for metric in ("beat_fmeasure", "beat_cmlt", "beat_amlt")
            },
        }
    (data / "numeric_summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--figure-dir", type=Path, required=True)
    parser.add_argument(
        "--only",
        nargs="*",
        choices=[f"fig{i:02d}" for i in range(1, 7)],
        help="Render only selected figures, e.g. --only fig05. Default: all figures.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_style()
    protocol = json.loads((args.data_dir / "protocol.json").read_text())
    frozen = protocol["frozen_parameters"]
    write_bootstrap(args.data_dir)
    write_numeric_summary(args.data_dir, frozen)
    selected = set(args.only or [f"fig{i:02d}" for i in range(1, 7)])
    if "fig01" in selected:
        figure_input_conditioning(args.data_dir, args.figure_dir, frozen)
    if "fig02" in selected:
        figure_real_traces(args.data_dir, args.figure_dir, frozen)
    if "fig03" in selected:
        figure_ablation(args.data_dir, args.figure_dir)
    if "fig04" in selected:
        figure_operating_points(args.data_dir, args.figure_dir)
    if "fig05" in selected:
        figure_calibration_scale(args.data_dir, args.figure_dir)
    if "fig06" in selected:
        figure_gain_risk(args.data_dir, args.figure_dir)
    print(f"WROTE {args.figure_dir}")


if __name__ == "__main__":
    main()
