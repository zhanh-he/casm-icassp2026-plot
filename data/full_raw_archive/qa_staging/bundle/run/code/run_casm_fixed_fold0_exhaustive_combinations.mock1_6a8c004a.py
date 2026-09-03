#!/usr/bin/env python3
"""Fixed-fold0 exhaustive CASM tuning-data scaling sensitivity.

Fold 0 is permanently excluded from CASM parameter selection.  The driver
exhaustively selects on every 1F/2F/4F/7F subset of folds 1..7 (7/21/35/1),
locks all 64 configurations, then evaluates the same frozen configurations on
SMC fold0 and GTZAN final1.  It imports the sealed ranked-protocol driver rather
than reimplementing its staged search or selection rule.  The sealed OOF
candidate registry is mounted read-only by policy: complete entries may be
adapted, while missing candidates are decoded into this run's private registry.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import itertools
import json
import math
import os
import platform
import random
import shutil
import signal
import statistics
import sys
import time
import traceback
from pathlib import Path
from typing import Any


DEVELOPMENT_FOLDS = tuple(range(1, 8))
FAMILY_NAMES = {1: "exhaustive_1f", 2: "exhaustive_2f", 4: "exhaustive_4f", 7: "exhaustive_7f"}


def family_blocks(size: int) -> tuple[tuple[str, tuple[int, ...]], ...]:
    return tuple(
        (f"{size}f_" + "_".join(map(str, folds)), folds)
        for folds in itertools.combinations(DEVELOPMENT_FOLDS, size)
    )


COMBINATION_FAMILIES = {size: family_blocks(size) for size in (1, 2, 4, 7)}
COMBINATIONS = tuple(
    block for size in (1, 2, 4, 7) for block in COMBINATION_FAMILIES[size]
)
BOOTSTRAP_SEED = 20260902
BOOTSTRAP_REPLICATES = 100_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--sealed-driver", type=Path, required=True)
    parser.add_argument("--sealed-registry", type=Path, required=True)
    parser.add_argument("--source-inventory", type=Path, required=True)
    parser.add_argument("--source-direct-metadata", type=Path, required=True)
    parser.add_argument("--source-seal-manifest", type=Path, required=True)
    parser.add_argument("--gtzan-final1-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--trim-seconds", type=float, default=5.0)
    parser.add_argument("--guard", type=float, default=0.0005)
    parser.add_argument("--metric-tie", type=float, default=0.0005)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--mock-pieces-per-fold", type=int, default=3)
    parser.add_argument("--mock-candidates-per-stage", type=int, default=2)
    parser.add_argument("--verify-result-hashes", action="store_true")
    return parser.parse_args()


def load_sealed_driver(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("sealed_ranked_protocol", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import sealed driver: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_design() -> None:
    expected = set(DEVELOPMENT_FOLDS)
    expected_counts = {1: 7, 2: 21, 4: 35, 7: 1}
    expected_occurrences = {1: 1, 2: 6, 4: 20, 7: 1}
    seen: set[tuple[int, ...]] = set()
    for size, blocks in COMBINATION_FAMILIES.items():
        if len(blocks) != expected_counts[size]:
            raise RuntimeError(f"Unexpected {size}F count: {len(blocks)}")
        occurrences = {fold: 0 for fold in DEVELOPMENT_FOLDS}
        for label, folds in blocks:
            canonical = tuple(sorted(folds))
            if len(folds) != size or set(folds) - expected or 0 in folds or canonical in seen:
                raise RuntimeError(f"Invalid exhaustive block {label}: {folds}")
            seen.add(canonical)
            for fold in folds:
                occurrences[fold] += 1
        if set(occurrences.values()) != {expected_occurrences[size]}:
            raise RuntimeError(f"{size}F family is not balanced: {occurrences}")
    if len(COMBINATIONS) != 64:
        raise RuntimeError(f"Expected 64 combinations, found {len(COMBINATIONS)}")


def registry_receipt(base: Any, root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    complete: list[str] = []
    incomplete: list[str] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or len(child.name) != 64:
            continue
        if (child / "COMPLETE").is_file():
            for required in ("params.json", "pieces.csv", "summary.json"):
                if not (child / required).is_file():
                    raise RuntimeError(f"COMPLETE candidate missing {required}: {child}")
            complete.append(child.name)
        else:
            incomplete.append(child.name)
    if incomplete:
        raise RuntimeError(f"Sealed registry contains incomplete candidates: {incomplete[:5]}")
    return {
        "path": str(root.resolve()),
        "complete_candidate_count": len(complete),
        "candidate_name_set_sha256": base.object_sha256(complete),
        "incomplete_candidate_count": 0,
    }


def validate_inventory(base: Any, source: Path, mock: bool, pieces: int) -> dict[str, Any]:
    inventory = json.loads(source.read_text())
    if int(inventory.get("piece_count", -1)) != 4556:
        raise RuntimeError("Source OOF inventory is not the sealed 4,556-piece panel")
    if set(inventory.get("partition_counts", {})) != {f"fold{i}" for i in range(8)}:
        raise RuntimeError("Source OOF inventory does not contain exactly folds 0..7")
    for entry in inventory["entries"]:
        path = Path(entry["path"])
        stat = path.stat()
        if int(entry["size"]) != stat.st_size or int(entry["mtime_ns"]) != stat.st_mtime_ns:
            raise RuntimeError(f"OOF cache entry changed: {path}")
    if not mock:
        return inventory
    selected = base.choose_mock_entries(inventory["entries"], pieces)
    partition_counts: dict[str, int] = {}
    dataset_counts: dict[str, int] = {}
    for entry in selected:
        partition = str(entry["partition"])
        dataset = str(entry["dataset"])
        partition_counts[partition] = partition_counts.get(partition, 0) + 1
        dataset_counts[dataset] = dataset_counts.get(dataset, 0) + 1
    fingerprint_payload = [
        {key: entry[key] for key in ("path", "piece", "dataset", "partition", "size", "mtime_ns")}
        for entry in selected
    ]
    result = dict(inventory)
    result.update(
        entries=selected,
        piece_count=len(selected),
        full_piece_count_before_mock=4556,
        partition_counts=partition_counts,
        dataset_counts=dataset_counts,
        mock=True,
        fingerprint=base.object_sha256(fingerprint_payload),
    )
    return result


def subset_inventory(
    base: Any,
    source: dict[str, Any],
    partitions: set[str],
    dataset: str | None = None,
) -> dict[str, Any]:
    """Create a fingerprinted in-memory inventory without rescanning caches."""

    entries = [
        entry
        for entry in source["entries"]
        if str(entry["partition"]) in partitions
        and (dataset is None or str(entry["dataset"]).lower() == dataset.lower())
    ]
    if not entries:
        raise RuntimeError(
            f"Inventory subset is empty: partitions={sorted(partitions)}, dataset={dataset}"
        )
    partition_counts: dict[str, int] = {}
    dataset_counts: dict[str, int] = {}
    for entry in entries:
        partition = str(entry["partition"])
        dataset_name = str(entry["dataset"]).lower()
        partition_counts[partition] = partition_counts.get(partition, 0) + 1
        dataset_counts[dataset_name] = dataset_counts.get(dataset_name, 0) + 1
    fingerprint_payload = [
        {key: entry[key] for key in ("path", "piece", "dataset", "partition", "size", "mtime_ns")}
        for entry in entries
    ]
    result = dict(source)
    result.update(
        entries=entries,
        piece_count=len(entries),
        partition_counts=partition_counts,
        dataset_counts=dataset_counts,
        fingerprint=base.object_sha256(fingerprint_payload),
        subset_partitions=sorted(partitions),
        subset_dataset=dataset,
    )
    return result


def build_read_through_store(base: Any) -> type:
    class ReadThroughStore(base.EvaluationStore):
        """Read sealed complete entries; publish only to a private registry."""

        def __init__(self, *args: Any, writable_registry: Path, **kwargs: Any) -> None:
            self.writable_registry = writable_registry.resolve()
            self.writable_registry.mkdir(parents=True, exist_ok=True)
            self._memo: dict[tuple[str, str], dict[str, Any]] = {}
            super().__init__(*args, **kwargs)

        def ensure(self, decoder: str, parameters: dict[str, Any]) -> dict[str, Any]:
            memo_key = (decoder, base.canonical_json(parameters))
            if memo_key not in self._memo:
                self._memo[memo_key] = super().ensure(decoder, parameters)
            return self._memo[memo_key]

        def _load_or_wait_shared(self, key: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
            assert self.shared_root is not None
            sealed_candidate = self.shared_root / key
            if sealed_candidate.exists():
                if not (sealed_candidate / "COMPLETE").is_file():
                    raise RuntimeError(f"Refusing to alter incomplete sealed candidate: {sealed_candidate}")
                return super()._load_or_wait_shared(key, parameters)
            original = self.shared_root
            self.shared_root = self.writable_registry
            try:
                return super()._load_or_wait_shared(key, parameters)
            finally:
                self.shared_root = original

        def _publish_shared(
            self,
            key: str,
            parameters: dict[str, Any],
            rows: list[dict[str, Any]],
            metadata: dict[str, Any],
        ) -> None:
            original = self.shared_root
            self.shared_root = self.writable_registry
            try:
                super()._publish_shared(key, parameters, rows, metadata)
            finally:
                self.shared_root = original

    return ReadThroughStore


def aggregate_record(base: Any, metadata: dict[str, Any], folds: list[int]) -> dict[str, Any]:
    partitions = [f"fold{fold}" for fold in folds]
    overall = base.aggregate_from_metadata(metadata, partitions)
    smc = base.aggregate_from_metadata(metadata, partitions, "smc")
    return {
        "piece_count": overall["piece_count"],
        "smc_piece_count": smc["piece_count"],
        "overall": overall["metrics"],
        "smc": smc["metrics"],
    }


def selection_rows(base: Any, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        row: dict[str, Any] = {
            "label": record["label"],
            "family": record["family"],
            "tuning_size": record["tuning_size"],
            "tuning_folds": ",".join(map(str, record["tuning_folds"])),
            "selected_candidate_hash": record["selected_candidate_hash"],
            "configuration_hash": record["configuration_hash"],
            "identity": record["identity"],
            "development_piece_count": record["development"]["piece_count"],
            "development_smc_piece_count": record["development"]["smc_piece_count"],
            "selected_parameters": base.canonical_json(record["selected_parameters"]),
        }
        for subset in ("overall", "smc"):
            metrics = base.METRICS if subset == "overall" else base.BEAT_METRICS
            for metric in metrics:
                row[f"development_{subset}_{metric}"] = record["development"][subset][metric]
        rows.append(row)
    return rows


def write_selection_outputs(base: Any, output: Path, protocol_hash: str, records: list[dict[str, Any]]) -> None:
    payload = {"protocol_hash": protocol_hash, "combination_count": len(records), "combinations": records}
    base.atomic_write_json(output / "combination_selection_results.json", payload)
    rows = selection_rows(base, records)
    if rows:
        base.atomic_write_csv(output / "combination_selection_results.csv", rows, tuple(rows[0]))


def read_piece_rows(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        result: list[dict[str, str]] = []
        for source in csv.DictReader(handle):
            row = dict(source)
            if not row.get("partition") and row.get("fold") is not None:
                fold = str(row["fold"])
                row["partition"] = fold if fold.startswith("fold") else f"fold{int(fold)}"
            row["dataset"] = str(row.get("dataset", "")).lower()
            result.append(row)
        return result


def write_panel_outputs(
    base: Any,
    output: Path,
    protocol_hash: str,
    stem: str,
    records: list[dict[str, Any]],
) -> None:
    base.atomic_write_json(
        output / f"{stem}_results.json",
        {"protocol_hash": protocol_hash, "combination_count": len(records), "combinations": records},
    )
    rows: list[dict[str, Any]] = []
    for record in records:
        row = {
            "label": record["label"],
            "family": record["family"],
            "tuning_size": record["tuning_size"],
            "tuning_folds": ",".join(map(str, record["tuning_folds"])),
            "selected_candidate_hash": record["selected_candidate_hash"],
            "configuration_hash": record["configuration_hash"],
            "piece_count": record["piece_count"],
        }
        row.update(record["metrics"])
        rows.append(row)
    if rows:
        base.atomic_write_csv(output / f"{stem}_results.csv", rows, tuple(rows[0]))


def summarize_values(values: list[float], seed_key: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "mean": statistics.fmean(values),
        "population_sd": None,
        "descriptive_bootstrap_ci95": None,
    }
    if len(values) == 1:
        return summary
    summary["population_sd"] = statistics.pstdev(values)
    rng = random.Random(f"{BOOTSTRAP_SEED}:{seed_key}")
    replicates = [
        sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        for _ in range(BOOTSTRAP_REPLICATES)
    ]
    replicates.sort()
    summary["descriptive_bootstrap_ci95"] = [
        replicates[int(0.025 * BOOTSTRAP_REPLICATES)],
        replicates[int(0.975 * BOOTSTRAP_REPLICATES) - 1],
    ]
    return summary


def bootstrap_summary(
    base: Any,
    smc_records: list[dict[str, Any]],
    gtzan_records: list[dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for size in (1, 2, 4, 7):
        family = FAMILY_NAMES[size]
        smc_group = [record for record in smc_records if record["family"] == family]
        gtzan_group = [record for record in gtzan_records if record["family"] == family]
        if len(smc_group) != len(gtzan_group) or len(smc_group) != len(COMBINATION_FAMILIES[size]):
            raise RuntimeError(f"Panel family alignment failed for {family}")
        panels: dict[str, Any] = {}
        for panel, group, metrics in (
            ("smc_fold0", smc_group, base.BEAT_METRICS),
            ("gtzan_final1", gtzan_group, base.METRICS),
        ):
            panels[panel] = {
                "metrics": {
                    metric: summarize_values(
                        [float(record["metrics"][metric]) for record in group],
                        f"{family}:{panel}:{metric}",
                    )
                    for metric in metrics
                }
            }
        result[family] = {
            "tuning_size": size,
            "combination_count": len(smc_group),
            "panels": panels,
        }
    return {
        "resampling_unit": "fold combination",
        "interpretation": "descriptive across-combination uncertainty; not a test-population or training-seed confidence interval",
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "families": result,
    }


def marker_start(base: Any, output: Path, args: argparse.Namespace) -> float:
    output.mkdir(parents=True, exist_ok=True)
    complete = output / "COMPLETE"
    if complete.exists():
        raise RuntimeError(f"Run is already COMPLETE: {complete}")
    running = output / "RUNNING"
    if running.exists():
        prior = json.loads(running.read_text())
        prior_pid = int(prior.get("pid", -1))
        alive = False
        if prior.get("host") == platform.node() and prior_pid > 1:
            try:
                os.kill(prior_pid, 0)
                alive = True
            except ProcessLookupError:
                pass
            except PermissionError:
                alive = True
        if alive:
            raise RuntimeError(f"Another live process owns RUNNING: PID {prior_pid}")
        archive = output / "marker_archive" / f"RUNNING.stale.{int(time.time())}.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        os.replace(running, archive)
    if (output / "FAILED").exists():
        archive = output / "marker_archive" / f"FAILED.prior.{int(time.time())}.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        os.replace(output / "FAILED", archive)
    started = time.time()
    receipt = {
        "pid": os.getpid(),
        "host": platform.node(),
        "started_at": base.now_iso(),
        "started_epoch": started,
        "argv": [sys.executable, *sys.argv],
        "workers": args.workers,
        "mock": args.mock,
    }
    base.atomic_write_json(running, receipt)
    base.atomic_write_json(output / "COMMAND.json", receipt)
    base.atomic_write_text(output / "PID", f"{os.getpid()}\n")
    return started


def main() -> None:
    args = parse_args()
    if not 1 <= args.workers <= 12:
        raise ValueError("workers must be in [1,12]")
    if not args.mock and (args.guard != 0.0005 or args.metric_tie != 0.0005):
        raise ValueError("formal guard and tie thresholds are locked at 0.0005")
    validate_design()
    base = load_sealed_driver(args.sealed_driver.resolve())
    output = args.output.resolve()
    started = marker_start(base, output, args)

    def terminate(signum: int, _frame: Any) -> None:
        raise base.Terminated(f"received signal {signum}")

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        project_root = args.project_root.resolve()
        source_inventory_path = args.source_inventory.resolve()
        full_inventory = validate_inventory(
            base, source_inventory_path, args.mock, args.mock_pieces_per_fold
        )
        selection_inventory = subset_inventory(
            base,
            full_inventory,
            {f"fold{fold}" for fold in DEVELOPMENT_FOLDS},
        )
        smc_fold0_inventory = subset_inventory(base, full_inventory, {"fold0"}, "smc")
        if not args.mock and int(smc_fold0_inventory["piece_count"]) != 27:
            raise RuntimeError("SMC fold0 is not the expected 27-piece panel")
        base.atomic_write_json(output / "input_inventory.json", full_inventory)
        base.atomic_write_json(output / "selection_inventory_folds1_7.json", selection_inventory)
        base.atomic_write_json(output / "smc_fold0_inventory.json", smc_fold0_inventory)
        registry = registry_receipt(base, args.sealed_registry.resolve())
        seal_payload = json.loads(args.source_seal_manifest.read_text())
        code = {
            "git_commit": base.run_command(["git", "rev-parse", "HEAD"], project_root),
            "git_dirty": bool(base.run_command(["git", "status", "--porcelain"], project_root)),
            "files": {
                "driver": {"path": str(args.sealed_driver.resolve()), "sha256": base.file_sha256(args.sealed_driver)},
                "supplemental_driver": {"path": str(Path(__file__).resolve()), "sha256": base.file_sha256(Path(__file__))},
                "decoders": {"path": str(project_root / "structbeat/decoders.py"), "sha256": base.file_sha256(project_root / "structbeat/decoders.py")},
                "evaluation": {"path": str(project_root / "structbeat/evaluation.py"), "sha256": base.file_sha256(project_root / "structbeat/evaluation.py")},
                "historical_search": {"path": str(project_root / "scripts/search_asm.py"), "sha256": base.file_sha256(project_root / "scripts/search_asm.py")},
            },
        }
        historical = base.full_historical_parameters(project_root)
        protocol = {
            "schema_version": 1,
            "name": "casm-fixed-fold0-exhaustive-combination-scaling-v1",
            "mock": args.mock,
            "design": {
                "permanently_held_out_smc_fold": 0,
                "development_fold_universe": list(DEVELOPMENT_FOLDS),
                "families": {
                    f"{size}f": [
                        {"label": label, "folds": list(folds)}
                        for label, folds in COMBINATION_FAMILIES[size]
                    ]
                    for size in (1, 2, 4, 7)
                },
                "combination_counts": {"1f": 7, "2f": 21, "4f": 35, "7f": 1},
                "total_combinations": 64,
                "contract": "all C(7,k) subsets for k in {1,2,4,7}; fold0 never enters selection",
            },
            "selection": {
                "data_visibility": "Beat This OOF folds1..7 only; fold0 and GTZAN metrics unavailable until all 64 configurations are locked",
                "stages": ["duration coarse", "duration refinement", "downbeat meter", "agreement", "fallback", "Historical one-field local refinement"],
                "candidate_spaces": {
                    "duration_coarse": base.DURATION_COARSE_VALUES,
                    "duration_refine": base.DURATION_REFINE_VALUES,
                    "meter": base.METER_VALUES,
                    "agreement": base.AGREEMENT_VALUES,
                    "fallback": base.DEFAULT_FALLBACK_VALUES,
                    "historical_local": base.DEFAULT_LOCAL_VALUES,
                },
                "f1_guard_absolute_0_to_1": args.guard,
                "metric_tie_absolute_0_to_1": args.metric_tie,
                "rule": "sealed ranked-protocol run_staged_search/select_lexicographic",
                "historical_parameters": historical,
            },
            "fixed_evaluation_panels": {
                "smc_fold0": {
                    "piece_count": smc_fold0_inventory["piece_count"],
                    "metrics": list(base.BEAT_METRICS),
                    "used_for_selection": False,
                },
                "gtzan_final1": {
                    "piece_count": 993 if not args.mock else args.mock_pieces_per_fold,
                    "metrics": list(base.METRICS),
                    "used_for_selection": False,
                },
                "lock_order": "all 64 selections and hashes locked before either fixed-panel score is computed",
            },
            "gtzan": {
                "checkpoint_seed": 1,
                "cache_path": str(args.gtzan_final1_cache.resolve()),
                "seed_selection_basis": "prior observed GTZAN Beat F1; final1 was the post-hoc best checkpoint under that metric",
                "test_conditioned_backbone_seed": True,
                "eligible_for_clean_test_claim": False,
                "gtzan_used_for_casm_parameter_selection": False,
                "lock_order": "all 64 CASM selections and hashes locked before GTZAN inventory is opened",
            },
            "uncertainty": {
                "unit": "fold combination",
                "summary": "mean, population SD, descriptive percentile bootstrap CI",
                "replicates": BOOTSTRAP_REPLICATES,
                "seed": BOOTSTRAP_SEED,
                "claim_limit": "descriptive across-combination uncertainty, not test-population or training-seed CI",
            },
            "metrics": list(base.METRICS),
            "aggregation": "unweighted macro mean over pieces",
            "trim_seconds": args.trim_seconds,
            "workers": args.workers,
            "source_oof_inventory": {
                "path": str(source_inventory_path),
                "file_sha256": base.file_sha256(source_inventory_path),
                "fingerprint": full_inventory["fingerprint"],
                "piece_count": full_inventory["piece_count"],
            },
            "selection_inventory": {
                "fingerprint": selection_inventory["fingerprint"],
                "piece_count": selection_inventory["piece_count"],
                "partition_counts": selection_inventory["partition_counts"],
                "fold0_piece_count": 0,
            },
            "sealed_registry": registry,
            "source_seal": {
                "path": str(args.source_seal_manifest.resolve()),
                "file_sha256": base.file_sha256(args.source_seal_manifest),
                "payload_hash": seal_payload.get("payload_hash"),
            },
            "code": code,
        }
        protocol_hash = base.object_sha256(protocol)
        protocol["protocol_hash"] = protocol_hash
        prereg = output / "PREREGISTERED_PROTOCOL.json"
        if prereg.exists() and json.loads(prereg.read_text()) != base.normalize_json(protocol):
            raise RuntimeError("Existing preregistered protocol differs; use a new output")
        base.atomic_write_json(prereg, protocol)
        base.atomic_write_text(output / "PREREGISTERED_PROTOCOL.sha256", f"{protocol_hash}\n")

        Store = build_read_through_store(base)
        store = Store(
            project_root,
            output / "candidate_cache/oof",
            selection_inventory,
            code,
            protocol_hash,
            args.trim_seconds,
            args.workers,
            args.verify_result_hashes,
            "fixed-fold0-selection-oof",
            shared_root=args.sealed_registry.resolve(),
            writable_registry=output / "candidate_registry",
            shared_wait_seconds=0.0,
        )
        if args.mock:
            direct = store.ensure("minimal", {})
        else:
            direct = json.loads(args.source_direct_metadata.read_text())
            if int(direct.get("piece_count", -1)) != 4556:
                raise RuntimeError("Sealed Direct metadata is not the 4,556-piece panel")

        records: list[dict[str, Any]] = []
        for index, (label, folds_tuple) in enumerate(COMBINATIONS, start=1):
            folds = list(folds_tuple)
            selection_path = output / "searches" / label / "selection.json"
            if selection_path.exists():
                selection = json.loads(selection_path.read_text())
                if selection.get("protocol_hash") != protocol_hash or selection.get("tuning_folds") != folds:
                    raise RuntimeError(f"Existing selection identity mismatch: {selection_path}")
            else:
                selection = base.run_staged_search(
                    label,
                    folds,
                    store,
                    output / "searches",
                    direct,
                    historical,
                    base.DEFAULT_FALLBACK_VALUES,
                    base.DEFAULT_LOCAL_VALUES,
                    args.guard,
                    args.metric_tie,
                    args.mock,
                    args.mock_candidates_per_stage,
                    protocol_hash,
                )
            metadata = base.selected_metadata(selection, store, direct)
            parameters = selection.get("selected_parameters")
            decoder = "minimal" if selection["identity"] else "casm"
            tuning_size = len(folds)
            record = {
                "label": label,
                "family": FAMILY_NAMES[tuning_size],
                "tuning_size": tuning_size,
                "tuning_folds": folds,
                "identity": selection["identity"],
                "selected_candidate_hash": selection.get("selected_candidate_hash"),
                "configuration_hash": base.object_sha256({"decoder": decoder, "parameters": parameters or {}}),
                "selected_parameters": parameters,
                "development": aggregate_record(base, metadata, folds),
            }
            records.append(record)
            write_selection_outputs(base, output, protocol_hash, records)
            base.atomic_write_json(output / "SEARCH_PROGRESS.json", {"completed": index, "total": len(COMBINATIONS), "last_label": label, "updated_at": base.now_iso()})

        frozen_payload = {
            "protocol_hash": protocol_hash,
            "combination_count": len(records),
            "configurations": [
                {key: record[key] for key in ("label", "family", "tuning_folds", "identity", "selected_candidate_hash", "configuration_hash", "selected_parameters")}
                for record in records
            ],
            "gtzan_checkpoint_seed": 1,
            "gtzan_cache_path": str(args.gtzan_final1_cache.resolve()),
            "gtzan_used_for_selection": False,
            "smc_fold0_used_for_selection": False,
            "evaluation_order": "frozen lock first; SMC fold0 and GTZAN final1 second",
            "eligible_for_clean_test_claim": False,
        }
        frozen_lock = base.stable_lock(output / "FROZEN_COMBINATIONS_LOCK.json", frozen_payload)
        base.atomic_write_text(output / "FROZEN_LOCKED", f"{frozen_lock['payload_hash']}\n")

        # Fixed SMC fold0 is evaluated only after every development combination
        # has been selected and locked.  CASM rows are read from the immutable
        # OOF registry through a 27-piece adapter; Direct is decoded once.
        smc_store = Store(
            project_root,
            output / "candidate_cache/smc_fold0",
            smc_fold0_inventory,
            code,
            protocol_hash,
            args.trim_seconds,
            args.workers,
            args.verify_result_hashes,
            "smc-fold0-after-lock",
            shared_root=args.sealed_registry.resolve(),
            writable_registry=output / "candidate_registry_smc_fold0",
            shared_wait_seconds=0.0,
        )
        direct_configuration_hash = base.object_sha256({"decoder": "minimal", "parameters": {}})
        direct_smc_metadata = smc_store.ensure("minimal", {})
        direct_smc = base.aggregate_from_metadata(direct_smc_metadata, ["fold0"], "smc")
        if not args.mock and int(direct_smc["piece_count"]) != 27:
            raise RuntimeError("Direct SMC fold0 aggregate is not 27 pieces")
        smc_records: list[dict[str, Any]] = []
        smc_piece_rows: list[dict[str, Any]] = []
        smc_metadata_memo: dict[tuple[str, str], dict[str, Any]] = {
            ("minimal", base.canonical_json({})): direct_smc_metadata
        }

        def append_piece_ledger(
            destination: list[dict[str, Any]],
            metadata: dict[str, Any],
            identity: dict[str, Any],
            metrics: tuple[str, ...] | list[str],
            panel: str,
        ) -> None:
            for source in read_piece_rows(Path(metadata["rows_path"])):
                if panel == "smc_fold0" and not (
                    source["dataset"] == "smc" and source["partition"] == "fold0"
                ):
                    continue
                row = dict(identity)
                row.update(
                    piece=source["piece"],
                    dataset=source["dataset"],
                    partition=source["partition"],
                )
                row.update({metric: source[metric] for metric in metrics})
                destination.append(row)

        append_piece_ledger(
            smc_piece_rows,
            direct_smc_metadata,
            {
                "label": "direct",
                "family": "direct",
                "tuning_size": 0,
                "tuning_folds": "",
                "selected_candidate_hash": "",
                "configuration_hash": direct_configuration_hash,
            },
            base.BEAT_METRICS,
            "smc_fold0",
        )
        for record in records:
            decoder = "minimal" if record["identity"] else "casm"
            parameters = record["selected_parameters"] or {}
            memo_key = (decoder, base.canonical_json(parameters))
            if memo_key not in smc_metadata_memo:
                smc_metadata_memo[memo_key] = smc_store.ensure(decoder, parameters)
            metadata = smc_metadata_memo[memo_key]
            metrics = base.aggregate_from_metadata(metadata, ["fold0"], "smc")
            result = {
                "label": record["label"],
                "family": record["family"],
                "tuning_size": record["tuning_size"],
                "tuning_folds": record["tuning_folds"],
                "selected_candidate_hash": record["selected_candidate_hash"],
                "configuration_hash": record["configuration_hash"],
                "piece_count": metrics["piece_count"],
                "metrics": {metric: metrics["metrics"][metric] for metric in base.BEAT_METRICS},
                "rows_path": metadata["rows_path"],
                "rows_sha256": metadata["rows_sha256"],
            }
            smc_records.append(result)
            append_piece_ledger(
                smc_piece_rows,
                metadata,
                {
                    "label": record["label"],
                    "family": record["family"],
                    "tuning_size": record["tuning_size"],
                    "tuning_folds": ",".join(map(str, record["tuning_folds"])),
                    "selected_candidate_hash": record["selected_candidate_hash"] or "",
                    "configuration_hash": record["configuration_hash"],
                },
                base.BEAT_METRICS,
                "smc_fold0",
            )
            write_panel_outputs(base, output, protocol_hash, "smc_fold0", smc_records)
        base.atomic_write_gzip_csv(
            output / "smc_fold0_per_piece.csv.gz", smc_piece_rows, tuple(smc_piece_rows[0])
        )

        gtzan_inventory = base.load_or_scan_inventory(
            output / "gtzan_final1_inventory.json",
            {"seed1": args.gtzan_final1_cache.resolve()},
            False,
            args.mock,
            args.mock_pieces_per_fold,
            allow_repeated_pieces_across_partitions=False,
        )
        if not args.mock and int(gtzan_inventory["piece_count"]) != 993:
            raise RuntimeError("GTZAN final1 inventory is not the expected 993-piece panel")
        external = base.EvaluationStore(
            project_root,
            output / "candidate_cache/gtzan_final1",
            gtzan_inventory,
            code,
            protocol_hash,
            args.trim_seconds,
            args.workers,
            args.verify_result_hashes,
            "gtzan-final1-after-lock",
        )
        direct_gtzan_metadata = external.ensure("minimal", {})
        direct_gtzan = base.aggregate_from_metadata(direct_gtzan_metadata, ["seed1"])
        gtzan_records: list[dict[str, Any]] = []
        piece_rows: list[dict[str, Any]] = []
        external_memo: dict[tuple[str, str], dict[str, Any]] = {
            ("minimal", base.canonical_json({})): direct_gtzan_metadata
        }
        append_piece_ledger(
            piece_rows,
            direct_gtzan_metadata,
            {
                "label": "direct",
                "family": "direct",
                "tuning_size": 0,
                "tuning_folds": "",
                "selected_candidate_hash": "",
                "configuration_hash": direct_configuration_hash,
            },
            base.METRICS,
            "gtzan_final1",
        )
        for record in records:
            decoder = "minimal" if record["identity"] else "casm"
            parameters = record["selected_parameters"] or {}
            memo_key = (decoder, base.canonical_json(parameters))
            if memo_key not in external_memo:
                external_memo[memo_key] = external.ensure(decoder, parameters)
            metadata = external_memo[memo_key]
            metrics = base.aggregate_from_metadata(metadata, ["seed1"])
            result = {
                "label": record["label"],
                "family": record["family"],
                "tuning_size": record["tuning_size"],
                "tuning_folds": record["tuning_folds"],
                "selected_candidate_hash": record["selected_candidate_hash"],
                "configuration_hash": record["configuration_hash"],
                "piece_count": metrics["piece_count"],
                "metrics": metrics["metrics"],
                "rows_path": metadata["rows_path"],
                "rows_sha256": metadata["rows_sha256"],
            }
            gtzan_records.append(result)
            append_piece_ledger(
                piece_rows,
                metadata,
                {
                    "label": record["label"],
                    "family": record["family"],
                    "tuning_size": record["tuning_size"],
                    "tuning_folds": ",".join(map(str, record["tuning_folds"])),
                    "selected_candidate_hash": record["selected_candidate_hash"] or "",
                    "configuration_hash": record["configuration_hash"],
                },
                base.METRICS,
                "gtzan_final1",
            )
            write_panel_outputs(base, output, protocol_hash, "gtzan_final1", gtzan_records)

        base.atomic_write_gzip_csv(
            output / "gtzan_final1_per_piece.csv.gz", piece_rows, tuple(piece_rows[0])
        )

        baselines = {
            "protocol_hash": protocol_hash,
            "method": "Beat This Direct",
            "configuration_hash": direct_configuration_hash,
            "smc_fold0": {"piece_count": direct_smc["piece_count"], "metrics": direct_smc["metrics"]},
            "gtzan_final1": {"piece_count": direct_gtzan["piece_count"], "metrics": direct_gtzan["metrics"]},
        }
        base.atomic_write_json(output / "fixed_panel_direct_baselines.json", baselines)
        baseline_rows: list[dict[str, Any]] = []
        for panel, payload, metrics in (
            ("smc_fold0", direct_smc, base.BEAT_METRICS),
            ("gtzan_final1", direct_gtzan, base.METRICS),
        ):
            row = {"panel": panel, "piece_count": payload["piece_count"]}
            row.update({metric: payload["metrics"].get(metric) for metric in base.METRICS})
            baseline_rows.append(row)
        base.atomic_write_csv(output / "fixed_panel_direct_baselines.csv", baseline_rows, tuple(baseline_rows[0]))

        smc_by_label = {record["label"]: record for record in smc_records}
        gtzan_by_label = {record["label"]: record for record in gtzan_records}
        combined_rows: list[dict[str, Any]] = [{
            "label": "direct",
            "family": "direct",
            "tuning_size": 0,
            "tuning_folds": "",
            "selected_candidate_hash": "",
            "configuration_hash": direct_configuration_hash,
            "selected_parameters": "{}",
            "smc_piece_count": direct_smc["piece_count"],
            "gtzan_piece_count": direct_gtzan["piece_count"],
            **{f"smc_{metric}": direct_smc["metrics"].get(metric) for metric in base.BEAT_METRICS},
            **{f"gtzan_{metric}": direct_gtzan["metrics"].get(metric) for metric in base.METRICS},
        }]
        for record in records:
            smc_result = smc_by_label[record["label"]]
            gtzan_result = gtzan_by_label[record["label"]]
            row = {
                "label": record["label"],
                "family": record["family"],
                "tuning_size": record["tuning_size"],
                "tuning_folds": ",".join(map(str, record["tuning_folds"])),
                "selected_candidate_hash": record["selected_candidate_hash"] or "",
                "configuration_hash": record["configuration_hash"],
                "selected_parameters": base.canonical_json(record["selected_parameters"] or {}),
                "smc_piece_count": smc_result["piece_count"],
                "gtzan_piece_count": gtzan_result["piece_count"],
            }
            row.update({f"smc_{metric}": smc_result["metrics"][metric] for metric in base.BEAT_METRICS})
            row.update({f"gtzan_{metric}": gtzan_result["metrics"][metric] for metric in base.METRICS})
            combined_rows.append(row)
        base.atomic_write_csv(
            output / "fixed_panel_combination_results.csv", combined_rows, tuple(combined_rows[0])
        )
        base.atomic_write_json(
            output / "fixed_panel_combination_results.json",
            {"protocol_hash": protocol_hash, "row_count": len(combined_rows), "rows": combined_rows},
        )

        uncertainty = bootstrap_summary(base, smc_records, gtzan_records)
        base.atomic_write_json(output / "across_combination_summary.json", uncertainty)
        summary_rows: list[dict[str, Any]] = []
        for family, family_result in uncertainty["families"].items():
            for panel, panel_result in family_result["panels"].items():
                for metric, values in panel_result["metrics"].items():
                    interval = values["descriptive_bootstrap_ci95"]
                    summary_rows.append({
                        "family": family,
                        "tuning_size": family_result["tuning_size"],
                        "combination_count": family_result["combination_count"],
                        "panel": panel,
                        "metric": metric,
                        "mean": values["mean"],
                        "population_sd": values["population_sd"],
                        "descriptive_ci95_low": interval[0] if interval else None,
                        "descriptive_ci95_high": interval[1] if interval else None,
                    })
        base.atomic_write_csv(output / "across_combination_summary.csv", summary_rows, tuple(summary_rows[0]))

        key_files = [
            "PREREGISTERED_PROTOCOL.json",
            "input_inventory.json",
            "selection_inventory_folds1_7.json",
            "smc_fold0_inventory.json",
            "combination_selection_results.json",
            "combination_selection_results.csv",
            "FROZEN_COMBINATIONS_LOCK.json",
            "smc_fold0_results.json",
            "smc_fold0_results.csv",
            "smc_fold0_per_piece.csv.gz",
            "gtzan_final1_inventory.json",
            "gtzan_final1_results.json",
            "gtzan_final1_results.csv",
            "gtzan_final1_per_piece.csv.gz",
            "fixed_panel_direct_baselines.json",
            "fixed_panel_direct_baselines.csv",
            "fixed_panel_combination_results.json",
            "fixed_panel_combination_results.csv",
            "across_combination_summary.json",
            "across_combination_summary.csv",
        ]
        artifact_manifest = {
            "protocol_hash": protocol_hash,
            "frozen_lock_hash": frozen_lock["payload_hash"],
            "files": [
                {"path": name, "size": (output / name).stat().st_size, "sha256": base.file_sha256(output / name)}
                for name in key_files
            ],
            "private_selection_registry_complete_candidates": len(list((output / "candidate_registry").glob("*/COMPLETE"))),
            "private_smc_registry_complete_candidates": len(list((output / "candidate_registry_smc_fold0").glob("*/COMPLETE"))),
            "sealed_registry_receipt": registry,
        }
        artifact_manifest["manifest_payload_hash"] = base.object_sha256(artifact_manifest)
        base.atomic_write_json(output / "ARTIFACT_MANIFEST.json", artifact_manifest)
        complete_payload = {
            "pid": os.getpid(),
            "host": platform.node(),
            "completed_at": base.now_iso(),
            "elapsed_seconds": time.time() - started,
            "protocol_hash": protocol_hash,
            "frozen_lock_hash": frozen_lock["payload_hash"],
            "artifact_manifest_sha256": base.file_sha256(output / "ARTIFACT_MANIFEST.json"),
            "combination_count": len(records),
            "smc_fold0_piece_count": smc_fold0_inventory["piece_count"],
            "gtzan_piece_count": gtzan_inventory["piece_count"],
            "unique_configuration_count": len({record["configuration_hash"] for record in records}),
        }
        base.atomic_write_json(output / "COMPLETE", complete_payload)
        (output / "RUNNING").unlink(missing_ok=True)
    except BaseException as exc:
        failure = {
            "pid": os.getpid(),
            "host": platform.node(),
            "failed_at": base.now_iso(),
            "elapsed_seconds": time.time() - started,
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "traceback": traceback.format_exc(),
        }
        base.atomic_write_json(output / "FAILED", failure)
        (output / "RUNNING").unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
