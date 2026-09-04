#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from scipy.special import expit

from scripts.evaluate_semicrf import decode_piece as decode_semicrf_piece
from structbeat.decoders import _edge_local_maxima, build_decoder
from structbeat.evaluation import beat_metrics, load_cache_item
from structbeat.semicrf import SemiCRFConfig, TransformerSemiCRF


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export one real held-out activation sequence with Direct, fixed-prior "
            "Semi-Markov, DBN, CASM, and learned Semi-CRF outputs."
        )
    )
    parser.add_argument("cache", type=Path)
    parser.add_argument("--semicrf-checkpoint", type=Path)
    parser.add_argument("--model-label", default="Beat This")
    parser.add_argument("--fold-label", default="fold 0")
    parser.add_argument("--fps", type=float, default=50.0)
    parser.add_argument("--trim-seconds", type=float, default=5.0)
    parser.add_argument("--window-seconds", type=float, default=16.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def rounded(values: np.ndarray, digits: int = 5) -> list[float]:
    return np.round(np.asarray(values, dtype=float), digits).tolist()


def global_period_frames(
    probability: np.ndarray,
    fps: float,
    min_bpm: float = 30.0,
    max_bpm: float = 300.0,
    tempo_bias: float = 0.15,
) -> tuple[int, list[dict[str, float]]]:
    """Estimate one track-level period from the frozen activation only."""
    minimum = max(2, int(np.ceil(fps * 60.0 / max_bpm)))
    maximum = min(len(probability) - 1, int(np.floor(fps * 60.0 / min_bpm)))
    rows: list[tuple[int, float]] = []
    for lag in range(minimum, maximum + 1):
        left = probability[:-lag]
        right = probability[lag:]
        denominator = np.sqrt(np.dot(left, left) * np.dot(right, right)) + 1e-8
        score = float(np.dot(left, right) / denominator)
        score *= (minimum / lag) ** tempo_bias
        rows.append((lag, score))
    ranked = sorted(rows, key=lambda row: row[1], reverse=True)
    period = ranked[0][0]
    hypotheses = [
        {
            "period_frames": int(lag),
            "period_seconds": round(lag / fps, 5),
            "bpm": round(60.0 * fps / lag, 3),
            "score": round(score, 6),
        }
        for lag, score in ranked[:5]
    ]
    return period, hypotheses


@dataclass
class FixedPriorSemiMarkov:
    fps: float = 50.0

    def decode(
        self, beat_logits: np.ndarray, downbeat_logits: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        probability = expit(np.asarray(beat_logits, dtype=np.float64))
        candidates = _edge_local_maxima(probability)
        candidates = candidates[probability[candidates] >= 0.03]
        if not len(candidates):
            return np.empty(0), np.empty(0)
        period, _ = global_period_frames(probability, self.fps)
        minimum = int(np.ceil(self.fps * 60.0 / 300.0))
        maximum = int(np.floor(self.fps * 60.0 / 30.0))
        node = np.clip(beat_logits[candidates] / 2.0, -6.0, 6.0)
        score = np.full(len(candidates), -np.inf, dtype=float)
        previous = np.full(len(candidates), -1, dtype=int)

        # A conventional fixed-prior replay: one track-level duration model and
        # one complete Viterbi path spanning the activation sequence.
        for end in range(len(candidates)):
            if candidates[end] <= maximum:
                score[end] = node[end]
            starts = np.arange(end)
            intervals = candidates[end] - candidates[starts]
            valid = (
                (intervals >= minimum)
                & (intervals <= maximum)
                & np.isfinite(score[starts])
            )
            if not np.any(valid):
                continue
            starts = starts[valid]
            intervals = intervals[valid].astype(float)
            log_error = np.log(np.maximum(intervals, 1.0) / period)
            duration_cost = 12.0 * 0.5 * (log_error / 0.15) ** 2
            values = score[starts] + node[end] - duration_cost
            offset = int(np.argmax(values))
            if values[offset] > score[end]:
                score[end] = values[offset]
                previous[end] = int(starts[offset])

        terminal = np.flatnonzero(
            (candidates >= max(0, len(beat_logits) - 1 - maximum))
            & np.isfinite(score)
        )
        if not len(terminal):
            return np.empty(0), np.empty(0)
        end = int(terminal[np.argmax(score[terminal])])
        path: list[int] = []
        while end >= 0:
            path.append(end)
            end = int(previous[end])
        beats = candidates[np.asarray(path[::-1], dtype=int)]
        return beats / self.fps, np.empty(0)


def score_events(
    truth: np.ndarray,
    predicted: np.ndarray,
    trim_seconds: float,
) -> dict[str, float | int]:
    metrics = beat_metrics(truth, predicted, trim_seconds)
    return {
        "fmeasure": round(float(metrics["fmeasure"]), 5),
        "cmlt": round(float(metrics["cmlt"]), 5),
        "amlt": round(float(metrics["amlt"]), 5),
        "event_count": int(len(predicted)),
    }


def best_window_start(
    truth: np.ndarray,
    outputs: dict[str, np.ndarray],
    duration: float,
    window_seconds: float,
    fps: float,
) -> float:
    frame_count = max(1, int(np.ceil(duration * fps)))
    evidence = np.zeros(frame_count, dtype=float)
    truth_mask = np.zeros(frame_count, dtype=bool)
    truth_frames = np.clip(np.rint(truth * fps).astype(int), 0, frame_count - 1)
    truth_mask[truth_frames] = True
    masks: dict[str, np.ndarray] = {}
    for name, events in outputs.items():
        mask = np.zeros(frame_count, dtype=bool)
        frames = np.clip(np.rint(events * fps).astype(int), 0, frame_count - 1)
        mask[frames] = True
        masks[name] = mask

    tolerance = max(1, int(round(0.07 * fps)))
    kernel = np.ones(2 * tolerance + 1, dtype=int)
    truth_near = np.convolve(truth_mask.astype(int), kernel, mode="same") > 0
    direct_near = np.convolve(masks["direct"].astype(int), kernel, mode="same") > 0
    fixed_near = np.convolve(
        masks["fixed_semimarkov"].astype(int), kernel, mode="same"
    ) > 0
    dbn_near = np.convolve(masks["dbn"].astype(int), kernel, mode="same") > 0
    casm_near = np.convolve(masks["casm"].astype(int), kernel, mode="same") > 0
    evidence += 2.0 * (truth_mask & ~direct_near & casm_near)
    evidence += 2.6 * (truth_mask & ~fixed_near & casm_near)
    evidence += 2.2 * (truth_mask & ~dbn_near & casm_near)
    evidence += 1.2 * (masks["fixed_semimarkov"] & ~truth_near & ~casm_near)
    evidence += 0.9 * (masks["dbn"] & ~truth_near & ~casm_near)
    if "semicrf" in masks:
        semicrf_near = (
            np.convolve(masks["semicrf"].astype(int), kernel, mode="same") > 0
        )
        evidence += 1.4 * (truth_mask & ~direct_near & semicrf_near)
    evidence += 0.6 * (masks["dbn"] & ~truth_near)
    stack = np.stack(list(masks.values()), axis=0)
    evidence += 0.25 * (stack.any(axis=0) & ~stack.all(axis=0))

    width = max(1, int(round(window_seconds * fps)))
    if width >= frame_count:
        return 0.0
    score = np.convolve(evidence, np.ones(width), mode="valid")
    floor = min(len(score) - 1, max(0, int(round(5.0 * fps))))
    return round((floor + int(np.argmax(score[floor:]))) / fps, 3)


def main() -> None:
    args = parse_args()
    item = load_cache_item(args.cache)
    beat_logits = np.asarray(item["beat_logits"], dtype=np.float64)
    downbeat_logits = np.asarray(item["downbeat_logits"], dtype=np.float64)
    truth_beat = np.asarray(item["truth_beat"], dtype=float)
    truth_downbeat = np.asarray(item["truth_downbeat"], dtype=float)

    checkpoint = None
    semicrf_beats = np.empty(0)
    semicrf_downbeats = np.empty(0)
    if args.semicrf_checkpoint is not None:
        checkpoint = torch.load(
            args.semicrf_checkpoint, map_location="cpu", weights_only=False
        )
        semicrf_config = SemiCRFConfig(**checkpoint["config"])
        semicrf = TransformerSemiCRF(semicrf_config)
        semicrf.load_state_dict(checkpoint["model_state"])
        semicrf.eval()
        semicrf_beats, semicrf_downbeats = decode_semicrf_piece(
            semicrf,
            beat_logits,
            downbeat_logits,
            torch.device("cpu"),
            window_frames=1500,
            margin_frames=250,
        )

    decoders = {
        "direct": build_decoder("minimal", fps=args.fps),
        "fixed_semimarkov": FixedPriorSemiMarkov(fps=args.fps),
        "dbn": build_decoder("dbn", fps=args.fps),
        "casm": build_decoder("casm", fps=args.fps),
    }
    beat_outputs: dict[str, np.ndarray] = {}
    downbeat_outputs: dict[str, np.ndarray] = {}
    for name, decoder in decoders.items():
        beat_outputs[name], downbeat_outputs[name] = decoder.decode(
            beat_logits, downbeat_logits
        )
    if checkpoint is not None:
        beat_outputs["semicrf"] = semicrf_beats
        downbeat_outputs["semicrf"] = semicrf_downbeats

    probability = expit(beat_logits)
    fixed_period, hypotheses = global_period_frames(
        probability, args.fps
    )
    casm_decoder = decoders["casm"]
    casm_candidates = _edge_local_maxima(probability)
    casm_candidates = casm_candidates[
        probability[casm_candidates] >= casm_decoder.candidate_threshold
    ]
    casm_periods, casm_confidence = casm_decoder._estimate_local_tempo(
        probability, casm_candidates
    )
    duration = len(beat_logits) / args.fps
    payload = {
        "piece": item["piece"],
        "dataset": item["dataset"],
        "front_end": args.model_label,
        "protocol": {
            "fold": args.fold_label,
            "role": "held-out test piece",
            "trim_seconds": args.trim_seconds,
            "semicrf_checkpoint_epoch": (
                int(checkpoint["epoch"]) if checkpoint is not None else None
            ),
        },
        "fps": args.fps,
        "duration_seconds": round(duration, 3),
        "window_seconds": args.window_seconds,
        "beat_probability": rounded(probability),
        "downbeat_probability": rounded(expit(downbeat_logits)),
        "truth": {
            "beat_times": rounded(truth_beat, 4),
            "downbeat_times": rounded(truth_downbeat, 4),
        },
        "decoders": {},
        "fixed_semimarkov": {
            "period_frames": fixed_period,
            "period_seconds": round(fixed_period / args.fps, 5),
            "bpm": round(60.0 * args.fps / fixed_period, 3),
            "top_global_hypotheses": hypotheses,
            "provenance": (
                "Mechanism replay on the held-out activation: one global period "
                "is estimated from the full activation, then held fixed."
            ),
        },
        "casm_analysis": {
            "candidate_times": rounded(casm_candidates / args.fps, 4),
            "period_seconds": rounded(casm_periods / args.fps, 5),
            "tempo_bpm": rounded(60.0 * args.fps / casm_periods, 3),
            "reliability_proxy": rounded(casm_confidence, 5),
            "local_window_seconds": float(casm_decoder.local_window_seconds),
            "provenance": (
                "Direct trace of the frozen CASM local comb-bank estimator; "
                "reliability is the best-versus-alternative period-score margin."
            ),
        },
    }
    for name, beats in beat_outputs.items():
        downbeats = downbeat_outputs[name]
        downbeat_metrics = None
        if len(truth_downbeat) and len(downbeats):
            downbeat_metrics = score_events(
                truth_downbeat, downbeats, args.trim_seconds
            )
        payload["decoders"][name] = {
            "beat_times": rounded(beats, 4),
            "downbeat_times": rounded(downbeats, 4),
            "beat_metrics": score_events(
                truth_beat, beats, args.trim_seconds
            ),
            "downbeat_metrics": downbeat_metrics,
        }
    payload["recommended_window_start"] = best_window_start(
        truth_beat,
        beat_outputs,
        duration,
        args.window_seconds,
        args.fps,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(args.output)
    print(
        json.dumps(
            {
                "piece": payload["piece"],
                "window_start": payload["recommended_window_start"],
                "fixed_bpm": payload["fixed_semimarkov"]["bpm"],
                "metrics": {
                    name: row["beat_metrics"]
                    for name, row in payload["decoders"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
