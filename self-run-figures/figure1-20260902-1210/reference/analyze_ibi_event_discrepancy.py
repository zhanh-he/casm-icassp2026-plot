#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Contrast event matching with phase-insensitive IBI curves."
    )
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--trim-seconds", type=float, default=5.0)
    parser.add_argument("--tolerance", type=float, default=0.07)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def intervals(events: list[float]) -> list[tuple[float, float]]:
    return [
        ((left + right) / 2, right - left)
        for left, right in zip(events, events[1:])
    ]


def interpolate(rows: list[tuple[float, float]], time: float) -> float | None:
    if len(rows) < 2 or time < rows[0][0] or time > rows[-1][0]:
        return None
    for left, right in zip(rows, rows[1:]):
        if left[0] <= time <= right[0]:
            weight = (time - left[0]) / max(right[0] - left[0], 1e-12)
            return left[1] + weight * (right[1] - left[1])
    return None


def correlation(first: list[float], second: list[float]) -> float | None:
    if len(first) < 2:
        return None
    first_mean = sum(first) / len(first)
    second_mean = sum(second) / len(second)
    numerator = sum(
        (left - first_mean) * (right - second_mean)
        for left, right in zip(first, second)
    )
    first_scale = sum((value - first_mean) ** 2 for value in first)
    second_scale = sum((value - second_mean) ** 2 for value in second)
    if first_scale == 0 or second_scale == 0:
        return None
    return numerator / math.sqrt(first_scale * second_scale)


def event_matches(
    reference: list[float], estimate: list[float], tolerance: float
) -> list[tuple[int, int, float]]:
    reference_index = 0
    estimate_index = 0
    matches = []
    while reference_index < len(reference) and estimate_index < len(estimate):
        difference = estimate[estimate_index] - reference[reference_index]
        if abs(difference) <= tolerance:
            matches.append((reference_index, estimate_index, difference))
            reference_index += 1
            estimate_index += 1
        elif difference < 0:
            estimate_index += 1
        else:
            reference_index += 1
    return matches


def analyze(
    reference: list[float], estimate: list[float], tolerance: float
) -> dict[str, float | int | None]:
    matches = event_matches(reference, estimate, tolerance)
    true_positive = len(matches)
    false_positive = len(estimate) - true_positive
    false_negative = len(reference) - true_positive
    event_f1 = (
        2 * true_positive / (len(reference) + len(estimate))
        if reference or estimate
        else 1.0
    )
    timing_error = [abs(row[2]) for row in matches]

    reference_intervals = intervals(reference)
    estimate_intervals = intervals(estimate)
    reference_values = []
    interpolated_values = []
    for time, value in reference_intervals:
        interpolated = interpolate(estimate_intervals, time)
        if interpolated is None:
            continue
        reference_values.append(value)
        interpolated_values.append(interpolated)
    curve_errors = [
        abs(reference_value - estimate_value)
        for reference_value, estimate_value in zip(
            reference_values, interpolated_values
        )
    ]
    return {
        "groundtruth_count": len(reference),
        "estimate_count": len(estimate),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "event_f1": round(event_f1, 6),
        "matched_timing_mae_seconds": (
            round(sum(timing_error) / len(timing_error), 6)
            if timing_error
            else None
        ),
        "midpoint_aligned_ibi_mae_seconds": (
            round(sum(curve_errors) / len(curve_errors), 6)
            if curve_errors
            else None
        ),
        "midpoint_aligned_ibi_correlation": (
            round(value, 6)
            if (value := correlation(reference_values, interpolated_values))
            is not None
            else None
        ),
        "ibi_comparison_count": len(curve_errors),
    }


def main() -> None:
    args = parse_args()
    output = {
        "trim_seconds": args.trim_seconds,
        "event_tolerance_seconds": args.tolerance,
        "diagnostic_warning": (
            "Midpoint-aligned IBI MAE/correlation are explanatory diagnostics, "
            "not standard beat-tracking benchmark metrics. IBI differencing can "
            "hide absolute phase errors and event insertions/deletions."
        ),
        "cases": {},
    }
    for path in args.input:
        payload = json.loads(path.read_text())
        reference = [
            value
            for value in payload["truth"]["beat_times"]
            if value >= args.trim_seconds
        ]
        methods = {}
        for method in ("direct", "fixed_semimarkov", "dbn", "casm"):
            estimate = [
                value
                for value in payload["decoders"][method]["beat_times"]
                if value >= args.trim_seconds
            ]
            methods[method] = analyze(reference, estimate, args.tolerance)
        output["cases"][payload["piece"]] = {
            "dataset": payload["dataset"],
            "methods": methods,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
