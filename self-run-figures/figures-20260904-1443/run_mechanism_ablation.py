#!/usr/bin/env python3
"""Run CASM mechanism ablations on cached activations.

This script never retrains a backbone.  It evaluates frozen decoders, records
per-piece metrics, and exports the *effective* input-conditioned quantities
used by CASM (local period margin, edge target, edge stiffness, and fallback).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.special import expit

from structbeat.decoders import (
    CASMDecoder,
    DBNDecoder,
    MinimalDecoder,
    PLPDPDecoder,
    _edge_local_maxima,
    deduplicate_peaks,
    local_maxima,
)
from structbeat.evaluation import evaluate_item, load_cache_item


FROZEN_KEYS = (
    "fps",
    "candidate_threshold",
    "min_bpm",
    "max_bpm",
    "local_window_seconds",
    "temperature",
    "logit_clip",
    "duration_weight",
    "duration_sigma",
    "uncertain_sigma",
    "tempo_bias",
    "fallback_minimal_ratio",
    "fallback_maximal_ratio",
    "downbeat_mode",
    "meters",
    "meter_change_penalty",
    "downbeat_temperature",
    "bar_reward",
    "downbeat_agreement_threshold",
    "downbeat_agreement_tolerance",
)

METHODS = (
    "direct",
    "casm_full",
    "local_target_fixed",
    "strength_only",
    "width_only",
    "one_sided",
    "no_safeguard",
    "dbn_default",
    "dbn_matched_30_300",
    "plpdp",
)

METHOD_LABELS = {
    "direct": "Direct",
    "casm_full": "CASM",
    "local_target_fixed": "Local target, fixed precision",
    "strength_only": "Ambiguity: strength only",
    "width_only": "Ambiguity: width only",
    "one_sided": "One-endpoint context",
    "no_safeguard": "CASM without safeguards",
    "dbn_default": "DBN (55--215 BPM)",
    "dbn_matched_30_300": "DBN (30--300 BPM)",
    "plpdp": "PLPDP",
}

PANEL_LABELS = {
    "bt_smc_oof": "Beat This / SMC OOF",
    "mscnn_smc_oof": "MSCNN-lite / SMC OOF",
    "bt_gtzan_seed0": "Beat This / GTZAN seed 0",
    "mscnn_gtzan": "MSCNN-lite / GTZAN",
    "tcn_smc_final0": "TCN / SMC final0",
}

_WORKER_DECODER = None


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=True)
        handle.write("\n")
    os.replace(temporary, path)


class LocalTargetFixedDecoder(CASMDecoder):
    """Keep the local period target but remove ambiguity modulation."""

    def _estimate_local_tempo(self, beat_prob, candidates):
        periods, confidence = super()._estimate_local_tempo(beat_prob, candidates)
        return periods, np.ones_like(confidence)


class StrengthOnlyDecoder(CASMDecoder):
    """Let ambiguity scale the penalty amplitude but not its width."""

    def _duration_cost(self, intervals, starts, end, periods, confidence):
        expected = np.sqrt(periods[end] * periods[starts])
        segment_confidence = np.sqrt(confidence[end] * confidence[starts])
        log_error = np.log(np.maximum(intervals, 1.0) / expected)
        return (
            self.duration_weight
            * segment_confidence
            * 0.5
            * (log_error / self.duration_sigma) ** 2
        )


class WidthOnlyDecoder(CASMDecoder):
    """Let ambiguity change tolerance but keep unit penalty amplitude."""

    def _duration_cost(self, intervals, starts, end, periods, confidence):
        expected = np.sqrt(periods[end] * periods[starts])
        segment_confidence = np.sqrt(confidence[end] * confidence[starts])
        sigma = self.duration_sigma + (1.0 - segment_confidence) * self.uncertain_sigma
        log_error = np.log(np.maximum(intervals, 1.0) / expected)
        return self.duration_weight * 0.5 * (log_error / sigma) ** 2


class OneSidedDecoder(CASMDecoder):
    """Use only the destination candidate's local context."""

    def _duration_cost(self, intervals, starts, end, periods, confidence):
        expected = np.full(len(starts), periods[end], dtype=float)
        segment_confidence = np.full(len(starts), confidence[end], dtype=float)
        sigma = self.duration_sigma + (1.0 - segment_confidence) * self.uncertain_sigma
        log_error = np.log(np.maximum(intervals, 1.0) / expected)
        return (
            self.duration_weight
            * segment_confidence
            * 0.5
            * (log_error / sigma) ** 2
        )


