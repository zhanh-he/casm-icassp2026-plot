#!/usr/bin/env python3
"""Build the reproducible 3x3 fixed-fold0 exhaustive CASM scaling figure.

The input is a canonical long-form aggregate table with one row per
evaluation-panel/configuration pair.  The builder refuses partial combination
families, fold-0 leakage, mixed score units, mixed checkpoints within a panel,
or GTZAN/SMC configuration-identity mismatches.

No experimental result is embedded in this file. Edit ``FIGURE_TWEAKS`` for
whole-figure styling and ``PANEL_TWEAKS`` for one subplot at a time. Leaving
both dictionaries unchanged reproduces the archived reference figure.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "data" / "plotting" / "fixed_fold0_exhaustive_combination_panel_scores.csv"
DEFAULT_OUTPUT = HERE / "output"

SCHEMA_VERSION = "structbeat.casm.fixed-fold0-combination-panel.v1"
SCORE_UNIT = "raw_0_1"
FOLDS = tuple(range(1, 8))
SCALES = (1, 2, 4, 7)
EXPECTED_COUNTS = {scale: math.comb(7, scale) for scale in SCALES}
X_SCALES = (0, *SCALES)

METRICS = (
    "beat_fmeasure",
    "beat_cmlt",
    "beat_amlt",
    "downbeat_fmeasure",
    "downbeat_cmlt",
    "downbeat_amlt",
)
BEAT_METRICS = METRICS[:3]

REQUIRED_COLUMNS = (
    "schema_version",
    "score_unit",
    "method",
    "scale",
    "combination_id",
    "tuning_folds",
    "evaluation_panel",
    "evaluation_piece_count",
    "checkpoint_id",
    "candidate_hash",
    "config_hash",
    *METRICS,
)

PANEL_META = {
    "gtzan_final1": {
        "piece_count": 993,
        "required_metrics": METRICS,
        "checkpoint_id": "beat_this_final1",
    },
    "smc_fold0": {
        "piece_count": 27,
        "required_metrics": BEAT_METRICS,
        "checkpoint_id": "beat_this_oof_fold0",
    },
}

PLOT_ROWS = (
    ("gtzan_final1", "beat", "GTZAN Beat\nFull dataset (N=993)"),
    ("gtzan_final1", "downbeat", "GTZAN Downbeat\nFull dataset (N=993)"),
    ("smc_fold0", "beat", "SMC Beat\nFold 0 (N=27)"),
)
PLOT_COLUMNS = (
    ("fmeasure", "F1"),
    ("cmlt", "CMLt"),
    ("amlt", "AMLt"),
)

X_LABELS = (
    "Beat This\nDirect (n=1)",
    "+ CASM 1F\n(n=7)",
    "+ CASM 2F\n(n=21)",
    "+ CASM 4F\n(n=35)",
    "+ CASM 7F\n(n=1)",
)

COMBINATION_COLOR = "#93C5FD"
MEAN_COLOR = "#1D4ED8"
INK = "#111827"
MUTED = "#4B5563"
GRID = "#D1D5DB"


# ---------------------------------------------------------------------------
# USER-EDITABLE SETTINGS
# ---------------------------------------------------------------------------
# These defaults reproduce original_reference/casm_fixed_fold0_..._3x3.png.
FIGURE_TWEAKS: dict[str, Any] = {
    "figsize": (17.2, 12.2),
    "title": "CASM tuning-data scaling on fixed evaluation panels",
    "subtitle": (
        "Fold 0 is never tuned; all 7 / 21 / 35 / 1 combinations from folds 1–7. "
        "GTZAN final1 is a post-hoc/test-conditioned sensitivity panel."
    ),
    "footer": (
        "Focused y-ranges: each lower boundary is that panel's Direct score − 2.0 pp; "
        "the first labeled tick is Direct. Scatter replication unit = fold combination, "
        "not piece or seed."
    ),
    "scatter_size": 24,
    "scatter_alpha": 0.72,
    "scatter_color": COMBINATION_COLOR,
    "mean_color": MEAN_COLOR,
    "mean_linewidth": 2.15,
    "mean_markersize": 6.4,
    "mean_label_format": "{:.3f}",
    "mean_label_fontsize": 7.7,
    "xlim": (-0.43, 4.43),
    "xtick_fontsize": 8.0,
    "ytick_fontsize": 8.7,
    "grid_alpha": 0.65,
    "layout": {
        "left": 0.105,
        "right": 0.982,
        "top": 0.91,
        "bottom": 0.095,
        "wspace": 0.27,
        "hspace": 0.39,
    },
}

# Keys are "evaluation_panel.component.metric". Add overrides only where you
# want a subplot to differ. Supported keys include:
#   ylim, yticks, title, ylabel, xlabels, show_mean_labels,
#   mean_label_offsets, scatter_color, mean_color.
# Example:
# "gtzan_final1.beat.beat_fmeasure": {
#     "ylim": (87.486, 90.20),
#     "yticks": [89.486, 89.70, 89.90, 90.10],
#     "mean_label_offsets": [(0, 7), (0, 7), (0, 10), (0, 7), (0, 7)],
# },
PANEL_TWEAKS: dict[str, dict[str, Any]] = {
    "gtzan_final1.beat.beat_fmeasure": {},
    "gtzan_final1.beat.beat_cmlt": {},
    "gtzan_final1.beat.beat_amlt": {},
    "gtzan_final1.downbeat.downbeat_fmeasure": {},
    "gtzan_final1.downbeat.downbeat_cmlt": {},
    "gtzan_final1.downbeat.downbeat_amlt": {},
    "smc_fold0.beat.beat_fmeasure": {},
    "smc_fold0.beat.beat_cmlt": {},
    "smc_fold0.beat.beat_amlt": {},
}


class InputError(RuntimeError):
    """Raised when the result table violates the locked figure contract."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_folds(value: str, *, row_number: int) -> tuple[int, ...]:
    text = value.strip()
    if text in {"", "none"}:
        return ()
    try:
        folds = tuple(int(item) for item in text.split(";"))
    except ValueError as exc:
        raise InputError(f"row {row_number}: tuning_folds must use semicolon-separated integers") from exc
    if tuple(sorted(set(folds))) != folds:
        raise InputError(f"row {row_number}: tuning_folds must be unique, sorted, and canonical")
    return folds


