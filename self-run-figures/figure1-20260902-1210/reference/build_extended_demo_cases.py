#!/usr/bin/env python3
"""Build the five frozen demo payloads from archived activation caches.

The two SMC payloads retain their finalized Direct, fixed Semi-Markov, DBN,
and CASM traces and only add PLPDP. The three GTZAN payloads are decoded from
the archived Beat This final0 caches with the locked Frozen-4F CASM parameters.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.special import expit


FROZEN_4F = {
    "fps": 50.0,
    "candidate_threshold": 0.03,
    "min_bpm": 30.0,
    "max_bpm": 300.0,
    "local_window_seconds": 8.0,
    "temperature": 2.0,
    "logit_clip": 6.0,
    "duration_weight": 4.0,
    "duration_sigma": 0.12,
    "uncertain_sigma": 0.4,
    "tempo_bias": 0.15,
    "fallback_minimal_ratio": 0.85,
    "fallback_maximal_ratio": 1.8,
    "downbeat_mode": "meter",
    "meters": (2, 3, 4, 5, 6, 7),
    "meter_change_penalty": 3.0,
    "downbeat_temperature": 4.0,
    "bar_reward": 0.0,
    "downbeat_agreement_threshold": 0.6,
    "downbeat_agreement_tolerance": 0.07,
}

DECODER_SOURCE_SHA256 = "f66e7dfb09b208882749fe6d212d8363b28b7a2da397b4ba297b93df1825eaed"

GTZAN_CASES = (
    ("gtzan_blues_00023", "gtzan/gtzan_blues_00023/track.npy"),
    ("gtzan_metal_00026", "gtzan/gtzan_metal_00026/track.npy"),
    ("gtzan_pop_00053", "gtzan/gtzan_pop_00053/track.npy"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--structbeat-root",
        type=Path,
        required=True,
        help="auto_structbeat checkout containing structbeat/ and third_party/.",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
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
    minimum = max(2, int(np.ceil(fps * 60.0 / max_bpm)))
    maximum = min(len(probability) - 1, int(np.floor(fps * 60.0 / min_bpm)))
    rows: list[tuple[int, float]] = []
    for lag in range(minimum, maximum + 1):
        left = probability[:-lag]
        right = probability[lag:]
        denominator = np.sqrt(np.dot(left, left) * np.dot(right, right)) + 1e-8
        score = float(np.dot(left, right) / denominator)
        rows.append((lag, score * (minimum / lag) ** tempo_bias))
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
    edge_local_maxima: object
    fps: float = 50.0

    def decode(
        self, beat_logits: np.ndarray, downbeat_logits: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        del downbeat_logits
        probability = expit(np.asarray(beat_logits, dtype=np.float64))
        candidates = self.edge_local_maxima(probability)
        candidates = candidates[probability[candidates] >= 0.03]
        if not len(candidates):
            return np.empty(0), np.empty(0)
        period, _ = global_period_frames(probability, self.fps)
        minimum = int(np.ceil(self.fps * 60.0 / 300.0))
        maximum = int(np.floor(self.fps * 60.0 / 30.0))
        node = np.clip(beat_logits[candidates] / 2.0, -6.0, 6.0)
        score = np.full(len(candidates), -np.inf, dtype=float)
        previous = np.full(len(candidates), -1, dtype=int)
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
            values = score[starts] + node[end] - 12.0 * 0.5 * (log_error / 0.15) ** 2
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
        return candidates[np.asarray(path[::-1], dtype=int)] / self.fps, np.empty(0)


def score_events(beat_metrics, truth, predicted, trim_seconds=5.0):
    if not len(truth) or not len(predicted):
        return None
    metrics = beat_metrics(np.asarray(truth), np.asarray(predicted), trim_seconds)
    return {
        "fmeasure": round(float(metrics["fmeasure"]), 5),
        "cmlt": round(float(metrics["cmlt"]), 5),
        "amlt": round(float(metrics["amlt"]), 5),
        "event_count": int(len(predicted)),
    }


def near_mask(events: np.ndarray, frames: int, fps: float, tolerance=0.07):
    mask = np.zeros(frames, dtype=bool)
    indices = np.clip(np.rint(np.asarray(events) * fps).astype(int), 0, frames - 1)
    mask[indices] = True
    width = max(1, int(round(tolerance * fps)))
    return np.convolve(mask.astype(int), np.ones(2 * width + 1), mode="same") > 0


def best_window_start(truth, outputs, duration, window_seconds, fps):
    frames = max(1, int(np.ceil(duration * fps)))
    truth_mask = np.zeros(frames, dtype=bool)
    truth_indices = np.clip(np.rint(np.asarray(truth) * fps).astype(int), 0, frames - 1)
    truth_mask[truth_indices] = True
    truth_near = near_mask(truth, frames, fps)
    casm_near = near_mask(outputs["casm"], frames, fps)
    evidence = np.zeros(frames, dtype=float)
    weights = {"direct": 1.8, "fixed_semimarkov": 2.0, "dbn": 2.2, "plpdp": 2.4}
    for method, weight in weights.items():
        method_near = near_mask(outputs[method], frames, fps)
        evidence += weight * (truth_mask & casm_near & ~method_near)
        method_mask = np.zeros(frames, dtype=bool)
        method_indices = np.clip(
            np.rint(np.asarray(outputs[method]) * fps).astype(int), 0, frames - 1
        )
        method_mask[method_indices] = True
        evidence += 0.45 * (method_mask & ~truth_near & ~casm_near)
    width = max(1, int(round(window_seconds * fps)))
    if width >= frames:
        return 0.0
    scores = np.convolve(evidence, np.ones(width), mode="valid")
    floor = min(len(scores) - 1, max(0, int(round(3.0 * fps))))
    return round((floor + int(np.argmax(scores[floor:]))) / fps, 3)


def decoder_payload(beat_metrics, truth_beat, truth_downbeat, beats, downbeats):
    return {
        "beat_times": rounded(beats, 4),
        "downbeat_times": rounded(downbeats, 4),
        "beat_metrics": score_events(beat_metrics, truth_beat, beats),
        "downbeat_metrics": score_events(beat_metrics, truth_downbeat, downbeats),
    }


def add_plpdp_to_smc(bundle_root, PLPDPDecoder, load_cache_item, beat_metrics):
    for stem in ("smc_117", "smc_221"):
        cache = bundle_root / "data" / "raw_cache" / f"{stem}_beat_this_oof.npz"
        payload_path = bundle_root / "data" / "figure_payloads" / f"{stem}.json"
        item = load_cache_item(cache)
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        beats, downbeats = PLPDPDecoder(
            fps=50.0, min_bpm=30, max_bpm=300
        ).decode(item["beat_logits"], item["downbeat_logits"])
        payload["decoders"]["plpdp"] = decoder_payload(
            beat_metrics,
            item["truth_beat"],
            item["truth_downbeat"],
            beats,
            downbeats,
        )
        payload["plpdp_configuration"] = {
            "implementation": "SunnyCYC/plpdp4beat released code",
            "source": "https://github.com/SunnyCYC/plpdp4beat",
            "decoder_source_sha256": DECODER_SOURCE_SHA256,
            "min_bpm": 30,
            "max_bpm": 300,
            "input_fps": 50.0,
            "algorithm_fps": 100,
            "combine_downbeats": True,
        }
        payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_gtzan(
    bundle_root,
    CASMDecoder,
    DBNDecoder,
    MinimalDecoder,
    PLPDPDecoder,
    edge_local_maxima,
    load_cache_item,
    beat_metrics,
):
    for stem, expected_piece in GTZAN_CASES:
        cache = bundle_root / "data" / "raw_cache" / f"{stem}_beat_this_final0.npz"
        item = load_cache_item(cache)
        assert item["piece"] == expected_piece
        beat_logits = np.asarray(item["beat_logits"], dtype=np.float64)
        downbeat_logits = np.asarray(item["downbeat_logits"], dtype=np.float64)
        truth_beat = np.asarray(item["truth_beat"], dtype=float)
        truth_downbeat = np.asarray(item["truth_downbeat"], dtype=float)
        decoders = {
            "direct": MinimalDecoder(fps=50.0),
            "fixed_semimarkov": FixedPriorSemiMarkov(edge_local_maxima, fps=50.0),
            "dbn": DBNDecoder(fps=50.0, min_bpm=30.0, max_bpm=300.0),
            "plpdp": PLPDPDecoder(fps=50.0, min_bpm=30, max_bpm=300),
            "casm": CASMDecoder(**FROZEN_4F),
        }
        beat_outputs = {}
        downbeat_outputs = {}
        for name, decoder in decoders.items():
            beat_outputs[name], downbeat_outputs[name] = decoder.decode(
                beat_logits, downbeat_logits
            )
        probability = expit(beat_logits)
        fixed_period, hypotheses = global_period_frames(probability, 50.0)
        casm_decoder = decoders["casm"]
        candidates = edge_local_maxima(probability)
        candidates = candidates[probability[candidates] >= casm_decoder.candidate_threshold]
        periods, confidence = casm_decoder._estimate_local_tempo(probability, candidates)
        duration = len(beat_logits) / 50.0
        payload = {
            "piece": item["piece"],
            "dataset": "gtzan",
            "front_end": "Beat This",
            "protocol": {
                "fold": "final0",
                "role": "clean held-out GTZAN test piece",
                "trim_seconds": 5.0,
                "semicrf_checkpoint_epoch": None,
            },
            "fps": 50.0,
            "duration_seconds": round(duration, 3),
            "window_seconds": 18.0,
            "beat_probability": rounded(probability),
            "downbeat_probability": rounded(expit(downbeat_logits)),
            "truth": {
                "beat_times": rounded(truth_beat, 4),
                "downbeat_times": rounded(truth_downbeat, 4),
            },
            "decoders": {
                name: decoder_payload(
                    beat_metrics,
                    truth_beat,
                    truth_downbeat,
                    beat_outputs[name],
                    downbeat_outputs[name],
                )
                for name in decoders
            },
            "fixed_semimarkov": {
                "period_frames": fixed_period,
                "period_seconds": round(fixed_period / 50.0, 5),
                "bpm": round(3000.0 / fixed_period, 3),
                "top_global_hypotheses": hypotheses,
                "provenance": "One global activation-derived period held fixed for the track.",
            },
            "casm_analysis": {
                "candidate_times": rounded(candidates / 50.0, 4),
                "period_seconds": rounded(periods / 50.0, 5),
                "tempo_bpm": rounded(3000.0 / periods, 3),
                "reliability_proxy": rounded(confidence, 5),
                "local_window_seconds": 8.0,
                "provenance": "Locked Frozen-4F CASM local period and reliability traces.",
            },
            "casm_configuration": {
                "label": "Frozen-4F",
                "parameters": {**FROZEN_4F, "meters": list(FROZEN_4F["meters"])},
                "parameter_sha256": "251c96b23223b2e4ddef7f4ab85592663a1c27fcd6d62b1a5d1ef5625ed01f71",
            },
            "dbn_configuration": {
                "label": "matched 30-300 BPM DBN",
                "parameters": {
                    "min_bpm": 30.0,
                    "max_bpm": 300.0,
                    "transition_lambda": 100.0,
                    "observation_lambda": 16.0,
                    "threshold": 0.05,
                },
            },
            "plpdp_configuration": {
                "implementation": "SunnyCYC/plpdp4beat released code",
                "source": "https://github.com/SunnyCYC/plpdp4beat",
                "decoder_source_sha256": DECODER_SOURCE_SHA256,
                "min_bpm": 30,
                "max_bpm": 300,
                "input_fps": 50.0,
                "algorithm_fps": 100,
                "combine_downbeats": True,
            },
        }
        payload["recommended_window_start"] = best_window_start(
            truth_beat, beat_outputs, duration, 18.0, 50.0
        )
        output = bundle_root / "data" / "figure_payloads" / f"{stem}.json"
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(output, payload["recommended_window_start"])


def main() -> None:
    args = parse_args()
    sys.path.insert(0, str(args.structbeat_root))
    from structbeat.decoders import (  # noqa: PLC0415
        CASMDecoder,
        DBNDecoder,
        MinimalDecoder,
        PLPDPDecoder,
        _edge_local_maxima,
    )
    from structbeat.evaluation import beat_metrics, load_cache_item  # noqa: PLC0415

    add_plpdp_to_smc(
        args.bundle_root, PLPDPDecoder, load_cache_item, beat_metrics
    )
    build_gtzan(
        args.bundle_root,
        CASMDecoder,
        DBNDecoder,
        MinimalDecoder,
        PLPDPDecoder,
        _edge_local_maxima,
        load_cache_item,
        beat_metrics,
    )


if __name__ == "__main__":
    main()