def normalized_frozen(parameters: dict[str, object]) -> dict[str, object]:
    output = {key: parameters[key] for key in FROZEN_KEYS if key in parameters}
    if "meters" in output:
        output["meters"] = tuple(output["meters"])
    return output


def make_decoder(method: str, frozen: dict[str, object]):
    params = normalized_frozen(frozen)
    if method == "direct":
        return MinimalDecoder(fps=float(params.get("fps", 50.0)))
    if method == "casm_full":
        return CASMDecoder(**params)
    if method == "local_target_fixed":
        return LocalTargetFixedDecoder(**params)
    if method == "strength_only":
        return StrengthOnlyDecoder(**params)
    if method == "width_only":
        return WidthOnlyDecoder(**params)
    if method == "one_sided":
        return OneSidedDecoder(**params)
    if method == "no_safeguard":
        return CASMDecoder(
            **{
                **params,
                "fallback_minimal_ratio": -math.inf,
                "fallback_maximal_ratio": math.inf,
                "downbeat_agreement_threshold": 0.0,
            }
        )
    if method == "dbn_default":
        return DBNDecoder(fps=float(params.get("fps", 50.0)))
    if method == "dbn_matched_30_300":
        return DBNDecoder(
            fps=float(params.get("fps", 50.0)), min_bpm=30.0, max_bpm=300.0
        )
    if method == "plpdp":
        return PLPDPDecoder(
            fps=float(params.get("fps", 50.0)), min_bpm=30, max_bpm=300
        )
    raise ValueError(method)


def init_worker(method: str, frozen: dict[str, object]) -> None:
    global _WORKER_DECODER
    _WORKER_DECODER = make_decoder(method, frozen)


def evaluate_path(path_text: str) -> dict[str, object]:
    if _WORKER_DECODER is None:
        raise RuntimeError("worker decoder not initialized")
    item = load_cache_item(Path(path_text))
    row = evaluate_item(item, _WORKER_DECODER, trim_seconds=5.0)
    row["source_path"] = path_text
    return row


def panel_paths(project: Path) -> dict[str, list[Path]]:
    panels: dict[str, list[Path]] = {}
    for backbone in ("beat_this", "mscnn"):
        key = "bt_smc_oof" if backbone == "beat_this" else "mscnn_smc_oof"
        paths: list[Path] = []
        for fold in range(8):
            paths.extend(
                sorted((project / f"caches/8fold/{backbone}_fold{fold}_val").glob("smc__*.npz"))
            )
        panels[key] = paths
    panels["bt_gtzan_seed0"] = sorted(
        (project / "caches/pilot/beat_this_final0_gtzan").glob("*.npz")
    )
    panels["mscnn_gtzan"] = sorted(
        (project / "caches/pilot/mscnn_final_last_gtzan").glob("*.npz")
    )
    panels["tcn_smc_final0"] = sorted(
        (project / "runs/20260903_final01_smc_casm_v1/cache/tcn_final0").glob("*.npz")
    )
    expected = {
        "bt_smc_oof": 217,
        "mscnn_smc_oof": 217,
        "bt_gtzan_seed0": 993,
        "mscnn_gtzan": 993,
        "tcn_smc_final0": 217,
    }
    for name, paths in panels.items():
        if len(paths) != expected[name]:
            raise RuntimeError(f"{name}: expected {expected[name]} caches, found {len(paths)}")
    return panels


def valid_existing(path: Path, expected: int) -> bool:
    if not path.exists():
        return False
    try:
        return len(pd.read_csv(path)) == expected
    except Exception:
        return False