def parse_metric(value: str, *, field: str, row_number: int, required: bool) -> float | None:
    text = value.strip()
    if not text:
        if required:
            raise InputError(f"row {row_number}: missing required metric {field}")
        return None
    try:
        score = float(text)
    except ValueError as exc:
        raise InputError(f"row {row_number}: non-numeric {field}={text!r}") from exc
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise InputError(f"row {row_number}: {field} must be a finite raw score in [0,1]")
    return score


def load_and_validate(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise InputError(f"input does not exist: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise InputError(f"missing required columns: {missing}")
        raw_rows = list(reader)
    if not raw_rows:
        raise InputError("input contains a header but no result rows")

    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, int, str]] = set()
    for row_number, raw in enumerate(raw_rows, start=2):
        if raw["schema_version"].strip() != SCHEMA_VERSION:
            raise InputError(f"row {row_number}: schema_version must be {SCHEMA_VERSION}")
        if raw["score_unit"].strip() != SCORE_UNIT:
            raise InputError(f"row {row_number}: score_unit must be {SCORE_UNIT}")

        method = raw["method"].strip()
        if method not in {"beat_this_direct", "casm"}:
            raise InputError(f"row {row_number}: unsupported method {method!r}")
        try:
            scale = int(raw["scale"])
        except ValueError as exc:
            raise InputError(f"row {row_number}: scale must be integer 0/1/2/4/7") from exc
        if scale not in X_SCALES:
            raise InputError(f"row {row_number}: scale must be one of {X_SCALES}")

        panel = raw["evaluation_panel"].strip()
        if panel not in PANEL_META:
            raise InputError(f"row {row_number}: unknown evaluation_panel {panel!r}")
        try:
            piece_count = int(raw["evaluation_piece_count"])
        except ValueError as exc:
            raise InputError(f"row {row_number}: evaluation_piece_count must be an integer") from exc
        expected_piece_count = int(PANEL_META[panel]["piece_count"])
        if piece_count != expected_piece_count:
            raise InputError(
                f"row {row_number}: {panel} must contain {expected_piece_count} pieces, got {piece_count}"
            )

        combination_id = raw["combination_id"].strip()
        if not combination_id:
            raise InputError(f"row {row_number}: combination_id is required")
        tuning_folds = parse_folds(raw["tuning_folds"], row_number=row_number)
        candidate_hash = raw["candidate_hash"].strip()
        config_hash = raw["config_hash"].strip()
        if not config_hash:
            raise InputError(f"row {row_number}: config_hash is required for every method")
        if method == "beat_this_direct":
            if scale != 0 or tuning_folds or combination_id != "direct":
                raise InputError(
                    f"row {row_number}: Direct must use scale=0, combination_id=direct, and no tuning folds"
                )
            if candidate_hash:
                raise InputError(f"row {row_number}: Direct candidate_hash must be blank")
        else:
            if scale not in SCALES or len(tuning_folds) != scale:
                raise InputError(f"row {row_number}: CASM fold count must equal scale {scale}")
            if any(fold not in FOLDS for fold in tuning_folds):
                raise InputError(f"row {row_number}: tuning folds must be drawn only from 1..7")
            if not candidate_hash:
                raise InputError(f"row {row_number}: CASM rows require candidate_hash")

        checkpoint_id = raw["checkpoint_id"].strip()
        expected_checkpoint = str(PANEL_META[panel]["checkpoint_id"])
        if checkpoint_id != expected_checkpoint:
            raise InputError(
                f"row {row_number}: {panel} checkpoint_id must be {expected_checkpoint!r}"
            )

        required_metrics = set(PANEL_META[panel]["required_metrics"])
        metrics = {
            field: parse_metric(
                raw[field], field=field, row_number=row_number, required=field in required_metrics
            )
            for field in METRICS
        }
        if panel == "smc_fold0" and any(metrics[field] is not None for field in METRICS[3:]):
            raise InputError(f"row {row_number}: SMC fold0 must not contain downbeat scores")

        unique_key = (panel, method, scale, combination_id)
        if unique_key in seen_keys:
            raise InputError(f"row {row_number}: duplicate row key {unique_key}")
        seen_keys.add(unique_key)
        rows.append(
            {
                "row_number": row_number,
                "method": method,
                "scale": scale,
                "combination_id": combination_id,
                "tuning_folds": tuning_folds,
                "evaluation_panel": panel,
                "evaluation_piece_count": piece_count,
                "checkpoint_id": checkpoint_id,
                "candidate_hash": candidate_hash,
                "config_hash": config_hash,
                **metrics,
            }
        )

    for panel in PANEL_META:
        panel_rows = [row for row in rows if row["evaluation_panel"] == panel]
        direct_rows = [row for row in panel_rows if row["method"] == "beat_this_direct"]
        if len(direct_rows) != 1:
            raise InputError(f"{panel}: expected exactly one Direct row, found {len(direct_rows)}")
        checkpoints = {row["checkpoint_id"] for row in panel_rows}
        if len(checkpoints) != 1:
            raise InputError(f"{panel}: all rows must use one fixed checkpoint_id, found {sorted(checkpoints)}")

        for scale in SCALES:
            family = [row for row in panel_rows if row["method"] == "casm" and row["scale"] == scale]
            expected_folds = set(itertools.combinations(FOLDS, scale))
            observed_folds = {row["tuning_folds"] for row in family}
            if len(family) != EXPECTED_COUNTS[scale] or observed_folds != expected_folds:
                missing = sorted(expected_folds - observed_folds)
                extra = sorted(observed_folds - expected_folds)
                raise InputError(
                    f"{panel} {scale}F is not exhaustive: rows={len(family)}, "
                    f"expected={EXPECTED_COUNTS[scale]}, missing={missing[:5]}, extra={extra[:5]}"
                )

    # The same frozen decoder selected from each fold subset must be evaluated on
    # both fixed panels.  Only the panel-specific checkpoint_id may differ.
    def combo_map(panel: str) -> dict[tuple[int, tuple[int, ...]], dict[str, Any]]:
        return {
            (row["scale"], row["tuning_folds"]): row
            for row in rows
            if row["evaluation_panel"] == panel and row["method"] == "casm"
        }

    gtzan_map = combo_map("gtzan_final1")
    smc_map = combo_map("smc_fold0")
    if set(gtzan_map) != set(smc_map):
        raise InputError("GTZAN and SMC CASM combination keys do not align")
    for key in sorted(gtzan_map):
        left, right = gtzan_map[key], smc_map[key]
        for field in ("combination_id", "candidate_hash", "config_hash"):
            if left[field] != right[field]:
                raise InputError(f"combination {key}: GTZAN/SMC {field} mismatch")

    direct_configs = {
        row["config_hash"] for row in rows if row["method"] == "beat_this_direct"
    }
    if len(direct_configs) != 1:
        raise InputError("GTZAN and SMC Direct config_hash values must match")

    expected_total = 2 * (1 + sum(EXPECTED_COUNTS.values()))
    if len(rows) != expected_total:
        raise InputError(f"expected exactly {expected_total} rows, found {len(rows)}")
    return rows


