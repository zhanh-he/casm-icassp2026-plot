#!/usr/bin/env python3
"""Render auditable Markdown tables for fixed-fold0 exhaustive CASM results.

The renderer deliberately preserves every score as its source CSV serialized
decimal.  It validates the exhaustive 7/21/35/1 combination topology and
recomputes the independent family statistics before writing either table.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import statistics
import tempfile
from pathlib import Path
from typing import Any, Iterable


DEVELOPMENT_FOLDS = tuple(range(1, 8))
SCALES = (0, 1, 2, 4, 7)
EXPECTED_COUNTS = {0: 1, 1: 7, 2: 21, 4: 35, 7: 1}
EXPECTED_FAMILIES = {
    0: "direct",
    1: "exhaustive_1f",
    2: "exhaustive_2f",
    4: "exhaustive_4f",
    7: "exhaustive_7f",
}

# Display label, independent-summary panel, metric, wide-results source column.
METRICS = (
    ("GTZAN Beat F1", "gtzan_beat", "beat_fmeasure", "gtzan_beat_fmeasure"),
    ("GTZAN Beat CMLt", "gtzan_beat", "beat_cmlt", "gtzan_beat_cmlt"),
    ("GTZAN Beat AMLt", "gtzan_beat", "beat_amlt", "gtzan_beat_amlt"),
    (
        "GTZAN Downbeat F1",
        "gtzan_downbeat",
        "downbeat_fmeasure",
        "gtzan_downbeat_fmeasure",
    ),
    (
        "GTZAN Downbeat CMLt",
        "gtzan_downbeat",
        "downbeat_cmlt",
        "gtzan_downbeat_cmlt",
    ),
    (
        "GTZAN Downbeat AMLt",
        "gtzan_downbeat",
        "downbeat_amlt",
        "gtzan_downbeat_amlt",
    ),
    ("SMC fold0 Beat F1", "smc_beat", "beat_fmeasure", "smc_beat_fmeasure"),
    ("SMC fold0 Beat CMLt", "smc_beat", "beat_cmlt", "smc_beat_cmlt"),
    ("SMC fold0 Beat AMLt", "smc_beat", "beat_amlt", "smc_beat_amlt"),
)

RESULT_REQUIRED_COLUMNS = {
    "label",
    "family",
    "tuning_size",
    "tuning_folds",
    "selected_candidate_hash",
    "configuration_hash",
    "smc_piece_count",
    "gtzan_piece_count",
    *(source for _, _, _, source in METRICS),
}
SUMMARY_REQUIRED_COLUMNS = {
    "panel",
    "metric",
    "tuning_size",
    "combination_count",
    "mean_raw",
    "population_sd_raw",
    "min_raw",
    "max_raw",
    "delta_vs_direct_pp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        required=True,
        help="Formal fixed_panel_combination_results.csv (Direct + 64 combinations).",
    )
    parser.add_argument(
        "--independent-summary",
        type=Path,
        required=True,
        help="independent_family_summary.csv from analyze_fixed_fold0_results.py.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"CSV has no header: {path}")
        return list(reader.fieldnames), [dict(row) for row in reader]


def parse_folds(value: str) -> tuple[int, ...]:
    if not value:
        return ()
    return tuple(int(item) for item in value.split(","))


def parse_score(value: str, context: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise RuntimeError(f"Non-numeric score for {context}: {value!r}") from exc
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise RuntimeError(f"Score outside [0, 1] for {context}: {value!r}")
    return parsed


def validate_hash(value: str, context: str, *, allow_blank: bool = False) -> None:
    if not value and allow_blank:
        return
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError(f"Invalid SHA-256 for {context}: {value!r}")


def validate_results(
    fieldnames: list[str], rows: list[dict[str, str]]
) -> dict[int, list[dict[str, str]]]:
    missing = sorted(RESULT_REQUIRED_COLUMNS - set(fieldnames))
    if missing:
        raise RuntimeError(f"Results CSV is missing columns: {missing}")
    if len(rows) != 65:
        raise RuntimeError(f"Expected Direct + 64 result rows, found {len(rows)}")
    if len({row["label"] for row in rows}) != len(rows):
        raise RuntimeError("Results labels are not unique")

    by_scale: dict[int, list[dict[str, str]]] = {scale: [] for scale in SCALES}
    for row in rows:
        try:
            scale = int(row["tuning_size"])
        except ValueError as exc:
            raise RuntimeError(f"Invalid tuning_size in {row!r}") from exc
        if scale not in EXPECTED_COUNTS:
            raise RuntimeError(f"Unexpected tuning size: {scale}")
        folds = parse_folds(row["tuning_folds"])
        if scale == 0:
            if row["label"] != "direct" or folds or row["family"] != "direct":
                raise RuntimeError("Direct row identity/topology mismatch")
            if row["selected_candidate_hash"]:
                raise RuntimeError("Direct row unexpectedly has a selected candidate hash")
        else:
            if (
                len(folds) != scale
                or tuple(sorted(set(folds))) != folds
                or not set(folds).issubset(DEVELOPMENT_FOLDS)
            ):
                raise RuntimeError(f"Invalid development folds for {row['label']}: {folds}")
            if row["family"] != EXPECTED_FAMILIES[scale]:
                raise RuntimeError(f"Family mismatch for {row['label']}: {row['family']}")
            validate_hash(
                row["selected_candidate_hash"],
                f"{row['label']} selected candidate",
                allow_blank=True,
            )
        validate_hash(row["configuration_hash"], f"{row['label']} configuration")
        for display, _, _, source in METRICS:
            parse_score(row[source], f"{row['label']} / {display}")
        try:
            smc_count = int(row["smc_piece_count"])
            gtzan_count = int(row["gtzan_piece_count"])
        except ValueError as exc:
            raise RuntimeError(f"Invalid piece count for {row['label']}") from exc
        if smc_count <= 0 or gtzan_count <= 0:
            raise RuntimeError(f"Non-positive piece count for {row['label']}")
        by_scale[scale].append(row)

    observed_counts = {scale: len(group) for scale, group in by_scale.items()}
    if observed_counts != EXPECTED_COUNTS:
        raise RuntimeError(f"Combination counts mismatch: {observed_counts}")
    for scale in (1, 2, 4, 7):
        observed = {parse_folds(row["tuning_folds"]) for row in by_scale[scale]}
        expected = set(itertools.combinations(DEVELOPMENT_FOLDS, scale))
        if observed != expected:
            raise RuntimeError(
                f"{scale}F combination coverage mismatch; "
                f"missing={sorted(expected - observed)}, extra={sorted(observed - expected)}"
            )
    if len({row["smc_piece_count"] for row in rows}) != 1:
        raise RuntimeError("SMC panel piece count is not fixed across methods")
    if len({row["gtzan_piece_count"] for row in rows}) != 1:
        raise RuntimeError("GTZAN panel piece count is not fixed across methods")
    return by_scale


def close(observed: float, expected: float) -> bool:
    return abs(observed - expected) <= 1e-12


def validate_summary(
    fieldnames: list[str],
    rows: list[dict[str, str]],
    by_scale: dict[int, list[dict[str, str]]],
) -> dict[tuple[str, str, int], dict[str, str]]:
    missing = sorted(SUMMARY_REQUIRED_COLUMNS - set(fieldnames))
    if missing:
        raise RuntimeError(f"Independent summary CSV is missing columns: {missing}")
    if len(rows) != len(METRICS) * len(SCALES):
        raise RuntimeError(f"Expected 45 independent-summary rows, found {len(rows)}")

    indexed: dict[tuple[str, str, int], dict[str, str]] = {}
    for row in rows:
        key = (row["panel"], row["metric"], int(row["tuning_size"]))
        if key in indexed:
            raise RuntimeError(f"Duplicate independent-summary key: {key}")
        indexed[key] = row

    for _, panel, metric, source in METRICS:
        for scale in SCALES:
            key = (panel, metric, scale)
            if key not in indexed:
                raise RuntimeError(f"Independent summary is missing {key}")
            row = indexed[key]
            values = [float(item[source]) for item in by_scale[scale]]
            direct = float(by_scale[0][0][source])
            expected = {
                "combination_count": float(len(values)),
                "mean_raw": statistics.fmean(values),
                "min_raw": min(values),
                "max_raw": max(values),
                "delta_vs_direct_pp": (statistics.fmean(values) - direct) * 100.0,
            }
            for name, value in expected.items():
                try:
                    observed = float(row[name])
                except ValueError as exc:
                    raise RuntimeError(f"Invalid {name} for {key}: {row[name]!r}") from exc
                if not close(observed, value):
                    raise RuntimeError(
                        f"Independent-summary mismatch for {key}/{name}: "
                        f"observed={observed}, recomputed={value}"
                    )
            expected_sd = statistics.pstdev(values) if len(values) > 1 else None
            serialized_sd = row["population_sd_raw"]
            if expected_sd is None:
                if serialized_sd not in ("", "None", "null"):
                    raise RuntimeError(f"Expected null population SD for {key}, found {serialized_sd!r}")
            else:
                try:
                    observed_sd = float(serialized_sd)
                except ValueError as exc:
                    raise RuntimeError(f"Invalid population SD for {key}: {serialized_sd!r}") from exc
                if not close(observed_sd, expected_sd):
                    raise RuntimeError(
                        f"Independent-summary SD mismatch for {key}: "
                        f"observed={observed_sd}, recomputed={expected_sd}"
                    )
    if set(indexed) != {
        (panel, metric, scale)
        for _, panel, metric, _ in METRICS
        for scale in SCALES
    }:
        unexpected = sorted(
            set(indexed)
            - {
                (panel, metric, scale)
                for _, panel, metric, _ in METRICS
                for scale in SCALES
            }
        )
        raise RuntimeError(f"Unexpected independent-summary keys: {unexpected}")
    return indexed


def markdown_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def markdown_table(headers: Iterable[str], rows: Iterable[Iterable[str]]) -> str:
    header_values = [markdown_escape(str(value)) for value in headers]
    lines = [
        "| " + " | ".join(header_values) + " |",
        "| " + " | ".join("---" for _ in header_values) + " |",
    ]
    for row in rows:
        values = [markdown_escape(str(value)) for value in row]
        if len(values) != len(header_values):
            raise RuntimeError("Internal Markdown table width mismatch")
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def source_preamble(results: Path, summary: Path) -> list[str]:
    return [
        f"- Results source: `{results.resolve()}`",
        f"- Results SHA-256: `{sha256(results)}`",
        f"- Independent summary source: `{summary.resolve()}`",
        f"- Independent summary SHA-256: `{sha256(summary)}`",
        "- Scores below are raw `[0, 1]` values copied verbatim from the source CSV; no display rounding was applied.",
        "- GTZAN final1 is post-hoc/test-conditioned sensitivity evidence, not clean model selection evidence.",
    ]


def render_exact_scores(
    results: Path,
    summary: Path,
    by_scale: dict[int, list[dict[str, str]]],
) -> str:
    direct = by_scale[0][0]
    score_headers = [display for display, _, _, _ in METRICS]
    lines = [
        "# CASM fixed-fold0 exhaustive combination exact score ledger",
        "",
        *source_preamble(results, summary),
        "",
        f"Fixed panels: SMC fold0 `N={direct['smc_piece_count']}`; GTZAN final1 `N={direct['gtzan_piece_count']}`.",
        "",
        "## Beat This Direct reference",
        "",
        markdown_table(
            ["Method", "Configuration SHA-256", *score_headers],
            [[
                "Direct",
                f"`{direct['configuration_hash']}`",
                *(direct[source] for _, _, _, source in METRICS),
            ]],
        ),
    ]
    for scale in (1, 2, 4, 7):
        lines.extend(
            [
                "",
                f"## CASM {scale}F exhaustive combinations (n={EXPECTED_COUNTS[scale]})",
                "",
                markdown_table(
                    [
                        "Label",
                        "Tuning folds",
                        "Selected candidate SHA-256",
                        "Configuration SHA-256",
                        *score_headers,
                    ],
                    [
                        [
                            row["label"],
                            row["tuning_folds"],
                            (
                                f"`{row['selected_candidate_hash']}`"
                                if row["selected_candidate_hash"]
                                else "identity (no candidate hash)"
                            ),
                            f"`{row['configuration_hash']}`",
                            *(row[source] for _, _, _, source in METRICS),
                        ]
                        for row in sorted(
                            by_scale[scale], key=lambda item: parse_folds(item["tuning_folds"])
                        )
                    ],
                ),
            ]
        )
    return "\n".join(lines) + "\n"


def summary_cell(row: dict[str, str]) -> str:
    parts = [f"mean={row['mean_raw']}"]
    if row["population_sd_raw"] not in ("", "None", "null"):
        parts.append(f"population SD={row['population_sd_raw']}")
    else:
        parts.append("population SD=— (n=1)")
    parts.append(f"range=[{row['min_raw']}, {row['max_raw']}]")
    parts.append(f"Δ Direct={row['delta_vs_direct_pp']} pp")
    return "<br>".join(parts)


def render_family_summary(
    results: Path,
    summary: Path,
    indexed: dict[tuple[str, str, int], dict[str, str]],
) -> str:
    compact_rows: list[list[str]] = []
    audit_rows: list[list[str]] = []
    for display, panel, metric, _ in METRICS:
        compact_rows.append(
            [
                display,
                *(summary_cell(indexed[(panel, metric, scale)]) for scale in SCALES),
            ]
        )
        for scale in SCALES:
            row = indexed[(panel, metric, scale)]
            audit_rows.append(
                [
                    display,
                    "Direct" if scale == 0 else f"{scale}F",
                    row["combination_count"],
                    row["mean_raw"],
                    row["population_sd_raw"] or "—",
                    row["min_raw"],
                    row["max_raw"],
                    row["delta_vs_direct_pp"],
                ]
            )
    return "\n".join(
        [
            "# CASM fixed-fold0 nine-metric family summary",
            "",
            *source_preamble(results, summary),
            "",
            "`population SD` is descriptive variation across development-fold combinations, not a test-population or training-seed uncertainty estimate. Direct and 7F each have `n=1`, so their SD is undefined.",
            "",
            "## Compact 9-metric table",
            "",
            markdown_table(
                ["Metric", "Direct (n=1)", "1F (n=7)", "2F (n=21)", "4F (n=35)", "7F (n=1)"],
                compact_rows,
            ),
            "",
            "## Long-form audit table",
            "",
            markdown_table(
                [
                    "Metric",
                    "Family",
                    "n combinations",
                    "Mean raw",
                    "Population SD raw",
                    "Min raw",
                    "Max raw",
                    "Delta vs Direct (pp)",
                ],
                audit_rows,
            ),
            "",
        ]
    )


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    args = parse_args()
    result_fields, result_rows = read_csv(args.results)
    by_scale = validate_results(result_fields, result_rows)
    summary_fields, summary_rows = read_csv(args.independent_summary)
    indexed = validate_summary(summary_fields, summary_rows, by_scale)

    exact_path = args.output_dir / "combination_exact_scores.md"
    family_path = args.output_dir / "family_summary_9_metrics.md"
    atomic_write_text(exact_path, render_exact_scores(args.results, args.independent_summary, by_scale))
    atomic_write_text(family_path, render_family_summary(args.results, args.independent_summary, indexed))

    receipt = {
        "status": "PASS",
        "results_path": str(args.results.resolve()),
        "results_sha256": sha256(args.results),
        "independent_summary_path": str(args.independent_summary.resolve()),
        "independent_summary_sha256": sha256(args.independent_summary),
        "input_rows": len(result_rows),
        "combination_rows": len(result_rows) - 1,
        "family_counts": EXPECTED_COUNTS,
        "metric_count": len(METRICS),
        "outputs": {
            str(exact_path.resolve()): sha256(exact_path),
            str(family_path.resolve()): sha256(family_path),
        },
    }
    receipt_path = args.output_dir / "markdown_table_generation_receipt.json"
    atomic_write_text(receipt_path, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({**receipt, "receipt_path": str(receipt_path.resolve())}, sort_keys=True))


if __name__ == "__main__":
    main()
