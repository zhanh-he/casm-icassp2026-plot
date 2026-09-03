#!/usr/bin/env python3
"""Independently summarize and cross-check fixed-fold0 exhaustive CASM results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any


PANELS = {
    "gtzan_beat": ("gtzan", ("beat_fmeasure", "beat_cmlt", "beat_amlt")),
    "gtzan_downbeat": ("gtzan", ("downbeat_fmeasure", "downbeat_cmlt", "downbeat_amlt")),
    "smc_beat": ("smc", ("beat_fmeasure", "beat_cmlt", "beat_amlt")),
}
EXPECTED_COUNTS = {0: 1, 1: 7, 2: 21, 4: 35, 7: 1}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--driver-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 65:
        raise RuntimeError(f"Expected 65 rows, found {len(rows)}")
    by_scale: dict[int, list[dict[str, str]]] = {scale: [] for scale in EXPECTED_COUNTS}
    for row in rows:
        scale = int(row["tuning_size"])
        by_scale.setdefault(scale, []).append(row)
        folds = tuple(int(value) for value in row["tuning_folds"].split(",") if value)
        if scale == 0:
            if row["label"] != "direct" or folds:
                raise RuntimeError("Direct identity mismatch")
        elif len(folds) != scale or 0 in folds or tuple(sorted(set(folds))) != folds:
            raise RuntimeError(f"Invalid folds for {row['label']}: {folds}")
    observed_counts = {scale: len(group) for scale, group in by_scale.items()}
    if observed_counts != EXPECTED_COUNTS:
        raise RuntimeError(f"Family counts mismatch: {observed_counts}")

    summary_rows: list[dict[str, Any]] = []
    panel_metric_keys: list[tuple[str, str, str]] = []
    for panel, (prefix, metrics) in PANELS.items():
        for metric in metrics:
            source_key = f"{prefix}_{metric}"
            panel_metric_keys.append((panel, metric, source_key))
            for scale in (0, 1, 2, 4, 7):
                values = [float(row[source_key]) for row in by_scale[scale]]
                if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
                    raise RuntimeError(f"Invalid values for {panel}/{metric}/{scale}F")
                direct = float(by_scale[0][0][source_key])
                summary_rows.append(
                    {
                        "panel": panel,
                        "metric": metric,
                        "tuning_size": scale,
                        "combination_count": len(values),
                        "mean_raw": statistics.fmean(values),
                        "population_sd_raw": statistics.pstdev(values) if len(values) > 1 else None,
                        "min_raw": min(values),
                        "max_raw": max(values),
                        "delta_vs_direct_pp": (statistics.fmean(values) - direct) * 100.0,
                    }
                )

    driver = json.loads(args.driver_summary.read_text(encoding="utf-8"))
    driver_mapping: dict[tuple[str, str, int], dict[str, Any]] = {}
    for family, payload in driver["families"].items():
        scale = int(payload["tuning_size"])
        for driver_panel, panel_payload in payload["panels"].items():
            panel = "smc_beat" if driver_panel == "smc_fold0" else None
            for metric, stats in panel_payload["metrics"].items():
                if driver_panel == "gtzan_final1":
                    panel = "gtzan_downbeat" if metric.startswith("downbeat_") else "gtzan_beat"
                assert panel is not None
                driver_mapping[(panel, metric, scale)] = stats
    max_error = 0.0
    for row in summary_rows:
        scale = int(row["tuning_size"])
        if scale == 0:
            continue
        expected = driver_mapping[(str(row["panel"]), str(row["metric"]), scale)]
        max_error = max(max_error, abs(float(row["mean_raw"]) - float(expected["mean"])))
        observed_sd = row["population_sd_raw"]
        expected_sd = expected["population_sd"]
        if observed_sd is None or expected_sd is None:
            if not (observed_sd is None and expected_sd is None):
                raise RuntimeError(f"SD null mismatch for {row}")
        else:
            max_error = max(max_error, abs(float(observed_sd) - float(expected_sd)))
    if max_error > 1e-12:
        raise RuntimeError(f"Driver summary mismatch: max error {max_error}")

    interpretation: dict[str, Any] = {
        "input_sha256": sha256(args.input),
        "driver_summary_sha256": sha256(args.driver_summary),
        "family_counts": EXPECTED_COUNTS,
        "driver_reconciliation_max_abs_error": max_error,
        "unique_configuration_count": len({row["configuration_hash"] for row in rows if int(row["tuning_size"]) > 0}),
        "unique_candidate_count": len({row["selected_candidate_hash"] for row in rows if int(row["tuning_size"]) > 0 and row["selected_candidate_hash"]}),
        "metrics": {},
    }
    for panel, metric, source_key in panel_metric_keys:
        centers = {
            scale: statistics.fmean(float(row[source_key]) for row in by_scale[scale])
            for scale in (1, 2, 4, 7)
        }
        best_value = max(centers.values())
        interpretation["metrics"][f"{panel}.{metric}"] = {
            "centers_raw": centers,
            "best_tuning_sizes": [scale for scale, value in centers.items() if abs(value - best_value) <= 1e-15],
            "nondecreasing_1_2_4_7": all(
                centers[left] <= centers[right]
                for left, right in ((1, 2), (2, 4), (4, 7))
            ),
            "adjacent_deltas_pp": {
                "1_to_2": (centers[2] - centers[1]) * 100.0,
                "2_to_4": (centers[4] - centers[2]) * 100.0,
                "4_to_7": (centers[7] - centers[4]) * 100.0,
            },
        }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "independent_family_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    interpretation_path = args.output_dir / "independent_result_interpretation.json"
    interpretation_path.write_text(json.dumps(interpretation, indent=2, sort_keys=True) + "\n")
    receipt = {
        "status": "PASS",
        "input_rows": len(rows),
        "summary_rows": len(summary_rows),
        "driver_reconciliation_max_abs_error": max_error,
        "summary_sha256": sha256(summary_path),
        "interpretation_sha256": sha256(interpretation_path),
    }
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
