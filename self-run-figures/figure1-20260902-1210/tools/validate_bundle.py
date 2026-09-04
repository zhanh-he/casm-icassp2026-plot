#!/usr/bin/env python3
"""Regression checks for the exact-data Figure 1 reproduction bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import nbformat
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from figure1 import CASES, load_case, window_data  # noqa: E402


EXPECTED = {
    "smc_221": {
        "piece": "smc/smc_221/track.npy",
        "fold": "fold 6",
        "window": (6.14, 18.0),
        "mae": {
            "direct": 0.3043855862139346,
            "fixed_semimarkov": 0.21212695276280785,
            "dbn": 0.28428269372238607,
            "casm": 0.14455930597312883,
        },
    },
    "smc_117": {
        "piece": "smc/smc_117/track.npy",
        "fold": "fold 5",
        "window": (21.48, 18.0),
        "mae": {
            "direct": 0.21163444443963114,
            "fixed_semimarkov": 0.13018814856007171,
            "dbn": 0.10548732021172251,
            "casm": 0.0971100298278904,
        },
    },
}


def check_case(case: str) -> None:
    expected = EXPECTED[case]
    bundle = load_case(ROOT, case)
    payload = bundle["payload"]
    assert payload["piece"] == expected["piece"]
    assert payload["protocol"]["fold"] == expected["fold"]
    assert bundle["raw"]["beat_logits"].shape == (2001,)
    assert bundle["raw"]["downbeat_logits"].shape == (2001,)
    assert bundle["spectrogram"].shape == (2001, 128)
    assert bundle["spectrogram"].dtype == np.float16
    assert max(bundle["rounding_error"].values()) <= 5.1e-6
    start, duration = expected["window"]
    observed = window_data(bundle, start, duration)["window_mae"]
    for method, value in expected["mae"].items():
        assert np.isclose(observed[method], value, atol=1e-12, rtol=0), (
            case,
            method,
            observed[method],
            value,
        )
    for suffix in ("events.csv", "ibi.csv", "priors.csv"):
        assert (ROOT / "data" / "tables" / f"{case}_{suffix}").is_file()
    for suffix in ("png", "pdf"):
        path = ROOT / "outputs" / f"figure1_{case}.{suffix}"
        assert path.is_file() and path.stat().st_size > 10_000


for case_name in CASES:
    check_case(case_name)

reference_html = (ROOT / "reference" / "real-decoder-contrast.html").read_bytes()
rebuilt_html = (ROOT / "outputs" / "real-decoder-contrast.html").read_bytes()
assert reference_html == rebuilt_html

manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
assert set(manifest["cases"]) == set(CASES)
assert len(manifest["files"]) >= 13

notebook = nbformat.read(ROOT / "figure1_reproduction.ipynb", as_version=4)
code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
assert code_cells and all(cell.execution_count is not None for cell in code_cells)
assert not any(
    output.output_type == "error"
    for cell in code_cells
    for output in cell.get("outputs", [])
)

print("PASS: exact source alignment for", ", ".join(CASES))
print("PASS: expected five-panel window IBI diagnostics")
print("PASS: static PNG/PDF outputs")
print("PASS: rebuilt D3 HTML is byte-identical to the frozen reference")
print("PASS: notebook executed top-to-bottom without cell errors")
