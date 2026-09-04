#!/usr/bin/env python3
"""Evaluate the 64 already-locked CASM fold combinations on GTZAN final0.

The source combination table fixes every selected configuration before this
script inventories or evaluates GTZAN final0. No GTZAN score participates in
configuration selection. Duplicate selected configurations are decoded once
and mapped back to all fold combinations that selected them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import platform
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any


FAMILY_COUNTS = {"exhaustive_1f": 7, "exhaustive_2f": 21, "exhaustive_4f": 35, "exhaustive_7f": 1}
BOOTSTRAP_SEED = 20260902
BOOTSTRAP_REPLICATES = 100_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--sealed-driver", type=Path, required=True)
    parser.add_argument("--locked-combinations", type=Path, required=True)
    parser.add_argument("--gtzan-final0-cache", type=Path, required=True)
    parser.add_argument("--crosscheck-csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--trim-seconds", type=float, default=5.0)
    parser.add_argument("--verify-result-hashes", action="store_true")
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_driver(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("sealed_ranked_protocol_final0", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import sealed driver: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def locked_rows(base: Any, path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    source = read_csv(path)
    direct_rows = [row for row in source if row["family"] == "direct"]
    selected_rows = [row for row in source if row["family"] != "direct"]
    if len(direct_rows) != 1 or len(selected_rows) != 64:
        raise RuntimeError(f"Expected one Direct and 64 locked configurations, found {len(direct_rows)} and {len(selected_rows)}")
    observed_counts: dict[str, int] = {}
    labels: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in selected_rows:
        family = row["family"]
        observed_counts[family] = observed_counts.get(family, 0) + 1
        if row["label"] in labels:
            raise RuntimeError(f"Duplicate combination label: {row['label']}")
        labels.add(row["label"])
        parameters = base.normalize_json(json.loads(row["selected_parameters"]))
        candidate_hash = base.object_sha256(parameters)
        if candidate_hash != row["selected_candidate_hash"]:
            raise RuntimeError(f"Locked parameter/hash mismatch for {row['label']}")
        if not row.get("tuning_folds") or "0" in row["tuning_folds"].split(","):
            raise RuntimeError(f"Invalid development folds for {row['label']}: {row.get('tuning_folds')}")
        normalized.append({"source": row, "parameters": parameters, "candidate_hash": candidate_hash})
    if observed_counts != FAMILY_COUNTS:
        raise RuntimeError(f"Unexpected family counts: {observed_counts}")
    return direct_rows[0], normalized


def summarize_values(values: list[float], seed_key: str) -> dict[str, float | None]:
    result: dict[str, float | None] = {
        "mean": statistics.fmean(values),
        "population_sd": None,
        "descriptive_ci95_low": None,
        "descriptive_ci95_high": None,
    }
    if len(values) == 1:
        return result
    result["population_sd"] = statistics.pstdev(values)
    rng = random.Random(f"{BOOTSTRAP_SEED}:{seed_key}")
    replicates = [
        sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        for _ in range(BOOTSTRAP_REPLICATES)
    ]
    replicates.sort()
    result["descriptive_ci95_low"] = replicates[int(0.025 * BOOTSTRAP_REPLICATES)]
    result["descriptive_ci95_high"] = replicates[int(0.975 * BOOTSTRAP_REPLICATES) - 1]
    return result


def main() -> None:
    args = parse_args()
    if not 1 <= args.workers <= 12:
        raise ValueError("workers must be in [1,12]")
    base = load_driver(args.sealed_driver.resolve())
    project_root = args.project_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "COMPLETE").exists():
        raise RuntimeError(f"Output is already complete: {output}")

    direct_source, combinations = locked_rows(base, args.locked_combinations.resolve())
    unique_parameters: dict[str, dict[str, Any]] = {}
    for record in combinations:
        unique_parameters[record["candidate_hash"]] = record["parameters"]
    lock_payload = {
        "source_path": str(args.locked_combinations.resolve()),
        "source_sha256": file_sha256(args.locked_combinations),
        "locked_before_gtzan_inventory": True,
        "combination_count": len(combinations),
        "unique_configuration_count": len(unique_parameters),
        "family_counts": FAMILY_COUNTS,
        "rows": [
            {
                "label": record["source"]["label"],
                "family": record["source"]["family"],
                "tuning_folds": record["source"]["tuning_folds"],
                "candidate_hash": record["candidate_hash"],
                "parameters": record["parameters"],
            }
            for record in combinations
        ],
    }
    base.atomic_write_json(output / "LOCKED_CONFIGURATIONS.json", lock_payload)
    base.atomic_write_text(output / "LOCKED_CONFIGURATIONS.sha256", base.object_sha256(lock_payload) + "\n")

    inventory = base.load_or_scan_inventory(
        output / "gtzan_final0_inventory.json",
        {"seed0": args.gtzan_final0_cache.resolve()},
        False,
        False,
        0,
        allow_repeated_pieces_across_partitions=False,
    )
    if int(inventory["piece_count"]) != 993 or inventory["partition_counts"] != {"seed0": 993}:
        raise RuntimeError(f"GTZAN final0 inventory mismatch: {inventory['piece_count']}, {inventory['partition_counts']}")

    code_files = {
        "sealed_driver": args.sealed_driver.resolve(),
        "decoders": project_root / "structbeat/decoders.py",
        "evaluation": project_root / "structbeat/evaluation.py",
        "supplemental_driver": Path(__file__).resolve(),
    }
    code = {
        "host": platform.node(),
        "python": sys.version,
        "files": {
            name: {"path": str(path), "sha256": file_sha256(path)}
            for name, path in code_files.items()
        },
    }
    protocol = {
        "schema": "structbeat.casm.locked-combinations-final0.v1",
        "question": "Evaluate the 64 configurations selected on SMC folds 1..7 on GTZAN final0",
        "selection_source_sha256": lock_payload["source_sha256"],
        "selection_visibility": "all 64 configurations fixed before GTZAN final0 inventory or scores",
        "development_folds": [1, 2, 3, 4, 5, 6, 7],
        "permanently_held_out_smc_fold": 0,
        "gtzan_checkpoint": "Beat This final0",
        "gtzan_inventory_fingerprint": inventory["fingerprint"],
        "gtzan_piece_count": inventory["piece_count"],
        "combination_count": 64,
        "unique_configuration_count": len(unique_parameters),
        "aggregation": "unweighted macro mean over pieces",
        "trim_seconds": args.trim_seconds,
        "workers": args.workers,
        "metrics": list(base.METRICS),
        "code": code,
    }
    protocol_hash = base.object_sha256(protocol)
    protocol["protocol_hash"] = protocol_hash
    base.atomic_write_json(output / "PREREGISTERED_PROTOCOL.json", protocol)
    base.atomic_write_text(output / "PREREGISTERED_PROTOCOL.sha256", protocol_hash + "\n")

    store = base.EvaluationStore(
        project_root,
        output / "candidate_cache/gtzan_final0",
        inventory,
        code,
        protocol_hash,
        args.trim_seconds,
        args.workers,
        args.verify_result_hashes,
        "locked-combinations-gtzan-final0",
    )
    started = time.monotonic()
    direct_metadata = store.ensure("minimal", {})
    direct_result = base.aggregate_from_metadata(direct_metadata, ["seed0"])
    evaluated: dict[str, dict[str, Any]] = {}
    for index, candidate_hash in enumerate(sorted(unique_parameters), start=1):
        print(f"[{index}/{len(unique_parameters)}] {candidate_hash[:12]}", flush=True)
        metadata = store.ensure("casm", unique_parameters[candidate_hash])
        aggregate = base.aggregate_from_metadata(metadata, ["seed0"])
        if int(aggregate["piece_count"]) != 993:
            raise RuntimeError(f"Incomplete final0 aggregate for {candidate_hash}")
        evaluated[candidate_hash] = {
            "candidate_hash": candidate_hash,
            "parameters": unique_parameters[candidate_hash],
            "piece_count": aggregate["piece_count"],
            "finite_counts": aggregate["finite_counts"],
            "metrics": aggregate["metrics"],
            "rows_path": metadata["rows_path"],
            "rows_sha256": metadata["rows_sha256"],
        }

    metric_columns = list(base.METRICS)
    combined_rows: list[dict[str, Any]] = []
    direct_row: dict[str, Any] = dict(direct_source)
    direct_row["gtzan_piece_count"] = direct_result["piece_count"]
    for metric in metric_columns:
        direct_row[f"gtzan_{metric}"] = direct_result["metrics"][metric]
    combined_rows.append(direct_row)
    for record in combinations:
        source = record["source"]
        result = evaluated[record["candidate_hash"]]
        row: dict[str, Any] = dict(source)
        row["gtzan_piece_count"] = result["piece_count"]
        for metric in metric_columns:
            row[f"gtzan_{metric}"] = result["metrics"][metric]
        combined_rows.append(row)
    base.atomic_write_csv(output / "calibration_fixed_panel_final0.csv", combined_rows, tuple(combined_rows[0]))
    base.atomic_write_json(
        output / "calibration_fixed_panel_final0.json",
        {"protocol_hash": protocol_hash, "row_count": len(combined_rows), "rows": combined_rows},
    )

    summary_rows: list[dict[str, Any]] = []
    for family, expected_count in FAMILY_COUNTS.items():
        family_rows = [row for row in combined_rows if row["family"] == family]
        if len(family_rows) != expected_count:
            raise RuntimeError(f"Summary family mismatch for {family}")
        for panel, prefix, metrics in (
            ("smc_fold0", "smc", list(base.BEAT_METRICS)),
            ("gtzan_final0", "gtzan", metric_columns),
        ):
            for metric in metrics:
                values = [float(row[f"{prefix}_{metric}"]) for row in family_rows]
                summary = summarize_values(values, f"{family}:{panel}:{metric}")
                summary_rows.append(
                    {
                        "family": family,
                        "tuning_size": int(family.split("_")[1][:-1]),
                        "combination_count": len(family_rows),
                        "panel": panel,
                        "metric": metric,
                        **summary,
                    }
                )
    base.atomic_write_csv(output / "calibration_summary_final0.csv", summary_rows, tuple(summary_rows[0]))

    crosscheck_rows = 0
    crosscheck_max_error = 0.0
    if args.crosscheck_csv:
        crosschecks = [row for row in read_csv(args.crosscheck_csv.resolve()) if int(row["seed"]) == 0]
        for row in crosschecks:
            candidate_hash = row["candidate_hash"]
            if candidate_hash not in evaluated:
                continue
            crosscheck_rows += 1
            for metric in metric_columns:
                error = abs(float(row[metric]) - float(evaluated[candidate_hash]["metrics"][metric]))
                crosscheck_max_error = max(crosscheck_max_error, error)
        if crosscheck_rows == 0 or crosscheck_max_error >= 1e-12:
            raise RuntimeError(f"Independent final0 cross-check failed: rows={crosscheck_rows}, error={crosscheck_max_error}")

    smc_source_error = 0.0
    source_by_label = {row["label"]: row for row in read_csv(args.locked_combinations.resolve())}
    for row in combined_rows:
        source = source_by_label[row["label"]]
        for metric in base.BEAT_METRICS:
            smc_source_error = max(smc_source_error, abs(float(row[f"smc_{metric}"]) - float(source[f"smc_{metric}"])))
    final_values = [float(row[f"gtzan_{metric}"]) for row in combined_rows for metric in metric_columns]
    checks = {
        "row_count_65": len(combined_rows) == 65,
        "combination_count_64": len(combinations) == 64,
        "unique_configuration_count_22": len(unique_parameters) == 22,
        "gtzan_final0_piece_count_993": all(int(row["gtzan_piece_count"]) == 993 for row in combined_rows),
        "gtzan_metrics_finite_and_bounded": all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in final_values),
        "smc_values_unchanged": smc_source_error < 1e-15,
        "independent_existing_final0_crosscheck": crosscheck_rows > 0 and crosscheck_max_error < 1e-12,
    }
    qa = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "smc_source_max_absolute_error": smc_source_error,
        "crosschecked_unique_configurations": crosscheck_rows,
        "crosscheck_max_absolute_error": crosscheck_max_error,
        "elapsed_seconds": time.monotonic() - started,
        "output_sha256": {
            "calibration_fixed_panel_final0.csv": file_sha256(output / "calibration_fixed_panel_final0.csv"),
            "calibration_summary_final0.csv": file_sha256(output / "calibration_summary_final0.csv"),
        },
    }
    base.atomic_write_json(output / "QA_REPORT.json", qa)
    if qa["status"] != "PASS":
        raise RuntimeError(f"QA failed: {qa}")
    base.atomic_write_json(
        output / "COMPLETE",
        {
            "status": "COMPLETE",
            "protocol_hash": protocol_hash,
            "locked_combination_count": 64,
            "unique_configuration_count": len(unique_parameters),
            "gtzan_final0_piece_count": 993,
            "qa": qa,
        },
    )
    print(json.dumps(qa, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