def load_axis_overrides(path: Path | None) -> tuple[dict[str, dict[str, Any]], str | None]:
    if path is None:
        return {}, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "structbeat.casm.fixed-fold0-axis-overrides.v1":
        raise InputError("axis override schema mismatch")
    panels = payload.get("panels")
    if not isinstance(panels, dict):
        raise InputError("axis override file must contain an object named panels")
    if any(not isinstance(value, dict) for value in panels.values()):
        raise InputError("every axis override panel value must be an object")
    return panels, sha256(path)


def nice_step_at_least(value: float) -> float:
    value = max(float(value), 1e-9)
    exponent = math.floor(math.log10(value))
    base = 10.0**exponent
    for multiplier in (1.0, 2.0, 2.5, 5.0, 10.0):
        candidate = multiplier * base
        if candidate + 1e-12 >= value:
            return candidate
    raise AssertionError("unreachable")


def axis_geometry(
    direct_pct: float,
    values_pct: list[float],
    override: dict[str, Any],
    *,
    top_padding_pp: float,
) -> dict[str, Any]:
    lower_pct = direct_pct - 2.0
    observed_min = min(values_pct)
    if observed_min < lower_pct - 1e-9:
        raise InputError(
            "locked Direct-minus-2pp lower boundary would clip a plotted value: "
            f"Direct={direct_pct:.9f}, lower={lower_pct:.9f}, min={observed_min:.9f}"
        )
    target = max(max(values_pct), direct_pct) + top_padding_pp
    top_tick_override = override.get("top_tick_pct")
    tick_count = int(override.get("tick_count") or 5)
    if tick_count < 2 or tick_count > 10:
        raise InputError("axis override tick_count must be between 2 and 10")

    if top_tick_override is not None:
        top_tick = float(top_tick_override)
        if not math.isfinite(top_tick):
            raise InputError("top_tick_pct must be finite")
        if top_tick > 100.0 + 1e-12:
            raise InputError("top_tick_pct cannot exceed the 100% metric bound")
        if top_tick <= direct_pct or top_tick + 1e-12 < max(values_pct):
            raise InputError("top_tick_pct must exceed Direct and cover every plotted value")
        ticks = np.linspace(direct_pct, top_tick, tick_count).tolist()
    else:
        if direct_pct >= 100.0 - 1e-12:
            raise InputError(
                "Direct is 100%; cannot place an additional labeled tick above the locked first tick"
            )
        step = nice_step_at_least(max(target - direct_pct, 0.1) / (tick_count - 1))
        top_tick = direct_pct + step * math.ceil((target - direct_pct) / step)
        if top_tick > 100.0:
            top_tick = 100.0
            ticks = np.linspace(direct_pct, top_tick, tick_count).tolist()
        else:
            ticks = np.arange(direct_pct, top_tick + step * 0.5, step).tolist()

    if abs(ticks[0] - direct_pct) > 1e-9:
        raise AssertionError("first labeled tick must equal Direct")
    upper_pct = float(ticks[-1] + max((ticks[-1] - direct_pct) * 0.045, 0.06))
    return {
        "lower_pct": float(lower_pct),
        "upper_pct": upper_pct,
        "first_labeled_tick_pct": float(direct_pct),
        "top_labeled_tick_pct": float(ticks[-1]),
        "ticks_pct": [float(value) for value in ticks],
    }


