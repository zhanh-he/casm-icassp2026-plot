#!/usr/bin/env python3
"""Independent Gadi QA for fixed-fold0 exhaustive CASM scaling results.

The consumer is deliberately independent of the experiment driver.  It reads a
compact checksummed bundle, validates the preregistered C(7,k) design, verifies
that all 64 CASM configurations were frozen before either fixed-panel score was
written, and recomputes every published macro score and across-combination
summary from the two per-piece ledgers.

Formal QA expects 27 SMC fold-0 pieces, 993 GTZAN final1 pieces, 100,000
combination-unit bootstrap replicates, and seed 20260902.  ``--self-test`` is a
small dependency-free smoke check; it never creates or labels experimental
results.
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import gzip
import hashlib
import itertools
import json
import math
import os
import platform
import random
import statistics
import tempfile
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


QA_SCHEMA = "structbeat.casm.fixed-fold0-exhaustive.gadi-qa.v1"
BUNDLE_SCHEMA = "structbeat.casm.fixed-fold0.qa-bundle.v1"
PROTOCOL_NAME = "casm-fixed-fold0-exhaustive-combination-scaling-v1"
DEVELOPMENT_FOLDS = tuple(range(1, 8))
FAMILY_NAMES = {
    1: "exhaustive_1f",
    2: "exhaustive_2f",
    4: "exhaustive_4f",
    7: "exhaustive_7f",
}
FAMILY_COUNTS = {1: 7, 2: 21, 4: 35, 7: 1}
METRICS = (
    "beat_fmeasure",
    "beat_cmlt",
    "beat_amlt",
    "downbeat_fmeasure",
    "downbeat_cmlt",
    "downbeat_amlt",
)
BEAT_METRICS = METRICS[:3]
FORMAL_SMC_PIECES = 27
FORMAL_GTZAN_PIECES = 993
FORMAL_RESAMPLES = 100_000
FORMAL_SEED = 20260902


def expected_design() -> tuple[tuple[str, str, int, tuple[int, ...]], ...]:
    rows: list[tuple[str, str, int, tuple[int, ...]]] = []
    for size in (1, 2, 4, 7):
        family = FAMILY_NAMES[size]
        for folds in itertools.combinations(DEVELOPMENT_FOLDS, size):
            label = f"{size}f_" + "_".join(map(str, folds))
            rows.append((label, family, size, folds))
    return tuple(rows)


DESIGN = expected_design()
DESIGN_BY_LABEL = {
    label: {"family": family, "tuning_size": size, "folds": folds}
    for label, family, size, folds in DESIGN
}
ORDERED_LABELS = tuple(label for label, _family, _size, _folds in DESIGN)
ALL_METHOD_LABELS = ("direct", *ORDERED_LABELS)

REQUIRED_BUNDLE_FILES = {
    "PREREGISTERED_PROTOCOL.json",
    "PREREGISTERED_PROTOCOL.sha256",
    "input_inventory.json",
    "selection_inventory_folds1_7.json",
    "smc_fold0_inventory.json",
    "combination_selection_results.json",
    "combination_selection_results.csv",
    "FROZEN_COMBINATIONS_LOCK.json",
    "FROZEN_COMBINATIONS_LOCK.json.sha256",
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
}

EVALUATION_FILES = {
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
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def object_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(
        path,
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n",
    )


def atomic_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Iterable[str]
) -> None:
    fieldnames = tuple(fields)
    if not rows:
        raise ValueError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_float(value: Any, label: str, *, allow_null: bool = False) -> float | None:
    if value is None or str(value).strip().lower() in {"", "none", "null", "na", "n/a"}:
        if allow_null:
            return None
        raise RuntimeError(f"Missing numeric value for {label}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid numeric value for {label}: {value!r}") from exc
    if not math.isfinite(result):
        raise RuntimeError(f"Non-finite numeric value for {label}: {result!r}")
    return result


def require_close(
    actual: Any,
    expected: Any,
    label: str,
    *,
    tolerance: float = 1e-12,
    allow_null: bool = False,
) -> None:
    observed = parse_float(actual, label, allow_null=allow_null)
    target = parse_float(expected, f"expected {label}", allow_null=allow_null)
    if observed is None or target is None:
        if observed is not None or target is not None:
            raise RuntimeError(f"{label} null mismatch: {observed!r} != {target!r}")
        return
    if abs(observed - target) > tolerance:
        raise RuntimeError(
            f"{label} mismatch: actual={observed!r}, expected={target!r}, "
            f"tolerance={tolerance}"
        )


def require_int(actual: Any, expected: int, label: str) -> None:
    try:
        observed = int(actual)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not an integer: {actual!r}") from exc
    if observed != expected:
        raise RuntimeError(f"{label} mismatch: {observed} != {expected}")


def require_score(value: Any, label: str) -> float:
    result = parse_float(value, label)
    assert result is not None
    if not 0.0 <= result <= 1.0:
        raise RuntimeError(f"Score outside [0,1] for {label}: {result}")
    return result


def parse_folds(value: Any) -> tuple[int, ...]:
    if isinstance(value, list):
        return tuple(int(item) for item in value)
    text = "" if value is None else str(value).strip()
    return tuple(int(item) for item in text.split(",") if item.strip())


def safe_bundle_file(root: Path, relative: str) -> Path:
    supplied = Path(relative)
    if supplied.is_absolute() or ".." in supplied.parts:
        raise RuntimeError(f"Unsafe bundle path: {relative!r}")
    unresolved = root / supplied
    if unresolved.is_symlink():
        raise RuntimeError(f"Bundle input may not be a symlink: {relative!r}")
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"Bundle path escapes root: {relative!r}") from exc
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def verify_bundle(
    root: Path, manifest_path: Path, declared_sha256: str
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Path]]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    if (root / "RUNNING").exists() or (root / "FAILED").exists():
        raise RuntimeError("Bundle source is not cleanly terminal: RUNNING/FAILED exists")
    if not valid_sha256(declared_sha256):
        raise ValueError("--manifest-sha256 must be a lowercase SHA-256")
    if file_sha256(manifest_path) != declared_sha256:
        raise RuntimeError("Independently supplied bundle-manifest SHA-256 mismatch")
    sidecar = manifest_path.with_suffix(manifest_path.suffix + ".sha256")
    if sidecar.is_file():
        if sidecar.read_text(encoding="utf-8").split()[0] != declared_sha256:
            raise RuntimeError("Bundle-manifest sidecar mismatch")

    payload = json_file(manifest_path)
    claimed_payload_hash = payload.get("manifest_payload_hash")
    unhashed = copy.deepcopy(payload)
    unhashed.pop("manifest_payload_hash", None)
    if object_sha256(unhashed) != claimed_payload_hash:
        raise RuntimeError("Bundle-manifest payload hash mismatch")
    if payload.get("schema_version") != BUNDLE_SCHEMA:
        raise RuntimeError(f"Unexpected bundle schema: {payload.get('schema_version')!r}")
    records = payload.get("files")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Bundle manifest has no file records")
    require_int(payload.get("file_count"), len(records), "bundle manifest file count")

    all_records: dict[str, dict[str, Any]] = {}
    all_paths: dict[str, Path] = {}
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("Malformed bundle file record")
        relative = str(record.get("path", ""))
        if not relative or relative in all_records:
            raise RuntimeError(f"Empty or duplicate bundle file path: {relative!r}")
        declared_file_sha = record.get("sha256")
        if not valid_sha256(declared_file_sha):
            raise RuntimeError(f"Invalid bundle SHA-256 for {relative}")
        if not isinstance(record.get("mtime_ns"), int) or int(record["mtime_ns"]) <= 0:
            raise RuntimeError(f"Bundle record lacks source mtime_ns for {relative}")
        path = safe_bundle_file(root, relative)
        require_int(path.stat().st_size, int(record.get("size", -1)), f"size {relative}")
        actual_sha = file_sha256(path)
        if actual_sha != declared_file_sha:
            raise RuntimeError(
                f"Bundle SHA-256 mismatch for {relative}: {actual_sha} != {declared_file_sha}"
            )
        all_records[relative] = record
        all_paths[relative] = path

    by_name: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for relative, record in all_records.items():
        if not relative.startswith("formal/"):
            continue
        logical = relative.removeprefix("formal/")
        if "/" in logical:
            continue
        if logical in by_name:
            raise RuntimeError(f"Duplicate formal top-level artifact: {logical}")
        by_name[logical] = record
        paths[logical] = all_paths[relative]

    missing = REQUIRED_BUNDLE_FILES - set(by_name)
    if missing:
        raise RuntimeError(f"Bundle is missing required files: {sorted(missing)}")
    return payload, by_name, paths


def validate_protocol(paths: dict[str, Path], smc_pieces: int, gtzan_pieces: int) -> dict[str, Any]:
    protocol = json_file(paths["PREREGISTERED_PROTOCOL.json"])
    protocol_hash = protocol.get("protocol_hash")
    if not valid_sha256(protocol_hash):
        raise RuntimeError("Invalid protocol hash")
    unhashed = copy.deepcopy(protocol)
    unhashed.pop("protocol_hash", None)
    if object_sha256(unhashed) != protocol_hash:
        raise RuntimeError("Preregistered protocol object hash mismatch")
    sidecar = paths["PREREGISTERED_PROTOCOL.sha256"].read_text(encoding="utf-8").split()[0]
    if sidecar != protocol_hash:
        raise RuntimeError("Preregistered protocol sidecar mismatch")
    if protocol.get("name") != PROTOCOL_NAME:
        raise RuntimeError(f"Unexpected protocol name: {protocol.get('name')!r}")
    if not protocol.get("mock") is False and not getattr(validate_protocol, "allow_mock", False):
        raise RuntimeError("Formal protocol is marked mock")

    design = protocol.get("design", {})
    require_int(design.get("permanently_held_out_smc_fold"), 0, "held-out SMC fold")
    if tuple(design.get("development_fold_universe", [])) != DEVELOPMENT_FOLDS:
        raise RuntimeError("Development fold universe is not exactly folds 1..7")
    require_int(design.get("total_combinations"), 64, "protocol total combinations")
    if design.get("combination_counts") != {"1f": 7, "2f": 21, "4f": 35, "7f": 1}:
        raise RuntimeError("Protocol family counts differ from 7/21/35/1")
    observed: dict[str, tuple[int, ...]] = {}
    for size in (1, 2, 4, 7):
        for item in design.get("families", {}).get(f"{size}f", []):
            observed[str(item["label"])] = tuple(int(fold) for fold in item["folds"])
    expected = {label: detail["folds"] for label, detail in DESIGN_BY_LABEL.items()}
    if observed != expected:
        raise RuntimeError("Protocol does not enumerate the exact exhaustive C(7,k) design")

    selection = protocol.get("selection_inventory", {})
    require_int(selection.get("fold0_piece_count"), 0, "protocol selection fold0 count")
    if "fold0" in selection.get("partition_counts", {}):
        raise RuntimeError("Protocol selection partition counts leak fold0")
    panels = protocol.get("fixed_evaluation_panels", {})
    require_int(panels.get("smc_fold0", {}).get("piece_count"), smc_pieces, "protocol SMC pieces")
    require_int(panels.get("gtzan_final1", {}).get("piece_count"), gtzan_pieces, "protocol GTZAN pieces")
    if panels.get("smc_fold0", {}).get("used_for_selection") is not False:
        raise RuntimeError("SMC fold0 is not declared selection-invisible")
    if panels.get("gtzan_final1", {}).get("used_for_selection") is not False:
        raise RuntimeError("GTZAN final1 is not declared selection-invisible")
    gtzan = protocol.get("gtzan", {})
    require_int(gtzan.get("checkpoint_seed"), 1, "protocol GTZAN seed")
    if gtzan.get("gtzan_used_for_casm_parameter_selection") is not False:
        raise RuntimeError("Protocol says GTZAN was used for CASM selection")
    if gtzan.get("eligible_for_clean_test_claim") is not False:
        raise RuntimeError("Test-conditioned final1 must not be marked clean-test eligible")
    uncertainty = protocol.get("uncertainty", {})
    if uncertainty.get("unit") != "fold combination":
        raise RuntimeError("Protocol uncertainty unit mismatch")
    return protocol


def inventory_fingerprint(entries: list[dict[str, Any]]) -> str:
    fields = ("path", "piece", "dataset", "partition", "size", "mtime_ns")
    payload = [{field: entry[field] for field in fields} for entry in entries]
    return object_sha256(payload)


def validate_inventory(
    inventory: dict[str, Any],
    *,
    expected_count: int,
    allowed_partitions: set[str],
    expected_dataset: str | None,
    label: str,
) -> set[tuple[str, str]]:
    entries = inventory.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError(f"{label} inventory has no entries")
    require_int(inventory.get("piece_count"), expected_count, f"{label} piece count")
    if len(entries) != expected_count:
        raise RuntimeError(f"{label} inventory entry count mismatch")
    identities = [(str(item["piece"]), str(item["partition"])) for item in entries]
    if len(set(identities)) != expected_count:
        raise RuntimeError(f"{label} inventory contains duplicate piece/partition identities")
    partitions = Counter(partition for _piece, partition in identities)
    if set(partitions) - allowed_partitions:
        raise RuntimeError(f"{label} inventory contains unexpected partitions: {partitions}")
    if inventory.get("partition_counts") != dict(partitions):
        raise RuntimeError(f"{label} partition count metadata mismatch")
    datasets = Counter(str(item.get("dataset", "")).lower() for item in entries)
    if expected_dataset is not None and datasets != {expected_dataset: expected_count}:
        raise RuntimeError(f"{label} dataset identity mismatch: {datasets}")
    if inventory.get("dataset_counts") != dict(datasets):
        raise RuntimeError(f"{label} dataset count metadata mismatch")
    if "fingerprint" in inventory and inventory["fingerprint"] != inventory_fingerprint(entries):
        raise RuntimeError(f"{label} inventory fingerprint mismatch")
    return set(identities)


def validate_inventories(
    paths: dict[str, Path], smc_pieces: int, gtzan_pieces: int, allow_fixture: bool
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    full = json_file(paths["input_inventory.json"])
    if not allow_fixture:
        require_int(full.get("piece_count"), 4556, "full OOF piece count")
        if set(full.get("partition_counts", {})) != {f"fold{fold}" for fold in range(8)}:
            raise RuntimeError("Full OOF inventory does not contain exactly folds 0..7")

    selection = json_file(paths["selection_inventory_folds1_7.json"])
    selection_entries = selection.get("entries", [])
    if not selection_entries:
        raise RuntimeError("Selection inventory is empty")
    if any(str(item.get("partition")) == "fold0" for item in selection_entries):
        raise RuntimeError("Fold0 leakage in selection inventory entries")
    if set(selection.get("partition_counts", {})) - {f"fold{fold}" for fold in DEVELOPMENT_FOLDS}:
        raise RuntimeError("Selection inventory contains a partition outside folds 1..7")
    require_int(selection.get("piece_count"), len(selection_entries), "selection inventory count")
    if "fingerprint" in selection and selection["fingerprint"] != inventory_fingerprint(selection_entries):
        raise RuntimeError("Selection inventory fingerprint mismatch")

    smc_identities = validate_inventory(
        json_file(paths["smc_fold0_inventory.json"]),
        expected_count=smc_pieces,
        allowed_partitions={"fold0"},
        expected_dataset="smc",
        label="SMC fold0",
    )
    gtzan_identities = validate_inventory(
        json_file(paths["gtzan_final1_inventory.json"]),
        expected_count=gtzan_pieces,
        allowed_partitions={"seed1"},
        expected_dataset=None,
        label="GTZAN final1",
    )
    if {partition for _piece, partition in gtzan_identities} != {"seed1"}:
        raise RuntimeError("GTZAN inventory is not exclusively seed1")
    if len({piece for piece, _partition in gtzan_identities}) != gtzan_pieces:
        raise RuntimeError("GTZAN final1 inventory repeats piece IDs")
    return smc_identities, gtzan_identities


def configuration_identity(record: dict[str, Any], label: str) -> tuple[str, str]:
    identity = bool(record.get("identity"))
    parameters = record.get("selected_parameters")
    if identity:
        if record.get("selected_candidate_hash") is not None or parameters not in (None, {}):
            raise RuntimeError(f"Identity candidate fields inconsistent for {label}")
        decoder = "minimal"
        parameters = {}
        candidate = ""
    else:
        if not isinstance(parameters, dict):
            raise RuntimeError(f"CASM selected parameters missing for {label}")
        expected_candidate = object_sha256(parameters)
        if record.get("selected_candidate_hash") != expected_candidate:
            raise RuntimeError(f"Selected candidate hash mismatch for {label}")
        decoder = "casm"
        candidate = expected_candidate
    expected_configuration = object_sha256({"decoder": decoder, "parameters": parameters})
    if record.get("configuration_hash") != expected_configuration:
        raise RuntimeError(f"Configuration hash mismatch for {label}")
    return candidate, expected_configuration


def validate_selections_and_lock(
    paths: dict[str, Path], protocol_hash: str
) -> dict[str, dict[str, Any]]:
    payload = json_file(paths["combination_selection_results.json"])
    if payload.get("protocol_hash") != protocol_hash:
        raise RuntimeError("Selection results protocol hash mismatch")
    require_int(payload.get("combination_count"), 64, "selection combination count")
    records = payload.get("combinations")
    if not isinstance(records, list) or len(records) != 64:
        raise RuntimeError("Selection JSON does not have exactly 64 combinations")
    by_label = {str(record.get("label")): record for record in records}
    if len(by_label) != 64 or set(by_label) != set(ORDERED_LABELS):
        raise RuntimeError("Selection labels do not match the exact exhaustive design")
    if Counter(record.get("family") for record in records) != Counter(
        {FAMILY_NAMES[size]: count for size, count in FAMILY_COUNTS.items()}
    ):
        raise RuntimeError("Selection family counts differ from 7/21/35/1")

    for label in ORDERED_LABELS:
        record = by_label[label]
        expected = DESIGN_BY_LABEL[label]
        if record.get("family") != expected["family"]:
            raise RuntimeError(f"Selection family mismatch for {label}")
        require_int(record.get("tuning_size"), expected["tuning_size"], f"{label} tuning size")
        if parse_folds(record.get("tuning_folds")) != expected["folds"]:
            raise RuntimeError(f"Selection tuning folds mismatch for {label}")
        if 0 in parse_folds(record.get("tuning_folds")):
            raise RuntimeError(f"Fold0 leakage in selection {label}")
        configuration_identity(record, label)
        development = record.get("development", {})
        if int(development.get("piece_count", 0)) <= 0:
            raise RuntimeError(f"Empty development aggregate for {label}")
        for subset, metrics in (("overall", METRICS), ("smc", BEAT_METRICS)):
            for metric in metrics:
                require_score(development.get(subset, {}).get(metric), f"{label} development {subset}.{metric}")

    selection_csv = read_csv(paths["combination_selection_results.csv"])
    if len(selection_csv) != 64 or {row.get("label") for row in selection_csv} != set(ORDERED_LABELS):
        raise RuntimeError("Selection CSV does not match the 64 JSON labels")
    csv_by_label = {row["label"]: row for row in selection_csv}
    for label, record in by_label.items():
        row = csv_by_label[label]
        if parse_folds(row.get("tuning_folds")) != DESIGN_BY_LABEL[label]["folds"]:
            raise RuntimeError(f"Selection CSV tuning folds mismatch for {label}")
        if row.get("configuration_hash") != record.get("configuration_hash"):
            raise RuntimeError(f"Selection CSV configuration hash mismatch for {label}")

    frozen = json_file(paths["FROZEN_COMBINATIONS_LOCK.json"])
    frozen_payload = frozen.get("payload")
    if not isinstance(frozen_payload, dict) or object_sha256(frozen_payload) != frozen.get("payload_hash"):
        raise RuntimeError("Frozen lock payload hash mismatch")
    if frozen_payload.get("protocol_hash") != protocol_hash:
        raise RuntimeError("Frozen lock protocol hash mismatch")
    require_int(frozen_payload.get("combination_count"), 64, "frozen combination count")
    locked_records = frozen_payload.get("configurations")
    if not isinstance(locked_records, list) or len(locked_records) != 64:
        raise RuntimeError("Frozen lock does not contain exactly 64 configurations")
    locked = {str(record.get("label")): record for record in locked_records}
    if set(locked) != set(ORDERED_LABELS):
        raise RuntimeError("Frozen lock labels differ from selection labels")
    compare_keys = (
        "family",
        "tuning_folds",
        "identity",
        "selected_candidate_hash",
        "configuration_hash",
        "selected_parameters",
    )
    for label in ORDERED_LABELS:
        for key in compare_keys:
            if locked[label].get(key) != by_label[label].get(key):
                raise RuntimeError(f"Frozen lock differs from selection for {label}.{key}")
    if frozen_payload.get("gtzan_checkpoint_seed") != 1:
        raise RuntimeError("Frozen lock GTZAN checkpoint is not final1")
    if frozen_payload.get("gtzan_used_for_selection") is not False:
        raise RuntimeError("Frozen lock says GTZAN was used for selection")
    if frozen_payload.get("smc_fold0_used_for_selection") is not False:
        raise RuntimeError("Frozen lock says SMC fold0 was used for selection")
    if frozen_payload.get("eligible_for_clean_test_claim") is not False:
        raise RuntimeError("Test-conditioned checkpoint is incorrectly marked clean")
    sidecar_value = paths["FROZEN_COMBINATIONS_LOCK.json.sha256"].read_text(encoding="utf-8").split()[0]
    marker_value = paths["FROZEN_LOCKED"].read_text(encoding="utf-8").split()[0]
    if sidecar_value != file_sha256(paths["FROZEN_COMBINATIONS_LOCK.json"]):
        raise RuntimeError("Bundle-derived frozen lock file-SHA sidecar mismatch")
    if marker_value != frozen.get("payload_hash"):
        raise RuntimeError("Frozen payload-hash marker mismatch")
    return by_label


def validate_chronology(
    bundle_manifest: dict[str, Any],
    manifest_files: dict[str, dict[str, Any]],
    frozen: dict[str, Any],
) -> dict[str, Any]:
    lock_mtime = int(manifest_files["FROZEN_COMBINATIONS_LOCK.json"]["mtime_ns"])
    violations = {
        name: int(manifest_files[name]["mtime_ns"])
        for name in EVALUATION_FILES
        if int(manifest_files[name]["mtime_ns"]) < lock_mtime
    }
    if violations:
        raise RuntimeError(
            f"Evaluation artifact predates frozen lock according to source mtime_ns: {violations}"
        )
    artifact_mtime = int(manifest_files["ARTIFACT_MANIFEST.json"]["mtime_ns"])
    complete_mtime = int(manifest_files["COMPLETE"]["mtime_ns"])
    if artifact_mtime < max(int(manifest_files[name]["mtime_ns"]) for name in EVALUATION_FILES):
        raise RuntimeError("ARTIFACT_MANIFEST predates a declared evaluation artifact")
    if complete_mtime < artifact_mtime:
        raise RuntimeError("COMPLETE predates ARTIFACT_MANIFEST")
    first_smc = min(
        int(manifest_files[name]["mtime_ns"])
        for name in (
            "smc_fold0_results.json",
            "smc_fold0_results.csv",
            "smc_fold0_per_piece.csv.gz",
        )
    )
    first_gtzan = min(
        int(manifest_files[name]["mtime_ns"])
        for name in (
            "gtzan_final1_results.json",
            "gtzan_final1_results.csv",
            "gtzan_final1_per_piece.csv.gz",
        )
    )
    declared_order = bundle_manifest.get("lock_order")
    expected_order = {
        "frozen_lock_mtime_ns": lock_mtime,
        "first_smc_output_mtime_ns": first_smc,
        "first_gtzan_output_mtime_ns": first_gtzan,
        "lock_before_smc": lock_mtime < first_smc,
        "lock_before_gtzan": lock_mtime < first_gtzan,
    }
    if declared_order != expected_order:
        raise RuntimeError("Bundle lock-order receipt differs from independently recomputed mtimes")
    if not expected_order["lock_before_smc"] or not expected_order["lock_before_gtzan"]:
        raise RuntimeError("Frozen lock is not strictly earlier than both fixed-panel outputs")
    locked_at = frozen.get("locked_at")
    if not isinstance(locked_at, str) or not locked_at:
        raise RuntimeError("Frozen lock lacks locked_at timestamp")
    return {
        "source_lock_mtime_ns": lock_mtime,
        "earliest_evaluation_mtime_ns": min(
            int(manifest_files[name]["mtime_ns"]) for name in EVALUATION_FILES
        ),
        "artifact_manifest_mtime_ns": artifact_mtime,
        "complete_mtime_ns": complete_mtime,
        "locked_at": locked_at,
        "verified_evaluation_file_count": len(EVALUATION_FILES),
        "bundle_lock_order": expected_order,
    }


def expected_method_identity(
    label: str, selections: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if label == "direct":
        return {
            "family": "direct",
            "tuning_size": 0,
            "tuning_folds": (),
            "selected_candidate_hash": "",
            "configuration_hash": object_sha256({"decoder": "minimal", "parameters": {}}),
        }
    record = selections[label]
    return {
        "family": record["family"],
        "tuning_size": record["tuning_size"],
        "tuning_folds": tuple(record["tuning_folds"]),
        "selected_candidate_hash": record.get("selected_candidate_hash") or "",
        "configuration_hash": record["configuration_hash"],
    }


def validate_ledger(
    path: Path,
    *,
    panel: str,
    metrics: tuple[str, ...],
    expected_identities: set[tuple[str, str]],
    selections: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, str]], int]:
    rows = read_csv(path)
    required = {
        "label",
        "family",
        "tuning_size",
        "tuning_folds",
        "selected_candidate_hash",
        "configuration_hash",
        "piece",
        "dataset",
        "partition",
        *metrics,
    }
    if not rows or not required.issubset(rows[0]):
        raise RuntimeError(f"{panel} per-piece ledger schema mismatch")
    expected_rows = len(ALL_METHOD_LABELS) * len(expected_identities)
    if len(rows) != expected_rows:
        raise RuntimeError(f"{panel} ledger row count mismatch: {len(rows)} != {expected_rows}")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["label"])].append(row)
    if set(grouped) != set(ALL_METHOD_LABELS):
        raise RuntimeError(f"{panel} ledger method labels mismatch")

    aggregates: dict[str, dict[str, float]] = {}
    identities_by_label: dict[str, dict[str, str]] = {}
    for label in ALL_METHOD_LABELS:
        group = grouped[label]
        observed_pairs = [(str(row["piece"]), str(row["partition"])) for row in group]
        if len(group) != len(expected_identities) or len(set(observed_pairs)) != len(group):
            raise RuntimeError(f"{panel}.{label} duplicate or missing rows")
        if set(observed_pairs) != expected_identities:
            raise RuntimeError(f"{panel}.{label} piece panel is not exactly aligned")
        identity = expected_method_identity(label, selections)
        expected_fields = {
            "family": str(identity["family"]),
            "tuning_size": str(identity["tuning_size"]),
            "tuning_folds": ",".join(map(str, identity["tuning_folds"])),
            "selected_candidate_hash": str(identity["selected_candidate_hash"]),
            "configuration_hash": str(identity["configuration_hash"]),
        }
        for field, expected in expected_fields.items():
            observed = {str(row.get(field, "")) for row in group}
            if observed != {expected}:
                raise RuntimeError(f"{panel}.{label} ledger {field} mismatch: {observed}")
        if panel == "smc_fold0":
            if {str(row["dataset"]).lower() for row in group} != {"smc"}:
                raise RuntimeError(f"{panel}.{label} contains a non-SMC row")
            if {str(row["partition"]) for row in group} != {"fold0"}:
                raise RuntimeError(f"{panel}.{label} contains a non-fold0 row")
        elif {str(row["partition"]) for row in group} != {"seed1"}:
            raise RuntimeError(f"{panel}.{label} contains a non-final1 row")
        aggregates[label] = {}
        for metric in metrics:
            values = [require_score(row[metric], f"{panel}.{label}.{metric}") for row in group]
            aggregates[label][metric] = statistics.fmean(values)
        identities_by_label[label] = expected_fields
    return aggregates, identities_by_label, len(rows)


def validate_panel_results(
    paths: dict[str, Path],
    *,
    stem: str,
    metrics: tuple[str, ...],
    piece_count: int,
    protocol_hash: str,
    selections: dict[str, dict[str, Any]],
    aggregates: dict[str, dict[str, float]],
) -> dict[str, dict[str, Any]]:
    payload = json_file(paths[f"{stem}_results.json"])
    if payload.get("protocol_hash") != protocol_hash:
        raise RuntimeError(f"{stem} result protocol hash mismatch")
    require_int(payload.get("combination_count"), 64, f"{stem} combination count")
    records = payload.get("combinations")
    if not isinstance(records, list) or len(records) != 64:
        raise RuntimeError(f"{stem} JSON does not contain exactly 64 CASM records")
    by_label = {str(record.get("label")): record for record in records}
    if set(by_label) != set(ORDERED_LABELS):
        raise RuntimeError(f"{stem} result labels mismatch")
    for label in ORDERED_LABELS:
        record = by_label[label]
        identity = expected_method_identity(label, selections)
        if record.get("family") != identity["family"]:
            raise RuntimeError(f"{stem}.{label} family mismatch")
        require_int(record.get("tuning_size"), int(identity["tuning_size"]), f"{stem}.{label} tuning size")
        if parse_folds(record.get("tuning_folds")) != identity["tuning_folds"]:
            raise RuntimeError(f"{stem}.{label} tuning folds mismatch")
        if (record.get("selected_candidate_hash") or "") != identity["selected_candidate_hash"]:
            raise RuntimeError(f"{stem}.{label} selected candidate hash mismatch")
        if record.get("configuration_hash") != identity["configuration_hash"]:
            raise RuntimeError(f"{stem}.{label} configuration hash mismatch")
        require_int(record.get("piece_count"), piece_count, f"{stem}.{label} piece count")
        if not valid_sha256(record.get("rows_sha256")):
            raise RuntimeError(f"{stem}.{label} rows_sha256 is invalid")
        for metric in metrics:
            require_close(
                aggregates[label][metric],
                record.get("metrics", {}).get(metric),
                f"{stem}.{label}.{metric}",
            )

    csv_rows = read_csv(paths[f"{stem}_results.csv"])
    if len(csv_rows) != 64 or {row.get("label") for row in csv_rows} != set(ORDERED_LABELS):
        raise RuntimeError(f"{stem} CSV label/count mismatch")
    csv_by_label = {row["label"]: row for row in csv_rows}
    for label in ORDERED_LABELS:
        row = csv_by_label[label]
        if row.get("configuration_hash") != by_label[label].get("configuration_hash"):
            raise RuntimeError(f"{stem}.{label} CSV configuration mismatch")
        require_int(row.get("piece_count"), piece_count, f"{stem}.{label} CSV piece count")
        for metric in metrics:
            require_close(row.get(metric), aggregates[label][metric], f"{stem}.{label} CSV {metric}")
    return by_label


def validate_direct_and_combined(
    paths: dict[str, Path],
    *,
    protocol_hash: str,
    smc_pieces: int,
    gtzan_pieces: int,
    selections: dict[str, dict[str, Any]],
    smc_aggregates: dict[str, dict[str, float]],
    gtzan_aggregates: dict[str, dict[str, float]],
) -> None:
    direct_hash = object_sha256({"decoder": "minimal", "parameters": {}})
    baselines = json_file(paths["fixed_panel_direct_baselines.json"])
    if baselines.get("protocol_hash") != protocol_hash or baselines.get("method") != "Beat This Direct":
        raise RuntimeError("Direct baseline identity/protocol mismatch")
    if baselines.get("configuration_hash") != direct_hash:
        raise RuntimeError("Direct baseline configuration hash mismatch")
    for panel, pieces, metrics, aggregates in (
        ("smc_fold0", smc_pieces, BEAT_METRICS, smc_aggregates),
        ("gtzan_final1", gtzan_pieces, METRICS, gtzan_aggregates),
    ):
        source = baselines.get(panel, {})
        require_int(source.get("piece_count"), pieces, f"Direct {panel} piece count")
        for metric in metrics:
            require_close(
                source.get("metrics", {}).get(metric),
                aggregates["direct"][metric],
                f"Direct {panel}.{metric}",
            )

    baseline_csv = read_csv(paths["fixed_panel_direct_baselines.csv"])
    if len(baseline_csv) != 2 or {row.get("panel") for row in baseline_csv} != {"smc_fold0", "gtzan_final1"}:
        raise RuntimeError("Direct baseline CSV panel mismatch")
    for row in baseline_csv:
        panel = row["panel"]
        pieces = smc_pieces if panel == "smc_fold0" else gtzan_pieces
        metrics = BEAT_METRICS if panel == "smc_fold0" else METRICS
        aggregates = smc_aggregates if panel == "smc_fold0" else gtzan_aggregates
        require_int(row.get("piece_count"), pieces, f"Direct CSV {panel} pieces")
        for metric in metrics:
            require_close(row.get(metric), aggregates["direct"][metric], f"Direct CSV {panel}.{metric}")

    combined = json_file(paths["fixed_panel_combination_results.json"])
    if combined.get("protocol_hash") != protocol_hash:
        raise RuntimeError("Combined fixed-panel protocol hash mismatch")
    require_int(combined.get("row_count"), 65, "combined row count")
    rows = combined.get("rows")
    if not isinstance(rows, list) or len(rows) != 65:
        raise RuntimeError("Combined JSON does not contain Direct plus 64 CASM rows")
    by_label = {str(row.get("label")): row for row in rows}
    if set(by_label) != set(ALL_METHOD_LABELS):
        raise RuntimeError("Combined JSON method labels mismatch")
    csv_rows = read_csv(paths["fixed_panel_combination_results.csv"])
    if len(csv_rows) != 65 or {row.get("label") for row in csv_rows} != set(ALL_METHOD_LABELS):
        raise RuntimeError("Combined CSV method labels mismatch")
    csv_by_label = {row["label"]: row for row in csv_rows}
    for label in ALL_METHOD_LABELS:
        identity = expected_method_identity(label, selections)
        row = by_label[label]
        csv_row = csv_by_label[label]
        for source_name, source in (("JSON", row), ("CSV", csv_row)):
            if source.get("configuration_hash") != identity["configuration_hash"]:
                raise RuntimeError(f"Combined {source_name} config hash mismatch for {label}")
            require_int(source.get("smc_piece_count"), smc_pieces, f"Combined {source_name} SMC pieces {label}")
            require_int(source.get("gtzan_piece_count"), gtzan_pieces, f"Combined {source_name} GTZAN pieces {label}")
            for metric in BEAT_METRICS:
                require_close(source.get(f"smc_{metric}"), smc_aggregates[label][metric], f"Combined {source_name} SMC {label}.{metric}")
            for metric in METRICS:
                require_close(source.get(f"gtzan_{metric}"), gtzan_aggregates[label][metric], f"Combined {source_name} GTZAN {label}.{metric}")


def summarize_values(values: list[float], seed_key: str, resamples: int, seed: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "mean": statistics.fmean(values),
        "population_sd": None,
        "descriptive_bootstrap_ci95": None,
    }
    if len(values) == 1:
        return result
    result["population_sd"] = statistics.pstdev(values)
    rng = random.Random(f"{seed}:{seed_key}")
    replicates = [
        sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        for _ in range(resamples)
    ]
    replicates.sort()
    result["descriptive_bootstrap_ci95"] = [
        replicates[int(0.025 * resamples)],
        replicates[int(0.975 * resamples) - 1],
    ]
    return result


def validate_summary(
    paths: dict[str, Path],
    *,
    smc_aggregates: dict[str, dict[str, float]],
    gtzan_aggregates: dict[str, dict[str, float]],
    resamples: int,
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    published = json_file(paths["across_combination_summary.json"])
    if published.get("resampling_unit") != "fold combination":
        raise RuntimeError("Published summary resampling unit mismatch")
    require_int(published.get("bootstrap_replicates"), resamples, "summary bootstrap replicates")
    require_int(published.get("bootstrap_seed"), seed, "summary bootstrap seed")
    families = published.get("families")
    if not isinstance(families, dict) or set(families) != set(FAMILY_NAMES.values()):
        raise RuntimeError("Published summary families mismatch")

    recomputed: dict[str, Any] = {}
    flat_rows: list[dict[str, Any]] = []
    for size in (1, 2, 4, 7):
        family = FAMILY_NAMES[size]
        labels = [label for label in ORDERED_LABELS if DESIGN_BY_LABEL[label]["family"] == family]
        source_family = families[family]
        require_int(source_family.get("tuning_size"), size, f"{family} tuning size")
        require_int(source_family.get("combination_count"), FAMILY_COUNTS[size], f"{family} count")
        recomputed[family] = {
            "tuning_size": size,
            "combination_count": len(labels),
            "panels": {},
        }
        for panel, aggregates, metrics in (
            ("smc_fold0", smc_aggregates, BEAT_METRICS),
            ("gtzan_final1", gtzan_aggregates, METRICS),
        ):
            recomputed[family]["panels"][panel] = {"metrics": {}}
            source_metrics = source_family.get("panels", {}).get(panel, {}).get("metrics", {})
            if set(source_metrics) != set(metrics):
                raise RuntimeError(f"{family}.{panel} summary metric set mismatch")
            for metric in metrics:
                values = [aggregates[label][metric] for label in labels]
                result = summarize_values(values, f"{family}:{panel}:{metric}", resamples, seed)
                source = source_metrics[metric]
                require_close(source.get("mean"), result["mean"], f"{family}.{panel}.{metric}.mean")
                require_close(
                    source.get("population_sd"),
                    result["population_sd"],
                    f"{family}.{panel}.{metric}.population_sd",
                    allow_null=True,
                )
                source_interval = source.get("descriptive_bootstrap_ci95")
                result_interval = result["descriptive_bootstrap_ci95"]
                if result_interval is None:
                    if source_interval is not None:
                        raise RuntimeError(f"{family}.{panel}.{metric} n=1 CI must be null")
                    if source.get("population_sd") is not None:
                        raise RuntimeError(f"{family}.{panel}.{metric} n=1 SD must be null")
                else:
                    if not isinstance(source_interval, list) or len(source_interval) != 2:
                        raise RuntimeError(f"{family}.{panel}.{metric} CI schema mismatch")
                    require_close(source_interval[0], result_interval[0], f"{family}.{panel}.{metric}.ci_low")
                    require_close(source_interval[1], result_interval[1], f"{family}.{panel}.{metric}.ci_high")
                recomputed[family]["panels"][panel]["metrics"][metric] = result
                flat_rows.append({
                    "family": family,
                    "tuning_size": size,
                    "combination_count": len(labels),
                    "panel": panel,
                    "metric": metric,
                    "mean": result["mean"],
                    "population_sd": result["population_sd"],
                    "descriptive_ci95_low": result_interval[0] if result_interval else None,
                    "descriptive_ci95_high": result_interval[1] if result_interval else None,
                })

    csv_rows = read_csv(paths["across_combination_summary.csv"])
    if len(csv_rows) != len(flat_rows):
        raise RuntimeError("Across-combination summary CSV row count mismatch")
    keyed_csv = {(row["family"], row["panel"], row["metric"]): row for row in csv_rows}
    if len(keyed_csv) != len(csv_rows):
        raise RuntimeError("Across-combination summary CSV has duplicate keys")
    for row in flat_rows:
        key = (row["family"], row["panel"], row["metric"])
        if key not in keyed_csv:
            raise RuntimeError(f"Missing summary CSV row: {key}")
        source = keyed_csv[key]
        require_int(source["combination_count"], row["combination_count"], f"summary CSV {key} count")
        for field in ("mean", "population_sd", "descriptive_ci95_low", "descriptive_ci95_high"):
            require_close(source.get(field), row[field], f"summary CSV {key}.{field}", allow_null=True)
    return recomputed, flat_rows


def validate_artifact_manifest(
    paths: dict[str, Path], protocol_hash: str, frozen_hash: str
) -> dict[str, Any]:
    artifact = json_file(paths["ARTIFACT_MANIFEST.json"])
    claimed_payload_hash = artifact.get("manifest_payload_hash")
    unhashed = copy.deepcopy(artifact)
    unhashed.pop("manifest_payload_hash", None)
    if object_sha256(unhashed) != claimed_payload_hash:
        raise RuntimeError("ARTIFACT_MANIFEST payload hash mismatch")
    if artifact.get("protocol_hash") != protocol_hash or artifact.get("frozen_lock_hash") != frozen_hash:
        raise RuntimeError("ARTIFACT_MANIFEST protocol/frozen identity mismatch")
    files = artifact.get("files")
    if not isinstance(files, list) or not files:
        raise RuntimeError("ARTIFACT_MANIFEST has no files")
    seen: set[str] = set()
    for record in files:
        relative = str(record.get("path", ""))
        if relative in seen or relative not in paths:
            raise RuntimeError(f"Invalid ARTIFACT_MANIFEST path: {relative!r}")
        seen.add(relative)
        path = paths[relative]
        require_int(path.stat().st_size, int(record.get("size", -1)), f"artifact size {relative}")
        if file_sha256(path) != record.get("sha256"):
            raise RuntimeError(f"ARTIFACT_MANIFEST SHA mismatch for {relative}")
    return artifact


def validate_complete(
    paths: dict[str, Path],
    *,
    protocol_hash: str,
    frozen_hash: str,
    smc_pieces: int,
    gtzan_pieces: int,
) -> dict[str, Any]:
    complete = json_file(paths["COMPLETE"])
    if complete.get("protocol_hash") != protocol_hash or complete.get("frozen_lock_hash") != frozen_hash:
        raise RuntimeError("COMPLETE protocol/frozen identity mismatch")
    if complete.get("artifact_manifest_sha256") != file_sha256(paths["ARTIFACT_MANIFEST.json"]):
        raise RuntimeError("COMPLETE does not bind ARTIFACT_MANIFEST")
    require_int(complete.get("combination_count"), 64, "COMPLETE combination count")
    require_int(complete.get("smc_fold0_piece_count"), smc_pieces, "COMPLETE SMC pieces")
    require_int(complete.get("gtzan_piece_count"), gtzan_pieces, "COMPLETE GTZAN pieces")
    unique_count = int(complete.get("unique_configuration_count", 0))
    if not 1 <= unique_count <= 64:
        raise RuntimeError("COMPLETE unique configuration count is invalid")
    return complete


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.bundle_root.resolve()
    manifest_path = args.bundle_manifest.resolve()
    bundle, manifest_files, paths = verify_bundle(root, manifest_path, args.manifest_sha256)
    pre_protocol = json_file(paths["PREREGISTERED_PROTOCOL.json"])
    if args.allow_synthetic_fixture:
        panels = pre_protocol.get("fixed_evaluation_panels", {})
        smc_pieces = int(panels.get("smc_fold0", {}).get("piece_count", -1))
        gtzan_pieces = int(panels.get("gtzan_final1", {}).get("piece_count", -1))
        if smc_pieces <= 0 or gtzan_pieces <= 0:
            raise RuntimeError("Synthetic fixture protocol has invalid panel counts")
    else:
        smc_pieces = FORMAL_SMC_PIECES
        gtzan_pieces = FORMAL_GTZAN_PIECES
        require_int(args.resamples, FORMAL_RESAMPLES, "formal bootstrap replicates")
        require_int(args.seed, FORMAL_SEED, "formal bootstrap seed")

    validate_protocol.allow_mock = bool(args.allow_synthetic_fixture)
    protocol = validate_protocol(paths, smc_pieces, gtzan_pieces)
    protocol_hash = protocol["protocol_hash"]
    smc_identities, gtzan_identities = validate_inventories(
        paths, smc_pieces, gtzan_pieces, args.allow_synthetic_fixture
    )
    selections = validate_selections_and_lock(paths, protocol_hash)
    frozen = json_file(paths["FROZEN_COMBINATIONS_LOCK.json"])
    chronology = validate_chronology(bundle, manifest_files, frozen)

    smc_aggregates, smc_ledger_identities, smc_row_count = validate_ledger(
        paths["smc_fold0_per_piece.csv.gz"],
        panel="smc_fold0",
        metrics=BEAT_METRICS,
        expected_identities=smc_identities,
        selections=selections,
    )
    gtzan_aggregates, gtzan_ledger_identities, gtzan_row_count = validate_ledger(
        paths["gtzan_final1_per_piece.csv.gz"],
        panel="gtzan_final1",
        metrics=METRICS,
        expected_identities=gtzan_identities,
        selections=selections,
    )
    require_int(smc_row_count, 65 * smc_pieces, "recomputed SMC ledger rows")
    require_int(gtzan_row_count, 65 * gtzan_pieces, "recomputed GTZAN ledger rows")
    for label in ALL_METHOD_LABELS:
        if smc_ledger_identities[label]["configuration_hash"] != gtzan_ledger_identities[label]["configuration_hash"]:
            raise RuntimeError(f"Configuration hash differs between fixed panels for {label}")

    validate_panel_results(
        paths,
        stem="smc_fold0",
        metrics=BEAT_METRICS,
        piece_count=smc_pieces,
        protocol_hash=protocol_hash,
        selections=selections,
        aggregates=smc_aggregates,
    )
    validate_panel_results(
        paths,
        stem="gtzan_final1",
        metrics=METRICS,
        piece_count=gtzan_pieces,
        protocol_hash=protocol_hash,
        selections=selections,
        aggregates=gtzan_aggregates,
    )
    validate_direct_and_combined(
        paths,
        protocol_hash=protocol_hash,
        smc_pieces=smc_pieces,
        gtzan_pieces=gtzan_pieces,
        selections=selections,
        smc_aggregates=smc_aggregates,
        gtzan_aggregates=gtzan_aggregates,
    )
    summary, summary_rows = validate_summary(
        paths,
        smc_aggregates=smc_aggregates,
        gtzan_aggregates=gtzan_aggregates,
        resamples=args.resamples,
        seed=args.seed,
    )
    artifact = validate_artifact_manifest(paths, protocol_hash, frozen["payload_hash"])
    complete = validate_complete(
        paths,
        protocol_hash=protocol_hash,
        frozen_hash=frozen["payload_hash"],
        smc_pieces=smc_pieces,
        gtzan_pieces=gtzan_pieces,
    )
    observed_unique_configurations = len(
        {record["configuration_hash"] for record in selections.values()}
    )
    require_int(
        complete.get("unique_configuration_count"),
        observed_unique_configurations,
        "COMPLETE unique configuration count",
    )

    recomputed_rows: list[dict[str, Any]] = []
    for label in ALL_METHOD_LABELS:
        identity = expected_method_identity(label, selections)
        row: dict[str, Any] = {
            "label": label,
            "family": identity["family"],
            "tuning_size": identity["tuning_size"],
            "tuning_folds": ",".join(map(str, identity["tuning_folds"])),
            "selected_candidate_hash": identity["selected_candidate_hash"],
            "configuration_hash": identity["configuration_hash"],
            "smc_piece_count": smc_pieces,
            "gtzan_piece_count": gtzan_pieces,
        }
        row.update({f"smc_{metric}": smc_aggregates[label][metric] for metric in BEAT_METRICS})
        row.update({f"gtzan_{metric}": gtzan_aggregates[label][metric] for metric in METRICS})
        recomputed_rows.append(row)

    output = args.output.resolve()
    row_fields = tuple(recomputed_rows[0])
    atomic_csv(output / "recomputed_fixed_panel_rows.csv", recomputed_rows, row_fields)
    atomic_csv(
        output / "recomputed_across_combination_summary.csv",
        summary_rows,
        tuple(summary_rows[0]),
    )
    result = {
        "schema": QA_SCHEMA,
        "status": "PASS",
        "completed_at": now_iso(),
        "host": platform.node(),
        "pbs_job_id": os.environ.get("PBS_JOBID"),
        "synthetic_fixture": bool(args.allow_synthetic_fixture),
        "bundle_manifest_file_sha256": args.manifest_sha256,
        "bundle_manifest_payload_hash": bundle["manifest_payload_hash"],
        "protocol_hash": protocol_hash,
        "frozen_lock_hash": frozen["payload_hash"],
        "artifact_manifest_payload_hash": artifact["manifest_payload_hash"],
        "verified_bundle_file_count": bundle["file_count"],
        "verified_combination_count": 64,
        "verified_family_counts": {FAMILY_NAMES[size]: FAMILY_COUNTS[size] for size in (1, 2, 4, 7)},
        "verified_unique_configuration_count": observed_unique_configurations,
        "verified_smc_piece_count_per_method": smc_pieces,
        "verified_gtzan_piece_count_per_method": gtzan_pieces,
        "verified_smc_ledger_row_count": smc_row_count,
        "verified_gtzan_ledger_row_count": gtzan_row_count,
        "fold0_leakage_detected": False,
        "same_configuration_hashes_across_panels": True,
        "freeze_before_evaluation": chronology,
        "bootstrap": {
            "unit": "fold combination",
            "replicates": args.resamples,
            "seed": args.seed,
            "interpretation": "descriptive across-combination uncertainty; not a test-population or training-seed CI",
            "seven_fold_population_sd": None,
            "seven_fold_descriptive_bootstrap_ci95": None,
        },
        "summary": summary,
    }
    atomic_json(output / "qa_results.json", result)
    receipt = {
        "bundle_manifest_file_sha256": args.manifest_sha256,
        "qa_script_sha256": file_sha256(Path(__file__).resolve()),
        "outputs": [
            {
                "path": name,
                "size": (output / name).stat().st_size,
                "sha256": file_sha256(output / name),
            }
            for name in (
                "recomputed_fixed_panel_rows.csv",
                "recomputed_across_combination_summary.csv",
                "qa_results.json",
            )
        ],
    }
    receipt["payload_hash"] = object_sha256(receipt)
    atomic_json(output / "checksum_receipt.json", receipt)
    return result


def self_test() -> None:
    if len(DESIGN) != 64:
        raise AssertionError("design count")
    if Counter(detail["family"] for detail in DESIGN_BY_LABEL.values()) != Counter(
        {FAMILY_NAMES[size]: count for size, count in FAMILY_COUNTS.items()}
    ):
        raise AssertionError("family counts")
    if any(0 in detail["folds"] for detail in DESIGN_BY_LABEL.values()):
        raise AssertionError("fold0 leakage")
    singleton = summarize_values([0.75], "self-test-singleton", 101, 20260902)
    if singleton["population_sd"] is not None or singleton["descriptive_bootstrap_ci95"] is not None:
        raise AssertionError("singleton null contract")
    repeated = summarize_values([0.1, 0.3, 0.2], "self-test", 101, 20260902)
    if repeated["mean"] != statistics.fmean([0.1, 0.3, 0.2]):
        raise AssertionError("summary mean")
    if repeated["descriptive_bootstrap_ci95"] is None:
        raise AssertionError("bootstrap interval")
    print(json.dumps({
        "status": "SELF_TEST_PASS",
        "experimental_results_created": False,
        "combination_count": len(DESIGN),
        "family_counts": {FAMILY_NAMES[size]: FAMILY_COUNTS[size] for size in (1, 2, 4, 7)},
        "singleton_sd": singleton["population_sd"],
        "singleton_ci": singleton["descriptive_bootstrap_ci95"],
    }, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path)
    parser.add_argument("--bundle-manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resamples", type=int, default=FORMAL_RESAMPLES)
    parser.add_argument("--seed", type=int, default=FORMAL_SEED)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--allow-synthetic-fixture", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return args
    for name in ("bundle_root", "bundle_manifest", "manifest_sha256", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required unless --self-test is used")
    if args.resamples < 100:
        parser.error("--resamples must be at least 100")
    return args


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    assert args.output is not None
    output = args.output.resolve()
    if output == args.bundle_root.resolve() or output.is_relative_to(args.bundle_root.resolve()):
        raise RuntimeError("QA output must be outside the immutable input bundle")
    output.mkdir(parents=True, exist_ok=True)
    unexpected_existing = {
        path.name for path in output.iterdir()
        if path.name != "PBS_LAUNCH_RECEIPT.tsv"
    }
    if unexpected_existing:
        raise RuntimeError(
            f"Refusing non-empty QA output directory: {output}; "
            f"unexpected={sorted(unexpected_existing)}"
        )
    atomic_json(
        output / "RUNNING",
        {
            "started_at": now_iso(),
            "pid": os.getpid(),
            "host": platform.node(),
            "pbs_job_id": os.environ.get("PBS_JOBID"),
        },
    )
    try:
        result = run(args)
        complete = {
            "status": "COMPLETE",
            "completed_at": now_iso(),
            "pid": os.getpid(),
            "host": platform.node(),
            "pbs_job_id": os.environ.get("PBS_JOBID"),
            "qa_results_sha256": file_sha256(output / "qa_results.json"),
            "checksum_receipt_sha256": file_sha256(output / "checksum_receipt.json"),
        }
        atomic_json(output / "COMPLETE", complete)
        (output / "RUNNING").unlink(missing_ok=True)
        print(json.dumps(result, indent=2, sort_keys=True))
    except BaseException as exc:
        atomic_json(
            output / "FAILED",
            {
                "status": "FAILED",
                "failed_at": now_iso(),
                "pid": os.getpid(),
                "host": platform.node(),
                "pbs_job_id": os.environ.get("PBS_JOBID"),
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        (output / "RUNNING").unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
