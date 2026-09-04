#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from itertools import product
from pathlib import Path

import numpy as np

from structbeat.evaluation import beat_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep one shared, illustration-only DBN configuration over the "
            "three real decoder cases and export adjusted visualization payloads."
        )
    )
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--trim-seconds", type=float, default=5.0)
    parser.add_argument("--apply-config-index", type=int)
    return parser.parse_args()


def decode_dbn(
    payload: dict[str, object], parameters: dict[str, float]
) -> tuple[np.ndarray, np.ndarray]:
    from madmom.features.downbeats import DBNDownBeatTrackingProcessor

    epsilon = 1e-5
    beat_probability = np.asarray(payload["beat_probability"], dtype=np.float64)
    downbeat_probability = np.asarray(
        payload["downbeat_probability"], dtype=np.float64
    )
    beat_probability = beat_probability * (1 - epsilon) + epsilon / 2
    downbeat_probability = downbeat_probability * (1 - epsilon) + epsilon / 2
    activations = np.column_stack(
        (
            np.maximum(beat_probability - downbeat_probability, epsilon / 2),
            downbeat_probability,
        )
    )
    processor = DBNDownBeatTrackingProcessor(
        beats_per_bar=[3, 4],
        fps=float(payload["fps"]),
        min_bpm=parameters["min_bpm"],
        max_bpm=parameters["max_bpm"],
        transition_lambda=parameters["transition_lambda"],
        observation_lambda=parameters["observation_lambda"],
        threshold=parameters["threshold"],
    )
    output = processor(activations)
    if not len(output):
        return np.empty(0), np.empty(0)
    return output[:, 0], output[output[:, 1] == 1, 0]


def metrics(
    truth: list[float], predicted: np.ndarray, trim_seconds: float
) -> dict[str, float | int]:
    values = beat_metrics(
        np.asarray(truth, dtype=float), predicted, trim_seconds
    )
    return {
        "fmeasure": float(values["fmeasure"]),
        "cmlt": float(values["cmlt"]),
        "amlt": float(values["amlt"]),
        "event_count": int(len(predicted)),
    }


def rounded_metrics(values: dict[str, float | int]) -> dict[str, float | int]:
    return {
        key: round(value, 5) if isinstance(value, float) else value
        for key, value in values.items()
    }


def parameter_grid() -> list[dict[str, float]]:
    rows = []
    for minimum, maximum, transition, observation, threshold in product(
        (25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0),
        (160.0, 180.0, 215.0),
        (25.0, 50.0, 75.0, 100.0),
        (8.0, 16.0),
        (0.03, 0.05),
    ):
        if minimum >= maximum:
            continue
        rows.append(
            {
                "min_bpm": minimum,
                "max_bpm": maximum,
                "transition_lambda": transition,
                "observation_lambda": observation,
                "threshold": threshold,
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    payloads = [(path, json.loads(path.read_text())) for path in args.input]
    args.output_root.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, object]] = []
    aggregate_rows: list[dict[str, object]] = []
    decoded: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
    configurations = parameter_grid()
    configuration_items = list(enumerate(configurations))
    if args.apply_config_index is not None:
        if not 0 <= args.apply_config_index < len(configurations):
            raise ValueError("apply-config-index is outside the parameter grid")
        configuration_items = [
            (args.apply_config_index, configurations[args.apply_config_index])
        ]
    for config_index, parameters in configuration_items:
        case_scores = []
        for case_index, (path, payload) in enumerate(payloads):
            beats, downbeats = decode_dbn(payload, parameters)
            decoded[(config_index, case_index)] = (beats, downbeats)
            beat = metrics(
                payload["truth"]["beat_times"], beats, args.trim_seconds
            )
            downbeat = metrics(
                payload["truth"]["downbeat_times"],
                downbeats,
                args.trim_seconds,
            )
            case_score = 0.5 * (beat["fmeasure"] + beat["cmlt"])
            case_scores.append(case_score)
            all_rows.append(
                {
                    "config_index": config_index,
                    "case": path.stem,
                    **parameters,
                    "beat_fmeasure": beat["fmeasure"],
                    "beat_cmlt": beat["cmlt"],
                    "beat_amlt": beat["amlt"],
                    "beat_event_count": beat["event_count"],
                    "downbeat_fmeasure": downbeat["fmeasure"],
                    "downbeat_cmlt": downbeat["cmlt"],
                    "downbeat_amlt": downbeat["amlt"],
                    "downbeat_event_count": downbeat["event_count"],
                    "selection_score": case_score,
                }
            )
        aggregate_rows.append(
            {
                "config_index": config_index,
                **parameters,
                "macro_selection_score": float(np.mean(case_scores)),
                "minimum_case_score": float(np.min(case_scores)),
            }
        )

    aggregate_rows.sort(
        key=lambda row: (
            row["minimum_case_score"], row["macro_selection_score"]
        ),
        reverse=True,
    )
    selected = aggregate_rows[0]
    selected_index = int(selected["config_index"])
    selected_parameters = {
        key: selected[key]
        for key in (
            "min_bpm",
            "max_bpm",
            "transition_lambda",
            "observation_lambda",
            "threshold",
        )
    }

    with (args.output_root / "per_case.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    with (args.output_root / "aggregate.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(aggregate_rows[0]))
        writer.writeheader()
        writer.writerows(aggregate_rows)

    selected_cases = []
    for case_index, (path, payload) in enumerate(payloads):
        beats, downbeats = decoded[(selected_index, case_index)]
        beat = rounded_metrics(
            metrics(payload["truth"]["beat_times"], beats, args.trim_seconds)
        )
        downbeat = rounded_metrics(
            metrics(
                payload["truth"]["downbeat_times"],
                downbeats,
                args.trim_seconds,
            )
        )
        original = payload["decoders"].get(
            "dbn_original", payload["decoders"]["dbn"]
        )
        payload["decoders"]["dbn_original"] = original
        payload["decoders"]["dbn"] = {
            "beat_times": np.round(beats, 5).tolist(),
            "downbeat_times": np.round(downbeats, 5).tolist(),
            "beat_metrics": beat,
            "downbeat_metrics": downbeat,
        }
        payload["dbn_tuning"] = {
            "label": "shared illustration-tuned DBN",
            "parameters": selected_parameters,
            "selection_scope": [item[0].stem for item in payloads],
            "selection_objective": "macro mean of 0.5 * (beat F1 + beat CMLt)",
            "evaluation_warning": (
                "Selected using these three displayed pieces only; use for "
                "mechanism visualization, never as an aggregate benchmark."
            ),
        }
        output_path = args.output_root / path.name
        output_path.write_text(json.dumps(payload, indent=2) + "\n")
        selected_cases.append(
            {
                "case": path.stem,
                "beat": beat,
                "downbeat": downbeat,
                "original_beat": original["beat_metrics"],
                "original_downbeat": original["downbeat_metrics"],
            }
        )

    summary = {
        "grid_size": len(configurations),
        "evaluated_config_count": len(configuration_items),
        "selection_rule": "maximin case score, then macro score",
        "selection_scope": [item[0].stem for item in payloads],
        "selection_objective": "macro mean of 0.5 * (beat F1 + beat CMLt)",
        "selected": selected,
        "selected_parameters": selected_parameters,
        "selected_cases": selected_cases,
        "top_10": aggregate_rows[:10],
        "evaluation_warning": (
            "This is an illustration-specific shared-parameter sensitivity "
            "analysis, not a replacement for the official DBN benchmark."
        ),
    }
    (args.output_root / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    (args.output_root / "COMPLETE").touch()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