def family_rows(rows: list[dict[str, Any]], panel: str, scale: int) -> list[dict[str, Any]]:
    method = "beat_this_direct" if scale == 0 else "casm"
    return sorted(
        (
            row
            for row in rows
            if row["evaluation_panel"] == panel
            and row["method"] == method
            and row["scale"] == scale
        ),
        key=lambda row: (row["tuning_folds"], row["combination_id"]),
    )


def metric_name(component: str, suffix: str) -> str:
    return f"{component}_{suffix}"


def build_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for panel, component, _ in PLOT_ROWS:
        for suffix, _ in PLOT_COLUMNS:
            metric = metric_name(component, suffix)
            for scale in X_SCALES:
                values = np.asarray(
                    [float(row[metric]) for row in family_rows(rows, panel, scale)], dtype=float
                )
                output.append(
                    {
                        "evaluation_panel": panel,
                        "component": component,
                        "metric": metric,
                        "scale": scale,
                        "combination_count": int(len(values)),
                        "mean_raw": float(values.mean()),
                        "population_sd_raw": "" if len(values) == 1 else float(values.std(ddof=0)),
                        "min_raw": float(values.min()),
                        "max_raw": float(values.max()),
                        "mean_pct": float(values.mean() * 100.0),
                        "population_sd_pct": "" if len(values) == 1 else float(values.std(ddof=0) * 100.0),
                        "min_pct": float(values.min() * 100.0),
                        "max_pct": float(values.max() * 100.0),
                    }
                )
    return output


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def preflight_axis_geometry(
    rows: list[dict[str, Any]],
    axis_overrides: dict[str, dict[str, Any]],
    *,
    top_padding_pp: float,
) -> dict[str, Any]:
    valid_keys = {
        f"{panel}.{component}.{metric_name(component, suffix)}"
        for panel, component, _ in PLOT_ROWS
        for suffix, _ in PLOT_COLUMNS
    }
    unknown_keys = sorted(set(axis_overrides) - valid_keys)
    if unknown_keys:
        raise InputError(f"unknown axis override keys: {unknown_keys}")
    output: dict[str, Any] = {}
    for panel, component, _ in PLOT_ROWS:
        for suffix, _ in PLOT_COLUMNS:
            metric = metric_name(component, suffix)
            values_pct = [
                float(row[metric]) * 100.0
                for scale in X_SCALES
                for row in family_rows(rows, panel, scale)
            ]
            direct_pct = float(family_rows(rows, panel, 0)[0][metric]) * 100.0
            axis_key = f"{panel}.{component}.{metric}"
            output[axis_key] = axis_geometry(
                direct_pct,
                values_pct,
                axis_overrides.get(axis_key, {}),
                top_padding_pp=top_padding_pp,
            )
    return output


