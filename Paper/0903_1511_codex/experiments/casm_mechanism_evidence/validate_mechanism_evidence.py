#!/usr/bin/env python3
"""Independent integrity checks for the CASM mechanism-evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


PRIMARY_METRICS = [
    "beat_fmeasure",
    "beat_cmlt",
    "beat_amlt",
    "downbeat_fmeasure",
    "downbeat_cmlt",
    "downbeat_amlt",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    checks: list[dict[str, object]] = []

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            failures.append(f"{name}: {detail}")

    protocol = json.loads((data_dir / "protocol.json").read_text())
    expected_panels = protocol["panels"]
    expected_methods = protocol["methods"]
    aggregate = pd.read_csv(data_dir / "aggregate_metrics.csv")
    pieces = pd.read_csv(data_dir / "all_piece_metrics.csv.gz")
    candidates = pd.read_csv(data_dir / "mechanism_candidates.csv.gz")
    edges = pd.read_csv(data_dir / "mechanism_edges.csv.gz")
    mechanism = pd.read_csv(data_dir / "mechanism_piece_summary.csv")
    bootstrap = pd.read_csv(data_dir / "paired_bootstrap.csv")

    check(
        "complete marker",
        (data_dir / "COMPLETE").exists(),
        "experiment runner emitted COMPLETE",
    )
    check(
        "aggregate grid",
        len(aggregate) == len(expected_panels) * len(expected_methods),
        f"{len(aggregate)} rows for {len(expected_panels)} panels x {len(expected_methods)} methods",
    )
    check(
        "piece-level unique keys",
        not pieces.duplicated(["panel", "method", "piece"]).any(),
        f"{len(pieces)} unique panel/method/piece rows",
    )

    maximum_aggregate_error = 0.0
    raw_file_count = 0
    for panel, panel_spec in expected_panels.items():
        panel_rows = aggregate[aggregate.panel == panel]
        check(
            f"{panel}: method coverage",
            set(panel_rows.method) == set(expected_methods),
            f"observed {len(panel_rows)} methods",
        )
        expected_piece_count = int(panel_spec["piece_count"])
        reference_pieces: set[str] | None = None
        for method in expected_methods:
            raw_path = data_dir / "raw" / f"{panel}__{method}.pieces.csv"
            check(f"{panel}/{method}: raw file", raw_path.exists(), raw_path.name)
            if not raw_path.exists():
                continue
            raw_file_count += 1
            raw = pd.read_csv(raw_path)
            current_pieces = set(raw.piece.astype(str))
            check(
                f"{panel}/{method}: piece count",
                len(raw) == expected_piece_count and len(current_pieces) == expected_piece_count,
                f"rows={len(raw)}, unique pieces={len(current_pieces)}, expected={expected_piece_count}",
            )
            if reference_pieces is None:
                reference_pieces = current_pieces
            else:
                check(
                    f"{panel}/{method}: identical panel",
                    current_pieces == reference_pieces,
                    "piece identifiers match Direct panel exactly",
                )
            aggregate_row = panel_rows[panel_rows.method == method].iloc[0]
            for metric in PRIMARY_METRICS:
                error = abs(float(raw[metric].mean()) - float(aggregate_row[metric]))
                maximum_aggregate_error = max(maximum_aggregate_error, error)
        check(
            f"{panel}: all-piece export count",
            len(pieces[pieces.panel == panel]) == expected_piece_count * len(expected_methods),
            f"{len(pieces[pieces.panel == panel])} rows",
        )

    check(
        "raw file inventory",
        raw_file_count == len(expected_panels) * len(expected_methods),
        f"validated {raw_file_count} raw files",
    )
    check(
        "aggregate recomputation",
        maximum_aggregate_error < 1e-12,
        f"maximum absolute discrepancy={maximum_aggregate_error:.3e}",
    )
    primary_values = pieces[PRIMARY_METRICS].to_numpy(float)
    finite_primary_values = primary_values[np.isfinite(primary_values)]
    missing_downbeats = pieces[[m for m in PRIMARY_METRICS if m.startswith("downbeat_")]].isna().all(axis=1)
    expected_missing_downbeats = pieces.dataset.eq("smc")
    check(
        "metric bounds",
        (finite_primary_values >= 0.0).all()
        and (finite_primary_values <= 1.0).all()
        and missing_downbeats.equals(expected_missing_downbeats),
        "all defined metrics are finite and in [0,1]; downbeat metrics are missing exactly for SMC",
    )

    expected_mechanism_count = sum(int(v["piece_count"]) for v in expected_panels.values())
    check(
        "mechanism summary coverage",
        len(mechanism) == expected_mechanism_count
        and not mechanism.duplicated(["panel", "piece"]).any(),
        f"{len(mechanism)} unique panel/piece rows; expected {expected_mechanism_count}",
    )
    for panel, panel_spec in expected_panels.items():
        expected_piece_count = int(panel_spec["piece_count"])
        summary_set = set(mechanism.loc[mechanism.panel == panel, "piece"].astype(str))
        candidate_set = set(candidates.loc[candidates.panel == panel, "piece"].astype(str))
        edge_set = set(edges.loc[edges.panel == panel, "piece"].astype(str))
        check(
            f"{panel}: mechanism piece coverage",
            len(summary_set) == expected_piece_count and candidate_set == summary_set and edge_set <= summary_set,
            f"summary={len(summary_set)}, candidates={len(candidate_set)}, edges={len(edge_set)}",
        )

    frozen = protocol["frozen_parameters"]
    duration_sigma = float(frozen["duration_sigma"])
    uncertain_sigma = float(frozen["uncertain_sigma"])
    duration_weight = float(frozen["duration_weight"])

    def validate_cost_table(
        frame: pd.DataFrame, margin_prefix: str, value_prefix: str
    ) -> tuple[float, float]:
        confidence = frame[f"{margin_prefix}_margin"].to_numpy(float)
        sigma_observed = frame[f"{value_prefix}_sigma"].to_numpy(float)
        coefficient_observed = frame[f"{value_prefix}_coefficient"].to_numpy(float)
        sigma_expected = duration_sigma + (1.0 - confidence) * uncertain_sigma
        coefficient_expected = duration_weight * confidence / (2.0 * sigma_expected**2)
        return (
            float(np.max(np.abs(sigma_observed - sigma_expected))),
            float(np.max(np.abs(coefficient_observed - coefficient_expected))),
        )

    candidate_sigma_error, candidate_coefficient_error = validate_cost_table(
        candidates, "period", "endpoint"
    )
    edge_sigma_error, edge_coefficient_error = validate_cost_table(edges, "edge", "edge")
    check(
        "candidate response-law closure",
        candidate_sigma_error < 2e-8 and candidate_coefficient_error < 5e-6,
        f"max sigma error={candidate_sigma_error:.3e}; coefficient error={candidate_coefficient_error:.3e} (float32 confidence storage)",
    )
    check(
        "edge response-law closure",
        edge_sigma_error < 1e-12 and edge_coefficient_error < 1e-10,
        f"max sigma error={edge_sigma_error:.3e}; coefficient error={edge_coefficient_error:.3e}",
    )
    candidate_domain_ok = (
        candidates.period_margin.between(0.0, 1.0).all()
        and candidates.period_bpm.between(float(frozen["min_bpm"]), float(frozen["max_bpm"])).all()
        and (candidates.endpoint_sigma > 0.0).all()
        and (candidates.endpoint_coefficient >= 0.0).all()
    )
    edge_domain_ok = (
        edges.edge_margin.between(0.0, 1.0).all()
        and edges.target_bpm.between(float(frozen["min_bpm"]), float(frozen["max_bpm"])).all()
        and (edges.edge_sigma > 0.0).all()
        and (edges.edge_coefficient >= 0.0).all()
        and (edges.interval_seconds > 0.0).all()
        and (edges.end_seconds > edges.start_seconds).all()
    )
    check("candidate domains", candidate_domain_ok, "confidence, tempo, sigma, and cost coefficient are valid")
    check("edge domains", edge_domain_ok, "confidence, tempo, interval, sigma, and cost coefficient are valid")
    duration_cost_error = np.max(
        np.abs(
            edges.duration_cost.to_numpy(float)
            - edges.edge_coefficient.to_numpy(float) * edges.log_duration_error.to_numpy(float) ** 2
        )
    )
    check(
        "duration-cost closure",
        duration_cost_error < 1e-12,
        f"maximum absolute discrepancy={duration_cost_error:.3e}",
    )

    check(
        "piece diagnostic domains",
        mechanism.period_margin_median.between(0.0, 1.0).all()
        and mechanism.direct_casm_agreement.between(0.0, 1.0).all()
        and mechanism.beat_fallback.isin([True, False]).all(),
        "confidence, agreement, and fallback flags are valid",
    )
    count_mismatch = 0
    metric_mismatch = 0.0
    for row in mechanism.itertuples(index=False):
        c = candidates[(candidates.panel == row.panel) & (candidates.piece == row.piece)]
        e = edges[(edges.panel == row.panel) & (edges.piece == row.piece)]
        count_mismatch += int(len(c) != int(row.candidate_count))
        count_mismatch += int(len(e) != max(int(row.structured_count) - 1, 0))
        pm = pieces[(pieces.panel == row.panel) & (pieces.piece == row.piece)]
        direct = pm[pm.method == "direct"].iloc[0]
        casm = pm[pm.method == "casm_full"].iloc[0]
        for metric, summary_name in [
            ("beat_fmeasure", "delta_fmeasure"),
            ("beat_cmlt", "delta_cmlt"),
            ("beat_amlt", "delta_amlt"),
        ]:
            metric_mismatch = max(
                metric_mismatch,
                abs(float(getattr(row, summary_name)) - (float(casm[metric]) - float(direct[metric]))),
            )
    check(
        "mechanism count reconciliation",
        count_mismatch == 0,
        f"candidate/edge count mismatches={count_mismatch}",
    )
    check(
        "mechanism metric reconciliation",
        metric_mismatch < 1e-12,
        f"maximum delta discrepancy={metric_mismatch:.3e}",
    )

    bootstrap_mean_error = 0.0
    for row in bootstrap.itertuples(index=False):
        left = pieces[(pieces.panel == row.panel) & (pieces.method == row.left)].set_index("piece")
        right = pieces[(pieces.panel == row.panel) & (pieces.method == row.right)].set_index("piece")
        common = left.index.intersection(right.index)
        difference = left.loc[common, row.metric] - right.loc[common, row.metric]
        bootstrap_mean_error = max(bootstrap_mean_error, abs(float(difference.mean()) - float(row.mean_difference)))
    check(
        "bootstrap paired means",
        bootstrap_mean_error < 1e-12,
        f"maximum discrepancy from piece-level paired means={bootstrap_mean_error:.3e}",
    )
    check(
        "bootstrap protocol",
        (bootstrap.repetitions == 5000).all()
        and (bootstrap.seed == 20260904).all()
        and (bootstrap.ci95_low <= bootstrap.mean_difference).all()
        and (bootstrap.mean_difference <= bootstrap.ci95_high).all()
        and bootstrap.bootstrap_probability_gt_zero.between(0.0, 1.0).all(),
        "5,000 paired resamples; seed fixed; means lie inside reported intervals",
    )

    representatives = json.loads((data_dir / "representatives.json").read_text())
    trace_failures = 0
    on_candidate_failures = 0
    for record in representatives:
        trace_path = data_dir / "representative_traces" / f"{record['panel']}__{record['role']}.npz"
        if not trace_path.exists():
            trace_failures += 1
            continue
        with np.load(trace_path, allow_pickle=False) as trace:
            trace_failures += int(str(trace["piece"].item()) != record["piece"])
            trace_failures += int(str(trace["panel"].item()) != record["panel"])
            trace_failures += int(str(trace["role"].item()) != record["role"])
            fps = float(trace["fps"].item())
            candidate_times = trace["candidates"].astype(float) / fps
            casm_times = trace["casm_beat"].astype(float)
            for time in casm_times:
                if len(candidate_times) == 0 or np.min(np.abs(candidate_times - time)) > 1e-8:
                    on_candidate_failures += 1
    check(
        "representative trace provenance",
        trace_failures == 0,
        f"validated {len(representatives)} trace files; metadata mismatches={trace_failures}",
    )
    check(
        "CASM event anchoring",
        on_candidate_failures == 0,
        f"structured beats absent from retained maxima={on_candidate_failures}",
    )

    observed_c = edges.edge_margin.to_numpy(float)
    empirical = {
        "edge_count": int(len(edges)),
        "edge_margin_median": float(np.median(observed_c)),
        "edge_margin_q90": float(np.quantile(observed_c, 0.90)),
        "edge_margin_q995": float(np.quantile(observed_c, 0.995)),
        "edge_margin_max": float(np.max(observed_c)),
        "edge_coefficient_median": float(np.median(edges.edge_coefficient)),
        "edge_coefficient_q995": float(np.quantile(edges.edge_coefficient, 0.995)),
        "edge_coefficient_max": float(np.max(edges.edge_coefficient)),
        "theoretical_coefficient_at_c1": float(duration_weight / (2.0 * duration_sigma**2)),
    }

    input_hashes = {
        name: sha256(data_dir / name)
        for name in [
            "protocol.json",
            "aggregate_metrics.csv",
            "all_piece_metrics.csv.gz",
            "mechanism_candidates.csv.gz",
            "mechanism_edges.csv.gz",
            "mechanism_piece_summary.csv",
            "paired_bootstrap.csv",
            "representatives.json",
        ]
    }
    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": sum(bool(item["passed"]) for item in checks),
        "checks_total": len(checks),
        "failures": failures,
        "checks": checks,
        "empirical_operating_range": empirical,
        "input_sha256": input_hashes,
    }
    (report_dir / "qa_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    markdown = [
        "# CASM mechanism-evidence QA",
        "",
        f"**Status: {report['status']} ({report['checks_passed']}/{report['checks_total']} checks passed).**",
        "",
        "## Checks",
        "",
    ]
    for item in checks:
        mark = "PASS" if item["passed"] else "FAIL"
        markdown.append(f"- **{mark} — {item['name']}:** {item['detail']}")
    markdown.extend(
        [
            "",
            "## Empirical operating range",
            "",
            f"Across {empirical['edge_count']:,} decoded CASM edges, the median margin is "
            f"{empirical['edge_margin_median']:.3f}, the 99.5th percentile is "
            f"{empirical['edge_margin_q995']:.3f}, and the maximum is {empirical['edge_margin_max']:.3f}.",
            "",
            f"The median effective duration coefficient is {empirical['edge_coefficient_median']:.3f}; "
            f"the observed maximum is {empirical['edge_coefficient_max']:.3f}. The response law would reach "
            f"{empirical['theoretical_coefficient_at_c1']:.3f} at c=1, which was not approached by these real edges.",
            "",
            "The QA checks integrity and algebraic consistency. It does not turn post-hoc representative windows into independent performance evidence, and the TCN final0 panel remains exploratory rather than OOF.",
        ]
    )
    (report_dir / "qa_report.md").write_text("\n".join(markdown) + "\n")
    print(json.dumps({"status": report["status"], "passed": report["checks_passed"], "total": report["checks_total"], "failures": failures}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
