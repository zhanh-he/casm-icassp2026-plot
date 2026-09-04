#!/usr/bin/env python3
"""Run the matched DBN calibration-scale experiment for Figure 5.

The experiment mirrors the CASM 1F/2F/4F/7F design at the data-split level:
all C(7,k) subsets of Beat This SMC folds 1..7 are used for automatic
configuration selection, while SMC fold0 and Beat This GTZAN final0 remain
fixed evaluation panels.  Every DBN choice is locked before either fixed
panel is inventoried or scored.

DBN and CASM have different parameterisations, so equality of named knobs is
neither possible nor desirable.  The DBN grid instead covers its three main
global timing controls: minimum tempo, maximum tempo, and transition strength.
The observation model and meter inventory stay at the documented baseline
settings.  Selection uses the same 0.0005 Beat-F1 equivalence band as CASM,
followed by CMLt and AMLt lexicographic tie-breaks.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import itertools
import json
import math
import platform
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Iterable


DEVELOPMENT_FOLDS = tuple(range(1, 8))
SCALES = (1, 2, 4, 7)
FAMILY_NAMES = {scale: f"exhaustive_{scale}f" for scale in SCALES}
FAMILY_COUNTS = {1: 7, 2: 21, 4: 35, 7: 1}
MIN_BPM_VALUES = (30.0, 55.0)
MAX_BPM_VALUES = (215.0, 300.0)
TRANSITION_LAMBDA_VALUES = (1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 30.0, 50.0, 70.0, 100.0, 150.0, 300.0, 500.0)
F1_EQUIVALENCE = 0.0005
BOOTSTRAP_SEED = 20260905
BOOTSTRAP_REPLICATES = 100_000
METRICS = (
    "beat_fmeasure",
    "beat_cmlt",
    "beat_amlt",
    "downbeat_fmeasure",
    "downbeat_cmlt",
    "downbeat_amlt",
)
BEAT_METRICS = METRICS[:3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--sealed-driver", type=Path, required=True)
    parser.add_argument("--source-oof-inventory", type=Path, required=True)
    parser.add_argument("--gtzan-final0-cache", type=Path, required=True)
    parser.add_argument("--casm-fixed-panel", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--trim-seconds", type=float, default=5.0)
    parser.add_argument("--verify-result-hashes", action="store_true")
    return parser.parse_args()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_driver(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("sealed_dbn_calibration_driver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import sealed driver: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def family_blocks(scale: int) -> tuple[tuple[str, tuple[int, ...]], ...]:
    return tuple(
        (f"{scale}f_" + "_".join(map(str, folds)), folds)
        for folds in itertools.combinations(DEVELOPMENT_FOLDS, scale)
    )


def validate_design() -> list[tuple[int, str, tuple[int, ...]]]:
    combinations: list[tuple[int, str, tuple[int, ...]]] = []
    for scale in SCALES:
        blocks = family_blocks(scale)
        if len(blocks) != FAMILY_COUNTS[scale]:
            raise RuntimeError(f"Unexpected {scale}F combination count: {len(blocks)}")
        expected_occurrences = math.comb(6, scale - 1)
        observed = {fold: 0 for fold in DEVELOPMENT_FOLDS}
        for label, folds in blocks:
            if 0 in folds or len(folds) != scale or len(set(folds)) != scale:
                raise RuntimeError(f"Invalid calibration subset: {label}={folds}")
            combinations.append((scale, label, folds))
            for fold in folds:
                observed[fold] += 1
        if set(observed.values()) != {expected_occurrences}:
            raise RuntimeError(f"Unbalanced {scale}F design: {observed}")
    if len(combinations) != 64:
        raise RuntimeError(f"Expected 64 combinations, found {len(combinations)}")
    return combinations


def dbn_candidates(base: Any) -> list[dict[str, Any]]:
    candidates = []
    for min_bpm, max_bpm, transition_lambda in itertools.product(
        MIN_BPM_VALUES, MAX_BPM_VALUES, TRANSITION_LAMBDA_VALUES
    ):
        candidates.append(
            base.normalize_json(
                {
                    "fps": 50.0,
                    "beats_per_bar": [3, 4],
                    "min_bpm": min_bpm,
                    "max_bpm": max_bpm,
                    "transition_lambda": transition_lambda,
                    "observation_lambda": 16.0,
                    "threshold": 0.05,
                }
            )
        )
    hashes = [base.object_sha256(candidate) for candidate in candidates]
    if len(candidates) != 52 or len(set(hashes)) != 52:
        raise RuntimeError("DBN grid must contain exactly 52 unique configurations")
    return candidates


def validate_source_inventory(base: Any, path: Path) -> dict[str, Any]:
    inventory = json.loads(path.read_text())
    if int(inventory.get("piece_count", -1)) != 4556:
        raise RuntimeError("Source OOF inventory is not the sealed 4,556-piece panel")
    if set(inventory.get("partition_counts", {})) != {f"fold{i}" for i in range(8)}:
        raise RuntimeError("Source OOF inventory must contain exactly folds 0..7")
    for entry in inventory["entries"]:
        item = Path(entry["path"])
        stat = item.stat()
        if int(entry["size"]) != stat.st_size or int(entry["mtime_ns"]) != stat.st_mtime_ns:
            raise RuntimeError(f"OOF input changed since inventory: {item}")
    smc_counts: dict[str, int] = {}
    for entry in inventory["entries"]:
        if str(entry["dataset"]).lower() == "smc":
            partition = str(entry["partition"])
            smc_counts[partition] = smc_counts.get(partition, 0) + 1
    expected = {"fold0": 27, **{f"fold{i}": 27 for i in range(1, 7)}, "fold7": 28}
    if smc_counts != expected:
        raise RuntimeError(f"Unexpected SMC fold counts: {smc_counts}")
    return inventory


def subset_inventory(
    base: Any,
    source: dict[str, Any],
    partitions: Iterable[str],
    *,
    dataset: str,
) -> dict[str, Any]:
    partition_set = set(partitions)
    entries = [
        entry
        for entry in source["entries"]
        if str(entry["partition"]) in partition_set
        and str(entry["dataset"]).lower() == dataset.lower()
    ]
    if not entries:
        raise RuntimeError(f"Empty inventory subset: {sorted(partition_set)}, {dataset}")
    partition_counts: dict[str, int] = {}
    for entry in entries:
        partition = str(entry["partition"])
        partition_counts[partition] = partition_counts.get(partition, 0) + 1
    fingerprint_payload = [
        {
            key: entry[key]
            for key in ("path", "piece", "dataset", "partition", "size", "mtime_ns")
        }
        for entry in entries
    ]
    return {
        **source,
        "entries": entries,
        "piece_count": len(entries),
        "partition_counts": partition_counts,
        "dataset_counts": {dataset.lower(): len(entries)},
        "subset_partitions": sorted(partition_set),
        "subset_dataset": dataset.lower(),
        "fingerprint": base.object_sha256(fingerprint_payload),
    }


def select_candidate(
    base: Any,
    store: Any,
    candidates: list[dict[str, Any]],
    partitions: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    defaults = {
        "fps": 50.0,
        "beats_per_bar": [3, 4],
        "min_bpm": 55.0,
        "max_bpm": 215.0,
        "transition_lambda": 100.0,
        "observation_lambda": 16.0,
        "threshold": 0.05,
    }
    for parameters in candidates:
        metadata = store.ensure("dbn", parameters)
        aggregate = base.aggregate_from_metadata(metadata, partitions, "smc")
        if int(aggregate["piece_count"]) not in {27 * len(partitions), 27 * len(partitions) + 1}:
            raise RuntimeError(f"Unexpected development SMC count: {aggregate['piece_count']}")
        distance, changed = base.parameter_distance(parameters, defaults)
        records.append(
            {
                "parameter_hash": base.object_sha256(parameters),
                "dev_cache_hash": metadata["candidate_hash"],
                "parameters": parameters,
                "development_piece_count": int(aggregate["piece_count"]),
                "beat_fmeasure": float(aggregate["metrics"]["beat_fmeasure"]),
                "beat_cmlt": float(aggregate["metrics"]["beat_cmlt"]),
                "beat_amlt": float(aggregate["metrics"]["beat_amlt"]),
                "default_distance": float(distance),
                "changed_parameter_count": int(changed),
            }
        )
    best_f1 = max(record["beat_fmeasure"] for record in records)
    eligible = [
        record
        for record in records
        if record["beat_fmeasure"] >= best_f1 - F1_EQUIVALENCE
    ]
    for metric in ("beat_cmlt", "beat_amlt"):
        best = max(record[metric] for record in eligible)
        eligible = [record for record in eligible if record[metric] >= best - 1e-15]
    eligible.sort(
        key=lambda record: (
            record["default_distance"],
            record["changed_parameter_count"],
            record["parameter_hash"],
        )
    )
    selected = dict(eligible[0])
    for record in records:
        record["within_f1_equivalence"] = bool(
            record["beat_fmeasure"] >= best_f1 - F1_EQUIVALENCE
        )
        record["selected"] = record["parameter_hash"] == selected["parameter_hash"]
    return selected, records


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def build_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    selected = [row for row in rows if row["family"] != "direct"]
    for scale in SCALES:
        family = FAMILY_NAMES[scale]
        family_rows = [row for row in selected if row["family"] == family]
        if len(family_rows) != FAMILY_COUNTS[scale]:
            raise RuntimeError(f"Unexpected {family} output count: {len(family_rows)}")
        for panel in ("smc", "gtzan"):
            for metric in METRICS if panel == "gtzan" else BEAT_METRICS:
                values = [float(row[f"{panel}_{metric}"]) for row in family_rows]
                stats = summarize_values(values, f"dbn:{family}:{panel}:{metric}")
                summary.append(
                    {
                        "decoder": "dbn",
                        "family": family,
                        "tuning_size": scale,
                        "combination_count": len(values),
                        "panel": f"{panel}_{'final0' if panel == 'gtzan' else 'fold0'}",
                        "metric": metric,
                        **stats,
                    }
                )
    return summary


def main() -> None:
    args = parse_args()
    if not 1 <= args.workers <= 12:
        raise ValueError("workers must be in [1, 12]")
    base = load_driver(args.sealed_driver.resolve())
    combinations = validate_design()
    candidates = dbn_candidates(base)
    source_inventory = validate_source_inventory(base, args.source_oof_inventory.resolve())
    project_root = args.project_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "COMPLETE").exists():
        raise RuntimeError(f"Output is already complete: {output}")

    code_files = {
        "sealed_driver": args.sealed_driver.resolve(),
        "decoders": project_root / "structbeat/decoders.py",
        "evaluation": project_root / "structbeat/evaluation.py",
        "experiment_driver": Path(__file__).resolve(),
    }
    code = {
        "host": platform.node(),
        "python": sys.version,
        "files": {
            name: {"path": str(path), "sha256": file_sha256(path)}
            for name, path in code_files.items()
        },
    }
    candidate_manifest = {
        "decoder": "joint DBNDownBeatTrackingProcessor wrapper",
        "candidate_count": len(candidates),
        "varied_parameters": {
            "min_bpm": list(MIN_BPM_VALUES),
            "max_bpm": list(MAX_BPM_VALUES),
            "transition_lambda": list(TRANSITION_LAMBDA_VALUES),
        },
        "fixed_parameters": {
            "fps": 50.0,
            "beats_per_bar": [3, 4],
            "observation_lambda": 16.0,
            "threshold": 0.05,
        },
        "candidates": [
            {
                "parameter_hash": base.object_sha256(parameters),
                "parameters": parameters,
            }
            for parameters in candidates
        ],
    }
    base.atomic_write_json(output / "CANDIDATE_GRID.json", candidate_manifest)

    dev_inventory = subset_inventory(
        base,
        source_inventory,
        [f"fold{i}" for i in DEVELOPMENT_FOLDS],
        dataset="smc",
    )
    if int(dev_inventory["piece_count"]) != 190:
        raise RuntimeError(f"Expected 190 development SMC pieces, found {dev_inventory['piece_count']}")
    base.atomic_write_json(output / "development_inventory.json", dev_inventory)

    preregistered = {
        "schema": "structbeat.dbn.calibration-scale.v1",
        "created_at": now_iso(),
        "question": "How does automatically selected DBN performance vary with SMC calibration-fold scale and composition?",
        "front_end": "Beat This eight-fold OOF activations",
        "selection_population": "SMC folds 1..7 only",
        "selection_piece_count": 190,
        "development_fold_universe": list(DEVELOPMENT_FOLDS),
        "permanently_held_out_smc_fold": 0,
        "fixed_panels_hidden_until_lock": ["SMC fold0", "Beat This GTZAN final0"],
        "combination_counts": {f"{scale}f": FAMILY_COUNTS[scale] for scale in SCALES},
        "candidate_grid_sha256": file_sha256(output / "CANDIDATE_GRID.json"),
        "candidate_count": len(candidates),
        "selection_rule": "maximize SMC Beat F1; retain candidates within 0.0005 absolute; maximize CMLt; maximize AMLt; prefer default-nearer configuration then hash",
        "f1_equivalence_absolute_0_to_1": F1_EQUIVALENCE,
        "aggregation": "unweighted macro mean over pieces",
        "trim_seconds": args.trim_seconds,
        "code": code,
    }
    preregistered_hash = base.object_sha256(preregistered)
    preregistered["protocol_hash"] = preregistered_hash
    base.atomic_write_json(output / "PREREGISTERED_PROTOCOL.json", preregistered)
    base.atomic_write_text(output / "PREREGISTERED_PROTOCOL.sha256", preregistered_hash + "\n")

    dev_store = base.EvaluationStore(
        project_root,
        output / "candidate_cache/development_smc",
        dev_inventory,
        code,
        preregistered_hash,
        args.trim_seconds,
        args.workers,
        args.verify_result_hashes,
        "dbn-calibration-development",
    )
    started = time.monotonic()
    dev_store.ensure("minimal", {})
    selected_records: list[dict[str, Any]] = []
    selection_audit: list[dict[str, Any]] = []
    for index, (scale, label, folds) in enumerate(combinations, start=1):
        partitions = [f"fold{fold}" for fold in folds]
        print(f"[select {index}/64] {label}", flush=True)
        selected, records = select_candidate(base, dev_store, candidates, partitions)
        selected_records.append(
            {
                "label": label,
                "family": FAMILY_NAMES[scale],
                "tuning_size": scale,
                "tuning_folds": ",".join(map(str, folds)),
                "selection_piece_count": selected["development_piece_count"],
                "selected_parameter_hash": selected["parameter_hash"],
                "selected_dev_cache_hash": selected["dev_cache_hash"],
                "selected_parameters": selected["parameters"],
                "development_metrics": {
                    metric: selected[metric] for metric in BEAT_METRICS
                },
            }
        )
        for record in records:
            selection_audit.append(
                {
                    "label": label,
                    "family": FAMILY_NAMES[scale],
                    "tuning_size": scale,
                    "tuning_folds": ",".join(map(str, folds)),
                    **{key: value for key, value in record.items() if key != "parameters"},
                    "parameters": base.canonical_json(record["parameters"]),
                }
            )

    unique_selected = {
        record["selected_parameter_hash"]: record["selected_parameters"]
        for record in selected_records
    }
    lock_payload = {
        "created_at": now_iso(),
        "locked_before_fixed_panel_inventory": True,
        "development_inventory_fingerprint": dev_inventory["fingerprint"],
        "candidate_grid_sha256": file_sha256(output / "CANDIDATE_GRID.json"),
        "combination_count": len(selected_records),
        "unique_configuration_count": len(unique_selected),
        "family_counts": {FAMILY_NAMES[scale]: FAMILY_COUNTS[scale] for scale in SCALES},
        "rows": selected_records,
    }
    base.atomic_write_json(output / "LOCKED_CONFIGURATIONS.json", lock_payload)
    lock_hash = base.object_sha256(lock_payload)
    base.atomic_write_text(output / "LOCKED_CONFIGURATIONS.sha256", lock_hash + "\n")
    if len(selection_audit) != 64 * 52:
        raise RuntimeError(f"Unexpected selection audit size: {len(selection_audit)}")
    base.atomic_write_csv(
        output / "selection_audit.csv",
        selection_audit,
        tuple(selection_audit[0]),
    )

    # Fixed-panel inputs are intentionally touched only after the lock exists.
    fold0_inventory = subset_inventory(base, source_inventory, ["fold0"], dataset="smc")
    if int(fold0_inventory["piece_count"]) != 27:
        raise RuntimeError(f"Expected 27 held-out SMC pieces, found {fold0_inventory['piece_count']}")
    base.atomic_write_json(output / "smc_fold0_inventory.json", fold0_inventory)
    gtzan_inventory = base.load_or_scan_inventory(
        output / "gtzan_final0_inventory.json",
        {"seed0": args.gtzan_final0_cache.resolve()},
        False,
        False,
        0,
        allow_repeated_pieces_across_partitions=False,
    )
    if int(gtzan_inventory["piece_count"]) != 993 or gtzan_inventory["partition_counts"] != {"seed0": 993}:
        raise RuntimeError(
            f"GTZAN final0 inventory mismatch: {gtzan_inventory['piece_count']}, {gtzan_inventory['partition_counts']}"
        )

    fixed_protocol = {
        **preregistered,
        "selection_lock_sha256": lock_hash,
        "selection_lock_mtime_ns": (output / "LOCKED_CONFIGURATIONS.json").stat().st_mtime_ns,
        "smc_fold0_inventory_fingerprint": fold0_inventory["fingerprint"],
        "gtzan_final0_inventory_fingerprint": gtzan_inventory["fingerprint"],
        "gtzan_checkpoint": "Beat This final0",
        "smc_fold0_piece_count": fold0_inventory["piece_count"],
        "gtzan_final0_piece_count": gtzan_inventory["piece_count"],
    }
    fixed_protocol_hash = base.object_sha256(fixed_protocol)
    fixed_protocol["fixed_evaluation_protocol_hash"] = fixed_protocol_hash
    base.atomic_write_json(output / "FIXED_EVALUATION_PROTOCOL.json", fixed_protocol)

    fold0_store = base.EvaluationStore(
        project_root,
        output / "candidate_cache/smc_fold0",
        fold0_inventory,
        code,
        fixed_protocol_hash,
        args.trim_seconds,
        args.workers,
        args.verify_result_hashes,
        "dbn-calibration-smc-fold0",
    )
    gtzan_store = base.EvaluationStore(
        project_root,
        output / "candidate_cache/gtzan_final0",
        gtzan_inventory,
        code,
        fixed_protocol_hash,
        args.trim_seconds,
        args.workers,
        args.verify_result_hashes,
        "dbn-calibration-gtzan-final0",
    )
    direct_smc_meta = fold0_store.ensure("minimal", {})
    direct_gtzan_meta = gtzan_store.ensure("minimal", {})
    direct_smc = base.aggregate_from_metadata(direct_smc_meta, ["fold0"], "smc")
    direct_gtzan = base.aggregate_from_metadata(direct_gtzan_meta, ["seed0"])
    evaluated: dict[str, dict[str, Any]] = {}
    for index, parameter_hash in enumerate(sorted(unique_selected), start=1):
        parameters = unique_selected[parameter_hash]
        print(f"[fixed {index}/{len(unique_selected)}] {parameter_hash[:12]}", flush=True)
        smc_meta = fold0_store.ensure("dbn", parameters)
        gtzan_meta = gtzan_store.ensure("dbn", parameters)
        evaluated[parameter_hash] = {
            "smc": base.aggregate_from_metadata(smc_meta, ["fold0"], "smc"),
            "gtzan": base.aggregate_from_metadata(gtzan_meta, ["seed0"]),
            "smc_cache_hash": smc_meta["candidate_hash"],
            "gtzan_cache_hash": gtzan_meta["candidate_hash"],
        }

    direct_row: dict[str, Any] = {
        "label": "direct",
        "decoder": "direct",
        "family": "direct",
        "tuning_size": 0,
        "tuning_folds": "",
        "selected_candidate_hash": "",
        "configuration_hash": base.object_sha256({"decoder": "minimal", "parameters": {}}),
        "selected_parameters": "{}",
        "smc_piece_count": direct_smc["piece_count"],
        "gtzan_piece_count": direct_gtzan["piece_count"],
    }
    for metric in METRICS:
        direct_row[f"smc_{metric}"] = direct_smc["metrics"][metric]
        direct_row[f"gtzan_{metric}"] = direct_gtzan["metrics"][metric]
    rows: list[dict[str, Any]] = [direct_row]
    for record in selected_records:
        result = evaluated[record["selected_parameter_hash"]]
        row = {
            "label": record["label"],
            "decoder": "dbn",
            "family": record["family"],
            "tuning_size": record["tuning_size"],
            "tuning_folds": record["tuning_folds"],
            "selected_candidate_hash": record["selected_parameter_hash"],
            "configuration_hash": result["gtzan_cache_hash"],
            "selected_parameters": base.canonical_json(record["selected_parameters"]),
            "smc_piece_count": result["smc"]["piece_count"],
            "gtzan_piece_count": result["gtzan"]["piece_count"],
        }
        for metric in METRICS:
            row[f"smc_{metric}"] = result["smc"]["metrics"][metric]
            row[f"gtzan_{metric}"] = result["gtzan"]["metrics"][metric]
        rows.append(row)
    output_fields = (
        "label",
        "decoder",
        "family",
        "tuning_size",
        "tuning_folds",
        "selected_candidate_hash",
        "configuration_hash",
        "selected_parameters",
        "smc_piece_count",
        "gtzan_piece_count",
        *(f"smc_{metric}" for metric in METRICS),
        *(f"gtzan_{metric}" for metric in METRICS),
    )
    base.atomic_write_csv(output / "dbn_calibration_fixed_panel.csv", rows, output_fields)
    summary = build_summary(rows)
    base.atomic_write_csv(output / "dbn_calibration_summary.csv", summary, tuple(summary[0]))

    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    check("candidate grid", len(candidates) == 52, f"{len(candidates)} unique configurations")
    check("combination design", len(selected_records) == 64, f"{len(selected_records)} locked choices")
    check("development excludes fold0", all("0" not in row["tuning_folds"].split(",") for row in selected_records), "all selection folds are in 1..7")
    check("development panel", dev_inventory["piece_count"] == 190, f"{dev_inventory['piece_count']} SMC pieces")
    check("SMC fixed panel", fold0_inventory["piece_count"] == 27, f"{fold0_inventory['piece_count']} pieces")
    check("GTZAN fixed panel", gtzan_inventory["piece_count"] == 993, f"{gtzan_inventory['piece_count']} pieces, Beat This final0")
    check("lock order", (output / "LOCKED_CONFIGURATIONS.json").stat().st_mtime_ns <= (output / "gtzan_final0_inventory.json").stat().st_mtime_ns, "selection lock predates GTZAN inventory")
    check("unique selected configurations", len(unique_selected) >= 1, f"{len(unique_selected)} unique DBN configurations")
    check("output rows", len(rows) == 65, f"{len(rows)} rows including Direct")
    finite_beat = all(
        math.isfinite(float(row[f"{panel}_{metric}"]))
        for row in rows
        for panel in ("smc", "gtzan")
        for metric in BEAT_METRICS
    )
    check("finite beat metrics", finite_beat, "all SMC fold0 and GTZAN final0 beat metrics are finite")
    if args.casm_fixed_panel:
        casm_rows = read_csv(args.casm_fixed_panel.resolve())
        casm_direct = next(row for row in casm_rows if row["family"] == "direct")
        compared = [
            "smc_beat_fmeasure",
            "smc_beat_cmlt",
            "smc_beat_amlt",
            "gtzan_beat_fmeasure",
            "gtzan_beat_cmlt",
            "gtzan_beat_amlt",
            "gtzan_downbeat_fmeasure",
            "gtzan_downbeat_cmlt",
            "gtzan_downbeat_amlt",
        ]
        largest = max(abs(float(direct_row[name]) - float(casm_direct[name])) for name in compared)
        check("Direct cross-check", largest <= 1e-15, f"maximum absolute discrepancy {largest:.3g}")
    qa = {
        "status": "pass" if all(item["passed"] for item in checks) else "fail",
        "created_at": now_iso(),
        "checks": checks,
        "candidate_count": len(candidates),
        "combination_count": len(selected_records),
        "unique_selected_configuration_count": len(unique_selected),
        "elapsed_seconds": time.monotonic() - started,
        "output_sha256": {
            name: file_sha256(output / name)
            for name in (
                "CANDIDATE_GRID.json",
                "PREREGISTERED_PROTOCOL.json",
                "LOCKED_CONFIGURATIONS.json",
                "selection_audit.csv",
                "dbn_calibration_fixed_panel.csv",
                "dbn_calibration_summary.csv",
            )
        },
    }
    base.atomic_write_json(output / "qa_report.json", qa)
    lines = [
        "# DBN calibration-scale QA",
        "",
        f"Status: **{qa['status'].upper()}**",
        "",
        f"Passed {sum(item['passed'] for item in checks)}/{len(checks)} checks.",
        "",
    ]
    for item in checks:
        lines.append(f"- **{'PASS' if item['passed'] else 'FAIL'} — {item['name']}:** {item['detail']}")
    base.atomic_write_text(output / "qa_report.md", "\n".join(lines) + "\n")
    if qa["status"] != "pass":
        raise RuntimeError("DBN calibration-scale QA failed")
    base.atomic_write_text(output / "COMPLETE", now_iso() + "\n")
    print(json.dumps(qa, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
