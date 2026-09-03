#!/usr/bin/env python3
"""Convert the sealed 65-row wide CASM table into the 130-row figure contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path


SCHEMA_VERSION = "structbeat.casm.fixed-fold0-combination-panel.v1"
METRICS = (
    "beat_fmeasure",
    "beat_cmlt",
    "beat_amlt",
    "downbeat_fmeasure",
    "downbeat_cmlt",
    "downbeat_amlt",
)
HEADER = (
    "schema_version",
    "score_unit",
    "method",
    "scale",
    "combination_id",
    "tuning_folds",
    "evaluation_panel",
    "evaluation_piece_count",
    "checkpoint_id",
    "candidate_hash",
    "config_hash",
    *METRICS,
)
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
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        source = list(csv.DictReader(handle))
    if len(source) != 65:
        raise RuntimeError(f"Expected Direct + 64 CASM rows, found {len(source)}")
    observed_counts = {scale: 0 for scale in EXPECTED_COUNTS}
    observed_subsets: dict[int, list[tuple[int, ...]]] = {
        scale: [] for scale in EXPECTED_COUNTS
    }
    seen_labels: set[str] = set()
    identity_substitutions = 0
    rows: list[dict[str, str | int]] = []
    for item in source:
        scale = int(item["tuning_size"])
        if scale not in EXPECTED_COUNTS:
            raise RuntimeError(f"Unexpected tuning size {scale}")
        observed_counts[scale] += 1
        label = item["label"].strip()
        if not label or label in seen_labels:
            raise RuntimeError(f"Missing or duplicate label: {label!r}")
        seen_labels.add(label)
        is_direct = scale == 0
        if is_direct != (label == "direct"):
            raise RuntimeError(f"Direct identity mismatch for {label}")
        folds = tuple(int(value) for value in item["tuning_folds"].split(",") if value)
        if is_direct:
            if folds:
                raise RuntimeError("Direct must not contain tuning folds")
        elif len(folds) != scale or 0 in folds or tuple(sorted(set(folds))) != folds:
            raise RuntimeError(f"Invalid tuning folds for {label}: {folds}")
        observed_subsets[scale].append(folds)
        candidate_hash = item["selected_candidate_hash"].strip()
        config_hash = item["configuration_hash"].strip()
        if not config_hash:
            raise RuntimeError(f"Missing configuration hash for {label}")
        if is_direct and candidate_hash:
            raise RuntimeError("Direct must not contain a selected candidate hash")
        if not is_direct and not candidate_hash:
            # A development setting is allowed to retain Direct identity when no
            # CASM candidate passes the guard.  Give that frozen identity a
            # deterministic provenance key instead of emitting a blank CASM key.
            candidate_hash = f"identity-{config_hash}"
            identity_substitutions += 1
        for panel, piece_field, prefix, checkpoint in (
            ("gtzan_final1", "gtzan_piece_count", "gtzan_", "beat_this_final1"),
            ("smc_fold0", "smc_piece_count", "smc_", "beat_this_oof_fold0"),
        ):
            piece_count = int(item[piece_field])
            expected_piece_count = 993 if panel == "gtzan_final1" else 27
            if piece_count != expected_piece_count:
                raise RuntimeError(
                    f"{label} {panel}: expected {expected_piece_count} pieces, found {piece_count}"
                )
            metrics: dict[str, str] = {}
            for metric in METRICS:
                if panel == "smc_fold0" and metric.startswith("downbeat_"):
                    metrics[metric] = ""
                    continue
                value = float(item[f"{prefix}{metric}"])
                if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                    raise RuntimeError(f"{label} {panel} {metric}: invalid raw score {value}")
                metrics[metric] = repr(value)
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "score_unit": "raw_0_1",
                    "method": "beat_this_direct" if is_direct else "casm",
                    "scale": scale,
                    "combination_id": "direct" if is_direct else label,
                    "tuning_folds": ";".join(map(str, folds)),
                    "evaluation_panel": panel,
                    "evaluation_piece_count": piece_count,
                    "checkpoint_id": checkpoint,
                    "candidate_hash": "" if is_direct else candidate_hash,
                    "config_hash": config_hash,
                    **metrics,
                }
            )
    if observed_counts != EXPECTED_COUNTS:
        raise RuntimeError(f"Family counts mismatch: {observed_counts}")
    expected_subsets = {
        0: {()},
        **{
            scale: set(itertools.combinations(range(1, 8), scale))
            for scale in (1, 2, 4, 7)
        },
    }
    for scale, expected in expected_subsets.items():
        observed = observed_subsets[scale]
        if len(observed) != len(set(observed)) or set(observed) != expected:
            missing = sorted(expected - set(observed))
            duplicated = sorted(
                subset for subset in set(observed) if observed.count(subset) > 1
            )
            extra = sorted(set(observed) - expected)
            raise RuntimeError(
                f"{scale}F subsets are not the exact exhaustive family: "
                f"missing={missing[:5]}, duplicated={duplicated[:5]}, extra={extra[:5]}"
            )
    if len(rows) != 130:
        raise RuntimeError(f"Expected 130 panel rows, found {len(rows)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(args.output)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "source_path": str(args.input.resolve()),
        "source_sha256": sha256(args.input),
        "source_rows": len(source),
        "output_path": str(args.output.resolve()),
        "output_sha256": sha256(args.output),
        "output_rows": len(rows),
        "family_counts": observed_counts,
        "identity_candidate_hash_substitutions": identity_substitutions,
    }
    receipt_path = args.output.with_suffix(args.output.suffix + ".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
