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
    "smc_117": {
        "piece": "smc/smc_117/track.npy",
        "fold": "fold 5",
        "frames": 2001,
        "window": (21.48, 18.0),
        "mae": {
            "direct": 0.21163444443963114,
            "fixed_semimarkov": 0.13018814856007171,
            "dbn": 0.10548732021172251,
            "plpdp": 0.16145840247829485,
            "casm": 0.0971100298278904,
        },
    },
    "smc_221": {
        "piece": "smc/smc_221/track.npy",
        "fold": "fold 6",
        "frames": 2001,
        "window": (6.14, 18.0),
        "mae": {
            "direct": 0.3043855862139346,
            "fixed_semimarkov": 0.21212695276280785,
            "dbn": 0.28428269372238607,
            "plpdp": 0.2604504355563224,
            "casm": 0.14455930597312883,
        },
    },
    "gtzan_blues_00023": {
        "piece": "gtzan/gtzan_blues_00023/track.npy",
        "fold": "final0",
        "frames": 1501,
        "window": (11.94, 18.0),
        "mae": {
            "direct": 0.05938884103565335,
            "fixed_semimarkov": 0.020766973660337053,
            "dbn": 0.019082276831056975,
            "plpdp": 0.09644615666649238,
            "casm": 0.03140625839597981,
        },
    },
    "gtzan_metal_00026": {
        "piece": "gtzan/gtzan_metal_00026/track.npy",
        "fold": "final0",
        "frames": 1501,
        "window": (3.0, 18.0),
        "mae": {
            "direct": 0.009234113712374845,
            "fixed_semimarkov": 0.009234113712374845,
            "dbn": 0.22825332063010137,
            "plpdp": 0.0047671529210844745,
            "casm": 0.009234113712374845,
        },
    },
    "gtzan_pop_00053": {
        "piece": "gtzan/gtzan_pop_00053/track.npy",
        "fold": "final0",
        "frames": 1501,
        "window": (3.0, 18.0),
        "mae": {
            "direct": 0.3670006762190544,
            "fixed_semimarkov": 0.23907537036610185,
            "dbn": 0.1832118607623401,
            "plpdp": 0.38769279606947143,
            "casm": 0.2854640171410957,
        },
    },
}


def check_case(case: str) -> None:
    expected = EXPECTED[case]
    bundle = load_case(ROOT, case)
    payload = bundle["payload"]
    assert payload["piece"] == expected["piece"]
    assert payload["protocol"]["fold"] == expected["fold"]
    frames = expected["frames"]
    assert bundle["raw"]["beat_logits"].shape == (frames,)
    assert bundle["raw"]["downbeat_logits"].shape == (frames,)
    assert bundle["spectrogram"].shape == (frames, 128)
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
print("PASS: expected six-panel window IBI diagnostics")
print("PASS: static PNG/PDF outputs")
print("PASS: rebuilt D3 HTML is byte-identical to the frozen reference")
print("PASS: notebook executed top-to-bottom without cell errors")