def run_panel_method(
    method: str,
    panel: str,
    paths: list[Path],
    frozen: dict[str, object],
    output: Path,
    workers: int,
) -> Path:
    destination = output / "raw" / f"{panel}__{method}.pieces.csv"
    if valid_existing(destination, len(paths)):
        print(f"SKIP {panel} {method} ({len(paths)})", flush=True)
        return destination
    started = time.time()
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=init_worker,
        initargs=(method, frozen),
    ) as executor:
        rows = list(executor.map(evaluate_path, map(str, paths), chunksize=4))
    table = pd.DataFrame(rows)
    table.insert(0, "method", method)
    table.insert(0, "panel", panel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    table.to_csv(temporary, index=False)
    os.replace(temporary, destination)
    print(
        f"DONE {panel} {method} n={len(table)} elapsed={time.time()-started:.1f}s "
        f"F={100*table.beat_fmeasure.mean():.3f}",
        flush=True,
    )
    return destination


def one_to_one_f(first: np.ndarray, second: np.ndarray, tolerance: float) -> float:
    first = np.sort(np.asarray(first, dtype=float))
    second = np.sort(np.asarray(second, dtype=float))
    if not len(first) and not len(second):
        return 1.0
    if not len(first) or not len(second):
        return 0.0
    i = j = matches = 0
    while i < len(first) and j < len(second):
        delta = first[i] - second[j]
        if abs(delta) <= tolerance:
            matches += 1
            i += 1
            j += 1
        elif delta < 0:
            i += 1
        else:
            j += 1
    return 2 * matches / (len(first) + len(second))


def casm_trace(path: Path, frozen: dict[str, object]) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    item = load_cache_item(path)
    decoder = CASMDecoder(**normalized_frozen(frozen))
    beat_logits = np.asarray(item["beat_logits"], dtype=np.float64)
    beat_prob = expit(beat_logits)
    candidates = _edge_local_maxima(beat_prob)
    candidates = candidates[beat_prob[candidates] >= decoder.candidate_threshold]
    direct_frames = deduplicate_peaks(local_maxima(beat_logits, 7, 0.0))
    if len(candidates):
        periods, confidence = decoder._estimate_local_tempo(beat_prob, candidates)
        structured_frames = decoder._decode_beats(beat_logits, candidates, periods, confidence)
    else:
        periods = np.empty(0)
        confidence = np.empty(0)
        structured_frames = np.empty(0)
    count_ratio = len(structured_frames) / len(direct_frames) if len(direct_frames) else math.nan
    fallback = bool(
        len(direct_frames)
        and (
            count_ratio < decoder.fallback_minimal_ratio
            or count_ratio > decoder.fallback_maximal_ratio
        )
    )
    final_frames = direct_frames if fallback else structured_frames
    final_times = final_frames / decoder.fps
    direct_times = direct_frames / decoder.fps
    structured_times = structured_frames / decoder.fps
    direct_metrics = evaluate_item(item, MinimalDecoder(fps=decoder.fps), 5.0)
    full_metrics = evaluate_item(item, decoder, 5.0)

    candidate_rows: list[dict[str, object]] = []
    for index, (frame, period, conf) in enumerate(zip(candidates, periods, confidence)):
        sigma = decoder.duration_sigma + (1.0 - conf) * decoder.uncertain_sigma
        coefficient = decoder.duration_weight * conf / (2.0 * sigma * sigma)
        candidate_rows.append(
            {
                "piece": item["piece"],
                "dataset": item["dataset"],
                "source_path": str(path),
                "candidate_index": index,
                "time_seconds": frame / decoder.fps,
                "activation": beat_prob[frame],
                "period_margin": conf,
                "period_seconds": period / decoder.fps,
                "period_bpm": 60.0 * decoder.fps / period,
                "endpoint_sigma": sigma,
                "endpoint_coefficient": coefficient,
            }
        )

    candidate_index = {int(frame): index for index, frame in enumerate(candidates)}
    edge_rows: list[dict[str, object]] = []
    for start_frame, end_frame in zip(structured_frames[:-1], structured_frames[1:]):
        start = candidate_index[int(round(start_frame))]
        end = candidate_index[int(round(end_frame))]
        c_edge = math.sqrt(float(confidence[start]) * float(confidence[end]))
        sigma = decoder.duration_sigma + (1.0 - c_edge) * decoder.uncertain_sigma
        coefficient = decoder.duration_weight * c_edge / (2.0 * sigma * sigma)
        target_seconds = math.sqrt(float(periods[start]) * float(periods[end])) / decoder.fps
        interval_seconds = (float(end_frame) - float(start_frame)) / decoder.fps
        log_error = math.log(max(interval_seconds, 1e-8) / target_seconds)
        edge_rows.append(
            {
                "piece": item["piece"],
                "dataset": item["dataset"],
                "source_path": str(path),
                "start_seconds": float(start_frame) / decoder.fps,
                "end_seconds": float(end_frame) / decoder.fps,
                "interval_seconds": interval_seconds,
                "target_seconds": target_seconds,
                "target_bpm": 60.0 / target_seconds,
                "edge_margin": c_edge,
                "edge_sigma": sigma,
                "edge_coefficient": coefficient,
                "log_duration_error": log_error,
                "duration_cost": coefficient * log_error * log_error,
            }
        )

    summary = {
        "piece": item["piece"],
        "dataset": item["dataset"],
        "source_path": str(path),
        "candidate_count": len(candidates),
        "direct_count": len(direct_frames),
        "structured_count": len(structured_frames),
        "final_count": len(final_frames),
        "count_ratio": count_ratio,
        "beat_fallback": fallback,
        "direct_casm_agreement": one_to_one_f(direct_times, final_times, 0.07),
        "period_margin_mean": float(np.mean(confidence)) if len(confidence) else math.nan,
        "period_margin_median": float(np.median(confidence)) if len(confidence) else math.nan,
        "period_margin_q10": float(np.quantile(confidence, 0.1)) if len(confidence) else math.nan,
        "period_margin_q90": float(np.quantile(confidence, 0.9)) if len(confidence) else math.nan,
        "low_margin_fraction": float(np.mean(confidence < 0.2)) if len(confidence) else math.nan,
        "high_margin_fraction": float(np.mean(confidence > 0.8)) if len(confidence) else math.nan,
        "edge_coefficient_median": float(np.median([row["edge_coefficient"] for row in edge_rows])) if edge_rows else math.nan,
        "edge_coefficient_q10": float(np.quantile([row["edge_coefficient"] for row in edge_rows], 0.1)) if edge_rows else math.nan,
        "edge_coefficient_q90": float(np.quantile([row["edge_coefficient"] for row in edge_rows], 0.9)) if edge_rows else math.nan,
        "direct_beat_fmeasure": direct_metrics["beat_fmeasure"],
        "direct_beat_cmlt": direct_metrics["beat_cmlt"],
        "direct_beat_amlt": direct_metrics["beat_amlt"],
        "casm_beat_fmeasure": full_metrics["beat_fmeasure"],
        "casm_beat_cmlt": full_metrics["beat_cmlt"],
        "casm_beat_amlt": full_metrics["beat_amlt"],
    }
    summary["delta_fmeasure"] = summary["casm_beat_fmeasure"] - summary["direct_beat_fmeasure"]
    summary["delta_cmlt"] = summary["casm_beat_cmlt"] - summary["direct_beat_cmlt"]
    summary["delta_amlt"] = summary["casm_beat_amlt"] - summary["direct_beat_amlt"]
    return summary, candidate_rows, edge_rows


def export_mechanism(panels: dict[str, list[Path]], frozen: dict[str, object], output: Path) -> None:
    summary_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    edge_rows: list[dict[str, object]] = []
    for panel, paths in panels.items():
        for index, path in enumerate(paths, 1):
            summary, candidates, edges = casm_trace(path, frozen)
            summary["panel"] = panel
            for row in candidates:
                row["panel"] = panel
            for row in edges:
                row["panel"] = panel
            summary_rows.append(summary)
            candidate_rows.extend(candidates)
            edge_rows.extend(edges)
        print(f"TRACE {panel} n={len(paths)}", flush=True)
    pd.DataFrame(summary_rows).to_csv(output / "mechanism_piece_summary.csv", index=False)
    pd.DataFrame(candidate_rows).to_csv(
        output / "mechanism_candidates.csv.gz", index=False, compression="gzip"
    )
    pd.DataFrame(edge_rows).to_csv(
        output / "mechanism_edges.csv.gz", index=False, compression="gzip"
    )


def export_representatives(output: Path, frozen: dict[str, object]) -> None:
    summary = pd.read_csv(output / "mechanism_piece_summary.csv")
    choices: list[dict[str, object]] = []
    for panel in ("bt_smc_oof", "bt_gtzan_seed0"):
        group = summary[(summary.panel == panel) & (~summary.beat_fallback)].copy()
        group["gain_score"] = group.delta_cmlt + 0.5 * group.delta_fmeasure
        improvement = group[group.delta_fmeasure > -0.03].sort_values("gain_score").iloc[-1]
        failure = group.sort_values("delta_fmeasure").iloc[0]
        ambiguous = group.sort_values("period_margin_median").iloc[0]
        clear = group.sort_values("period_margin_median").iloc[-1]
        for role, row in (
            ("improvement", improvement),
            ("failure", failure),
            ("ambiguous", ambiguous),
            ("clear", clear),
        ):
            choices.append(
                {
                    "panel": panel,
                    "role": role,
                    "piece": row.piece,
                    "source_path": row.source_path,
                    "delta_fmeasure": row.delta_fmeasure,
                    "delta_cmlt": row.delta_cmlt,
                    "period_margin_median": row.period_margin_median,
                }
            )

    traces_dir = output / "representative_traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    for choice in choices:
        path = Path(str(choice["source_path"]))
        item = load_cache_item(path)
        decoder = CASMDecoder(**normalized_frozen(frozen))
        logits = np.asarray(item["beat_logits"], dtype=float)
        probabilities = expit(logits)
        candidates = _edge_local_maxima(probabilities)
        candidates = candidates[probabilities[candidates] >= decoder.candidate_threshold]
        periods, confidence = decoder._estimate_local_tempo(probabilities, candidates)
        structured = decoder._decode_beats(logits, candidates, periods, confidence)
        direct, _ = MinimalDecoder(fps=decoder.fps).decode(
            item["beat_logits"], item["downbeat_logits"]
        )
        casm, _ = decoder.decode(item["beat_logits"], item["downbeat_logits"])
        dbn_default, _ = make_decoder("dbn_default", frozen).decode(
            item["beat_logits"], item["downbeat_logits"]
        )
        dbn_matched, _ = make_decoder("dbn_matched_30_300", frozen).decode(
            item["beat_logits"], item["downbeat_logits"]
        )
        try:
            plpdp, _ = make_decoder("plpdp", frozen).decode(
                item["beat_logits"], item["downbeat_logits"]
            )
        except Exception:
            plpdp = np.empty(0)
        slug = f"{choice['panel']}__{choice['role']}"
        np.savez_compressed(
            traces_dir / f"{slug}.npz",
            piece=np.asarray(item["piece"]),
            panel=np.asarray(choice["panel"]),
            role=np.asarray(choice["role"]),
            fps=np.asarray(decoder.fps),
            beat_logits=logits,
            beat_prob=probabilities,
            truth_beat=item["truth_beat"],
            candidates=candidates,
            periods=periods,
            confidence=confidence,
            structured_beat=structured / decoder.fps,
            direct_beat=direct,
            casm_beat=casm,
            dbn_default_beat=dbn_default,
            dbn_matched_beat=dbn_matched,
            plpdp_beat=plpdp,
        )
    write_json(output / "representatives.json", choices)


def aggregate(output: Path) -> None:
    paths = sorted((output / "raw").glob("*.pieces.csv"))
    table = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    table.to_csv(output / "all_piece_metrics.csv.gz", index=False, compression="gzip")
    metric_columns = [
        "beat_fmeasure",
        "beat_cmlt",
        "beat_amlt",
        "downbeat_fmeasure",
        "downbeat_cmlt",
        "downbeat_amlt",
    ]
    summary_rows = []
    for (panel, method), group in table.groupby(["panel", "method"], sort=True):
        row: dict[str, object] = {
            "panel": panel,
            "panel_label": PANEL_LABELS[panel],
            "method": method,
            "method_label": METHOD_LABELS[method],
            "piece_count": len(group),
        }
        for metric in metric_columns:
            row[metric] = float(group[metric].mean())
        summary_rows.append(row)
    pd.DataFrame(summary_rows).to_csv(output / "aggregate_metrics.csv", index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frozen-params", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--methods", nargs="*", choices=METHODS, default=list(METHODS))
    parser.add_argument("--skip-mechanism", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = args.project_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    payload = json.loads(args.frozen_params.read_text())
    frozen = payload.get("parameters", payload)
    panels = panel_paths(project)
    write_json(
        output / "protocol.json",
        {
            "created_at_unix": time.time(),
            "project_root": str(project),
            "frozen_parameters": frozen,
            "frozen_parameter_sha256": hashlib.sha256(canonical_json(frozen).encode()).hexdigest(),
            "methods": args.methods,
            "method_labels": METHOD_LABELS,
            "panels": {name: {"label": PANEL_LABELS[name], "piece_count": len(paths)} for name, paths in panels.items()},
            "trim_seconds": 5.0,
            "workers": args.workers,
            "script_sha256": sha256_file(Path(__file__)),
        },
    )
    for method in args.methods:
        for panel, paths in panels.items():
            run_panel_method(method, panel, paths, frozen, output, args.workers)
    aggregate(output)
    if not args.skip_mechanism:
        export_mechanism(panels, frozen, output)
        export_representatives(output, frozen)
    (output / "COMPLETE").touch()
    print(f"COMPLETE {output}", flush=True)


if __name__ == "__main__":
    main()
