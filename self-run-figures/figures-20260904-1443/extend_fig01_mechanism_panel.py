#!/usr/bin/env python3
"""Append one cache panel to the archived Fig. 1 mechanism tables.

The base experiment's aggregate performance tables remain unchanged.  This
utility recomputes only the candidate/path diagnostics used by Fig. 1 and
writes a new, merged data directory instead of mutating the archived run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from run_mechanism_ablation import canonical_json, casm_trace


_FROZEN: dict[str, object] | None = None


def init_worker(frozen: dict[str, object]) -> None:
    global _FROZEN
    _FROZEN = frozen


def process_path(path_text: str):
    if _FROZEN is None:
        raise RuntimeError("worker was not initialized")
    return casm_trace(Path(path_text), _FROZEN)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--expected-pieces", type=int, required=True)
    parser.add_argument("--workers", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base = args.base_data_dir.resolve()
    output = args.output_dir.resolve()
    cache = args.cache_dir.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    paths = sorted(cache.glob("*.npz"))
    if len(paths) != args.expected_pieces:
        raise RuntimeError(
            f"{args.panel}: expected {args.expected_pieces} caches, found {len(paths)}"
        )

    protocol = json.loads((base / "protocol.json").read_text())
    frozen = protocol["frozen_parameters"]
    frozen_hash = hashlib.sha256(canonical_json(frozen).encode()).hexdigest()
    if frozen_hash != protocol["frozen_parameter_sha256"]:
        raise RuntimeError("frozen parameter hash mismatch")

    summaries: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    with ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=init_worker,
        initargs=(frozen,),
    ) as executor:
        for index, (summary, candidate_rows, edge_rows) in enumerate(
            executor.map(process_path, map(str, paths), chunksize=2), 1
        ):
            summary["panel"] = args.panel
            for row in candidate_rows:
                row["panel"] = args.panel
            for row in edge_rows:
                row["panel"] = args.panel
            summaries.append(summary)
            candidates.extend(candidate_rows)
            edges.extend(edge_rows)
            if index % 100 == 0 or index == len(paths):
                print(f"TRACE {args.panel} {index}/{len(paths)}", flush=True)

    output.mkdir(parents=True)
    table_specs = [
        ("mechanism_piece_summary.csv", pd.DataFrame(summaries), None),
        ("mechanism_candidates.csv.gz", pd.DataFrame(candidates), "gzip"),
        ("mechanism_edges.csv.gz", pd.DataFrame(edges), "gzip"),
    ]
    counts: dict[str, int] = {}
    for filename, addition, compression in table_specs:
        original = pd.read_csv(base / filename)
        if args.panel in set(original.panel.astype(str)):
            raise RuntimeError(f"panel already exists in {filename}: {args.panel}")
        merged = pd.concat([original, addition], ignore_index=True)
        merged.to_csv(output / filename, index=False, compression=compression)
        counts[filename] = len(addition)

    updated_protocol = dict(protocol)
    mechanism_panels = dict(protocol.get("mechanism_panels", protocol["panels"]))
    mechanism_panels[args.panel] = {
        "label": args.label,
        "piece_count": len(paths),
        "role": "Fig. 1 mechanism-only panel",
    }
    updated_protocol["mechanism_panels"] = mechanism_panels
    updated_protocol["fig01_extension"] = {
        "panel": args.panel,
        "label": args.label,
        "cache_dir": str(cache),
        "cache_piece_count": len(paths),
        "base_protocol_sha256": sha256(base / "protocol.json"),
        "frozen_parameter_sha256": frozen_hash,
        "generator": Path(__file__).name,
    }
    (output / "protocol.json").write_text(
        json.dumps(updated_protocol, indent=2, sort_keys=True) + "\n"
    )
    shutil.copy2(Path(__file__), output / Path(__file__).name)

    manifest = {
        "status": "COMPLETE",
        "panel": args.panel,
        "piece_count": len(paths),
        "new_rows": counts,
        "output_sha256": {
            path.name: sha256(path)
            for path in sorted(output.iterdir())
            if path.is_file() and path.name != "MANIFEST.json"
        },
    }
    (output / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
