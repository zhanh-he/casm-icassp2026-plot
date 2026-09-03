#!/usr/bin/env python3
"""Create a compact, mtime-preserving QA bundle for the fixed-fold0 run."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


TOP_LEVEL_FILES = (
    "COMMAND.json",
    "PID",
    "PREREGISTERED_PROTOCOL.json",
    "PREREGISTERED_PROTOCOL.sha256",
    "input_inventory.json",
    "selection_inventory_folds1_7.json",
    "smc_fold0_inventory.json",
    "combination_selection_results.json",
    "combination_selection_results.csv",
    "SEARCH_PROGRESS.json",
    "FROZEN_COMBINATIONS_LOCK.json",
    "FROZEN_LOCKED",
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
    "ARTIFACT_MANIFEST.json",
    "COMPLETE",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sealed-registry", type=Path, required=True)
    parser.add_argument("--support-file", type=Path, action="append", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    formal = args.formal_root.resolve()
    run_root = args.run_root.resolve()
    output = args.output.resolve()
    sealed_registry = args.sealed_registry.resolve()
    if not (formal / "COMPLETE").is_file() or (formal / "RUNNING").exists():
        raise RuntimeError("Formal run is not COMPLETE")
    if output.exists():
        raise RuntimeError(f"Refusing existing bundle output: {output}")
    output.mkdir(parents=True)

    sources: list[tuple[Path, Path, str]] = []
    for name in TOP_LEVEL_FILES:
        source = formal / name
        if not source.is_file():
            raise FileNotFoundError(source)
        sources.append((source, Path("formal") / name, "formal-artifact"))
    for source in sorted((formal / "searches").rglob("*")):
        if source.is_file():
            role = "selection-stage-score-table" if source.suffix == ".csv" else "selection-trace"
            sources.append((source, Path("formal") / source.relative_to(formal), role))

    selection_payload = json.loads((formal / "combination_selection_results.json").read_text())
    selected_sources: dict[str, dict[str, Any]] = {}
    for combination in selection_payload["combinations"]:
        candidate_hash = combination.get("selected_candidate_hash")
        if not candidate_hash:
            continue
        candidate_hash = str(candidate_hash)
        if candidate_hash in selected_sources:
            continue
        private_candidate = formal / "candidate_registry" / candidate_hash
        sealed_candidate = sealed_registry / candidate_hash
        if (private_candidate / "COMPLETE").is_file():
            candidate_root = private_candidate
            origin = "formal-private-registry"
        elif (sealed_candidate / "COMPLETE").is_file():
            candidate_root = sealed_candidate
            origin = "sealed-918-registry"
        else:
            raise RuntimeError(f"Selected candidate is absent from both registries: {candidate_hash}")
        selected_sources[candidate_hash] = {
            "origin": origin,
            "source_root": str(candidate_root),
        }
        for name in ("params.json", "pieces.csv", "summary.json", "COMPLETE"):
            source = candidate_root / name
            if not source.is_file():
                raise FileNotFoundError(source)
            sources.append(
                (
                    source,
                    Path("selected_oof_candidates") / candidate_hash / name,
                    f"selected-oof-candidate-{origin}",
                )
            )
    for relative, role in (
        (Path("code") / "run_casm_fixed_fold0_exhaustive_combinations.py", "formal-code"),
        (Path("code") / "run_casm_fixed_fold0_exhaustive_combinations.mock1_6a8c004a.py", "rejected-mock-code"),
        (Path("logs") / "mock.log", "rejected-mock-log"),
        (Path("logs") / "mock_v2.log", "accepted-mock-log"),
        (Path("logs") / "formal.log", "formal-log"),
        (Path("FORMAL_LAUNCH_RECEIPT.txt"), "launch-receipt"),
    ):
        source = run_root / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        sources.append((source, Path("run") / relative, role))
    for source in args.support_file:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        sources.append((source, Path("support") / source.name, "support-code"))

    records: list[dict[str, Any]] = []
    for source, relative, role in sources:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        stat = destination.stat()
        records.append(
            {
                "path": relative.as_posix(),
                "role": role,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": sha256(destination),
                "source_path": str(source),
            }
        )

    selected_source_path = output / "SELECTED_CANDIDATE_SOURCES.json"
    selected_source_path.write_text(
        json.dumps(
            {
                "selected_unique_candidate_count": len(selected_sources),
                "candidates": selected_sources,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    selected_source_stat = selected_source_path.stat()
    records.append(
        {
            "path": "SELECTED_CANDIDATE_SOURCES.json",
            "role": "selected-candidate-provenance",
            "size": selected_source_stat.st_size,
            "mtime_ns": selected_source_stat.st_mtime_ns,
            "sha256": sha256(selected_source_path),
            "source_path": None,
        }
    )

    frozen_copy = output / "formal/FROZEN_COMBINATIONS_LOCK.json"
    frozen_sidecar = output / "formal/FROZEN_COMBINATIONS_LOCK.json.sha256"
    frozen_sidecar.write_text(
        f"{sha256(frozen_copy)}  FROZEN_COMBINATIONS_LOCK.json\n",
        encoding="utf-8",
    )
    sidecar_stat = frozen_sidecar.stat()
    records.append(
        {
            "path": "formal/FROZEN_COMBINATIONS_LOCK.json.sha256",
            "role": "bundle-derived-lock-hash-sidecar",
            "size": sidecar_stat.st_size,
            "mtime_ns": sidecar_stat.st_mtime_ns,
            "sha256": sha256(frozen_sidecar),
            "source_path": None,
        }
    )

    lock_record = next(record for record in records if record["path"] == "formal/FROZEN_COMBINATIONS_LOCK.json")
    smc_score_paths = {
        "formal/smc_fold0_results.json",
        "formal/smc_fold0_results.csv",
        "formal/smc_fold0_per_piece.csv.gz",
    }
    gtzan_score_paths = {
        "formal/gtzan_final1_results.json",
        "formal/gtzan_final1_results.csv",
        "formal/gtzan_final1_per_piece.csv.gz",
    }
    smc_records = [record for record in records if record["path"] in smc_score_paths]
    gtzan_records = [record for record in records if record["path"] in gtzan_score_paths]
    first_smc = min(record["mtime_ns"] for record in smc_records)
    first_gtzan = min(record["mtime_ns"] for record in gtzan_records)
    if not lock_record["mtime_ns"] < first_smc or not lock_record["mtime_ns"] < first_gtzan:
        raise RuntimeError("Frozen-lock mtime is not earlier than both fixed-panel outputs")
    lock_receipt = {
        "frozen_lock_mtime_ns": lock_record["mtime_ns"],
        "first_smc_output_mtime_ns": first_smc,
        "first_gtzan_output_mtime_ns": first_gtzan,
        "lock_before_smc": lock_record["mtime_ns"] < first_smc,
        "lock_before_gtzan": lock_record["mtime_ns"] < first_gtzan,
    }
    lock_receipt_path = output / "LOCK_ORDER_RECEIPT.json"
    lock_receipt_path.write_text(json.dumps(lock_receipt, indent=2, sort_keys=True) + "\n")
    lock_stat = lock_receipt_path.stat()
    records.append(
        {
            "path": "LOCK_ORDER_RECEIPT.json",
            "role": "bundle-derived-lock-order-receipt",
            "size": lock_stat.st_size,
            "mtime_ns": lock_stat.st_mtime_ns,
            "sha256": sha256(lock_receipt_path),
            "source_path": None,
        }
    )
    manifest = {
        "schema_version": "structbeat.casm.fixed-fold0.qa-bundle.v1",
        "formal_root": str(formal),
        "run_root": str(run_root),
        "file_count": len(records),
        "lock_order": lock_receipt,
        "files": records,
    }
    manifest["manifest_payload_hash"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path = output / "BUNDLE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (output / "BUNDLE_MANIFEST.json.sha256").write_text(f"{sha256(manifest_path)}  BUNDLE_MANIFEST.json\n")
    print(json.dumps({"bundle": str(output), "file_count": len(records), "manifest_sha256": sha256(manifest_path), **lock_receipt}, sort_keys=True))


if __name__ == "__main__":
    main()