def make_figure(
    rows: list[dict[str, Any]],
    axis_overrides: dict[str, dict[str, Any]],
    *,
    output_dir: Path,
    basename: str,
    dpi: int,
    top_padding_pp: float,
    show_mean_labels: bool,
    show: bool,
) -> tuple[list[Path], dict[str, Any]]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 12,
            "axes.labelsize": 9.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig, axes = plt.subplots(
        3, 3, figsize=FIGURE_TWEAKS["figsize"], constrained_layout=False
    )
    axis_manifest: dict[str, Any] = {}

    for row_index, (panel, component, row_label) in enumerate(PLOT_ROWS):
        for column_index, (suffix, column_label) in enumerate(PLOT_COLUMNS):
            ax = axes[row_index, column_index]
            metric = metric_name(component, suffix)
            axis_key = f"{panel}.{component}.{metric}"
            panel_tweaks = PANEL_TWEAKS.get(axis_key, {})
            means_pct: list[float] = []
            all_values_pct: list[float] = []

            for x, scale in enumerate(X_SCALES):
                current_rows = family_rows(rows, panel, scale)
                values_pct = np.asarray([float(row[metric]) * 100.0 for row in current_rows])
                means_pct.append(float(values_pct.mean()))
                all_values_pct.extend(values_pct.tolist())
                if scale > 0:
                    half_width = 0.0 if len(values_pct) == 1 else min(0.25, 0.018 * len(values_pct))
                    jitter = np.linspace(-half_width, half_width, len(values_pct))
                    ax.scatter(
                        np.full(len(values_pct), x) + jitter,
                        values_pct,
                        s=FIGURE_TWEAKS["scatter_size"],
                        color=panel_tweaks.get(
                            "scatter_color", FIGURE_TWEAKS["scatter_color"]
                        ),
                        alpha=FIGURE_TWEAKS["scatter_alpha"],
                        edgecolor="white",
                        linewidth=0.45,
                        zorder=2,
                    )

            direct_pct = means_pct[0]
            geometry = axis_geometry(
                direct_pct,
                all_values_pct,
                axis_overrides.get(axis_key, {}),
                top_padding_pp=top_padding_pp,
            )
            if panel_tweaks.get("ylim") is not None:
                lower_pct, upper_pct = map(float, panel_tweaks["ylim"])
                if not lower_pct < upper_pct:
                    raise InputError(f"{axis_key}: PANEL_TWEAKS ylim must be increasing")
                geometry["lower_pct"] = lower_pct
                geometry["upper_pct"] = upper_pct
            if panel_tweaks.get("yticks") is not None:
                ticks_pct = [float(value) for value in panel_tweaks["yticks"]]
                if not ticks_pct or ticks_pct != sorted(set(ticks_pct)):
                    raise InputError(f"{axis_key}: PANEL_TWEAKS yticks must be sorted and unique")
                geometry["ticks_pct"] = ticks_pct
            axis_manifest[axis_key] = geometry

            x_values = np.arange(len(X_SCALES))
            mean_color = panel_tweaks.get("mean_color", FIGURE_TWEAKS["mean_color"])
            ax.plot(
                x_values,
                means_pct,
                color=mean_color,
                linewidth=FIGURE_TWEAKS["mean_linewidth"],
                marker="o",
                markersize=FIGURE_TWEAKS["mean_markersize"],
                markerfacecolor=mean_color,
                markeredgecolor="white",
                markeredgewidth=0.9,
                zorder=4,
            )
            if show_mean_labels and panel_tweaks.get("show_mean_labels", True):
                offsets = panel_tweaks.get("mean_label_offsets", [(0, 7)] * len(X_SCALES))
                if len(offsets) != len(X_SCALES):
                    raise InputError(
                        f"{axis_key}: mean_label_offsets needs {len(X_SCALES)} pairs"
                    )
                for x, mean, offset in zip(x_values, means_pct, offsets):
                    ax.annotate(
                        FIGURE_TWEAKS["mean_label_format"].format(mean),
                        (x, mean),
                        xytext=offset,
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=FIGURE_TWEAKS["mean_label_fontsize"],
                        fontweight=700,
                        color=mean_color,
                        zorder=5,
                    )

            ax.set_xlim(*FIGURE_TWEAKS["xlim"])
            ax.set_ylim(geometry["lower_pct"], geometry["upper_pct"])
            ax.set_yticks(geometry["ticks_pct"])
            ax.set_yticklabels([f"{value:.3f}" for value in geometry["ticks_pct"]])
            ax.set_xticks(x_values, panel_tweaks.get("xlabels", X_LABELS))
            ax.tick_params(axis="x", labelsize=FIGURE_TWEAKS["xtick_fontsize"], pad=5)
            ax.tick_params(axis="y", labelsize=FIGURE_TWEAKS["ytick_fontsize"])
            ax.grid(
                axis="y", color=GRID, alpha=FIGURE_TWEAKS["grid_alpha"], linewidth=0.75
            )
            ax.set_axisbelow(True)
            ax.spines["left"].set_color("#9CA3AF")
            ax.spines["bottom"].set_color("#9CA3AF")
            if panel_tweaks.get("title") is not None:
                ax.set_title(
                    panel_tweaks["title"], loc="left", fontweight="bold", color=INK, pad=9
                )
            elif row_index == 0:
                ax.set_title(column_label, loc="left", fontweight="bold", color=INK, pad=9)
            if panel_tweaks.get("ylabel") is not None:
                ax.set_ylabel(
                    panel_tweaks["ylabel"], color=INK, fontweight=700, labelpad=12
                )
            elif column_index == 0:
                ax.set_ylabel(f"{row_label}\nScore (%)", color=INK, fontweight=700, labelpad=12)

    fig.suptitle(
        FIGURE_TWEAKS["title"],
        x=0.055,
        y=0.987,
        ha="left",
        fontsize=17,
        fontweight="bold",
        color=INK,
    )
    fig.text(
        0.055,
        0.956,
        FIGURE_TWEAKS["subtitle"],
        ha="left",
        fontsize=10,
        color=MUTED,
    )
    legend_handles = [
        Line2D(
            [0], [0], marker="o", linestyle="none", markerfacecolor=COMBINATION_COLOR,
            markeredgecolor="white", markersize=6, label="One development-fold combination"
        ),
        Line2D(
            [0], [0], marker="o", color=MEAN_COLOR, markerfacecolor=MEAN_COLOR,
            markeredgecolor="white", linewidth=2.15, markersize=6,
            label="Equal-weight family mean (connected)"
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper right",
        bbox_to_anchor=(0.975, 0.984),
        frameon=False,
        ncol=2,
        fontsize=9,
    )
    fig.text(
        0.055,
        0.018,
        FIGURE_TWEAKS["footer"],
        ha="left",
        fontsize=8.7,
        color=MUTED,
    )
    fig.subplots_adjust(**FIGURE_TWEAKS["layout"])

    png = output_dir / f"{basename}.png"
    svg = output_dir / f"{basename}.svg"
    fig.savefig(png, dpi=dpi, facecolor="white")
    fig.savefig(svg, facecolor="white")
    if show:
        plt.show()
    plt.close(fig)
    return [png, svg], axis_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--basename",
        default="casm_datascaling_3x3",
    )
    parser.add_argument("--axis-overrides", type=Path)
    parser.add_argument("--top-padding-pp", type=float, default=0.35)
    parser.add_argument("--dpi", type=int, default=240)
    parser.add_argument("--hide-mean-labels", action="store_true")
    parser.add_argument("--show", action="store_true", help="open a Matplotlib preview window")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not math.isfinite(args.top_padding_pp) or args.top_padding_pp <= 0:
        raise InputError("--top-padding-pp must be finite and positive")
    rows = load_and_validate(args.input.resolve())
    axis_overrides, axis_overrides_sha = load_axis_overrides(
        args.axis_overrides.resolve() if args.axis_overrides else None
    )
    preflight_geometry = preflight_axis_geometry(
        rows, axis_overrides, top_padding_pp=args.top_padding_pp
    )
    if args.validate_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "input": str(args.input.resolve()),
                    "input_sha256": sha256(args.input.resolve()),
                    "row_count": len(rows),
                    "combination_counts": EXPECTED_COUNTS,
                    "axis_geometry": preflight_geometry,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = build_summary(rows)
    summary_path = output_dir / "plotted_family_summary.csv"
    write_summary(summary_path, summary_rows)
    figures, axis_manifest = make_figure(
        rows,
        axis_overrides,
        output_dir=output_dir,
        basename=args.basename,
        dpi=args.dpi,
        top_padding_pp=args.top_padding_pp,
        show_mean_labels=not args.hide_mean_labels,
        show=args.show,
    )

    manifest_path = output_dir / "FIGURE_MANIFEST.json"
    manifest = {
        "schema": "structbeat.casm.fixed-fold0-exhaustive-figure-manifest.v1",
        "input": str(args.input.resolve()),
        "input_sha256": sha256(args.input.resolve()),
        "builder": str(Path(__file__).resolve()),
        "builder_sha256": sha256(Path(__file__).resolve()),
        "axis_overrides": str(args.axis_overrides.resolve()) if args.axis_overrides else None,
        "axis_overrides_sha256": axis_overrides_sha,
        "score_unit": SCORE_UNIT,
        "fixed_panels": {key: value["piece_count"] for key, value in PANEL_META.items()},
        "expected_combination_counts": EXPECTED_COUNTS,
        "input_row_count": len(rows),
        "y_axis_rule": {
            "lower": "panel-specific Direct raw score minus 0.02 (2.0 percentage points)",
            "first_labeled_tick": "panel-specific Direct score",
            "broken_axis": False,
        },
        "axis_geometry": axis_manifest,
        "outputs": {},
        "manifest_hashing": "FIGURE_MANIFEST.sha256 stores this manifest's SHA-256",
    }
    for path in [summary_path, *figures]:
        manifest["outputs"][str(path)] = sha256(path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_sha_path = output_dir / "FIGURE_MANIFEST.sha256"
    manifest_sha_path.write_text(
        f"{sha256(manifest_path)}  {manifest_path.name}\n", encoding="utf-8"
    )
    reported_outputs = {
        **manifest["outputs"],
        str(manifest_path): sha256(manifest_path),
        str(manifest_sha_path): sha256(manifest_sha_path),
    }
    print(json.dumps({"status": "PASS", "outputs": reported_outputs}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
