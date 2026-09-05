#!/usr/bin/env python3
"""Build the reproducible notebook with nbformat rather than hand-edited JSON."""

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]


def code(source: str, tags: list[str] | None = None):
    cell = nbf.v4.new_code_cell(source.strip())
    if tags:
        cell.metadata["tags"] = tags
    return cell


notebook = nbf.v4.new_notebook()
notebook.metadata.update(
    {
        "kernelspec": {
            "display_name": "Python 3 (CASM Figure 1)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.12"},
    }
)
notebook.cells = [
    nbf.v4.new_markdown_cell(
        """# StructBeat Figure 1: exact-data reproduction

**TL;DR.** This notebook replays the finalized SMC 117/221 and selected GTZAN
decoder-contrast figures from exact held-out Beat This logits and spectrograms.
It verifies the frozen figure payload, derives every IBI from event times,
exports inspectable CSVs, and keeps one parameter cell for segment selection.

The default `payload` probability source reproduces the browser figure. Choose
`raw_logits` to plot a fresh sigmoid of the stored float32 logits; the notebook
asserts that the only difference is five-decimal JSON rounding."""
    ),
    code(
        """
from pathlib import Path
import json
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
from IPython.display import Audio, IFrame, display

ROOT = Path.cwd().resolve()
if not (ROOT / "src" / "figure1.py").exists():
    raise RuntimeError("Run this notebook from the reproduction bundle root.")
sys.path.insert(0, str(ROOT / "src"))

from figure1 import (
    CASES,
    build_manifest,
    export_case_tables,
    load_case,
    plot_figure,
    plot_spectrogram,
    save_audio_segment,
)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.titleweight": "regular",
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
})
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Parameters

Edit this single cell to move the visible/audio window. `AUDIO_OVERRIDE` may
point to an authorized WAV, FLAC, MP3, or OGG file matching the chosen item."""
    ),
    code(
        """
CASE_NAME = "smc_117"       # See CASES for SMC and selected GTZAN options
WINDOW_START = None          # None uses the frozen recommended window
WINDOW_SECONDS = 18.0
PROBABILITY_SOURCE = "payload"  # "payload" or "raw_logits"
SHOW_LOCAL_TAU = True
AUDIO_OVERRIDE = None        # e.g. Path("/authorized/path/smc_117.wav")
EXPORT_AUDIO_CLIP = False

assert CASE_NAME in CASES
""",
        tags=["parameters"],
    ),
    nbf.v4.new_markdown_cell(
        """## Load and audit the source chain

The checks below require matching piece IDs, frame counts, GT arrays, and
sigmoid(logit) probabilities. The frozen HTML payload stores probabilities at
five decimal places, so its maximum allowed reconstruction error is 5.1e-6."""
    ),
    code(
        """
bundle = load_case(ROOT, CASE_NAME)
payload = bundle["payload"]
if WINDOW_START is None:
    WINDOW_START = float(payload["recommended_window_start"])

audit = {
    "case": CASE_NAME,
    "piece": payload["piece"],
    "fold": payload["protocol"]["fold"],
    "role": payload["protocol"]["role"],
    "frames": int(bundle["raw"]["beat_logits"].size),
    "spectrogram_shape": list(bundle["spectrogram"].shape),
    "beat_logit_range": [float(bundle["raw"]["beat_logits"].min()), float(bundle["raw"]["beat_logits"].max())],
    "probability_rounding_error": bundle["rounding_error"],
    "window_seconds": [WINDOW_START, WINDOW_START + WINDOW_SECONDS],
}
print(json.dumps(audit, indent=2))
"""
    ),
    nbf.v4.new_markdown_cell("## Reproduce Figure 1"),
    code(
        """
figure_path = ROOT / "outputs" / f"figure1_{CASE_NAME}.png"
fig, selected = plot_figure(
    bundle,
    start=WINDOW_START,
    duration=WINDOW_SECONDS,
    probability_source=PROBABILITY_SOURCE,
    show_local_tau=SHOW_LOCAL_TAU,
    output_path=figure_path,
)
figure_pdf_path = figure_path.with_suffix(".pdf")
fig.savefig(figure_pdf_path, bbox_inches="tight", facecolor="white")
display(fig)
plt.close(fig)
print("Wrote", figure_path)
print("Wrote", figure_pdf_path)
print("Window IBI MAE:", json.dumps(selected["window_mae"], indent=2))
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Inspect the exact model input

This is the unaugmented 128-bin Beat This input. SMC cases contain 2,001 frames
and GTZAN cases 1,501 frames; both use the same 50 fps clock as Figure 1."""
    ),
    code(
        """
spec_figure = plot_spectrogram(bundle, WINDOW_START, WINDOW_SECONDS)
display(spec_figure)
plt.close(spec_figure)
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Optional waveform playback and clip export

The numerical bundle contains spectrograms rather than waveform audio. Set
`AUDIO_OVERRIDE` to a matching authorized local file; this cell then
plays exactly `[WINDOW_START, WINDOW_START + WINDOW_SECONDS]` and can export it."""
    ),
    code(
        """
if AUDIO_OVERRIDE is None:
    print("No waveform bundled. Set AUDIO_OVERRIDE to enable aligned playback.")
else:
    export_path = ROOT / "outputs" / f"{CASE_NAME}_{WINDOW_START:.2f}_{WINDOW_SECONDS:.2f}s.wav" if EXPORT_AUDIO_CLIP else None
    audio, sample_rate = save_audio_segment(
        AUDIO_OVERRIDE,
        WINDOW_START,
        WINDOW_SECONDS,
        output_path=export_path,
    )
    display(Audio(audio, rate=sample_rate))
    if export_path is not None:
        print("Wrote", export_path)
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Export all events, IBIs, priors, and checksums

IBIs are derived directly from consecutive event times, not copied from a
plot. The manifest records SHA-256 checksums for every data artifact."""
    ),
    code(
        """
all_written = []
for case in CASES:
    case_bundle = load_case(ROOT, case)
    all_written.extend(export_case_tables(case_bundle, ROOT / "data" / "tables"))
    case_png = ROOT / "outputs" / f"figure1_{case}.png"
    case_figure, _ = plot_figure(case_bundle, output_path=case_png)
    case_figure.savefig(case_png.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(case_figure)
manifest = build_manifest(ROOT)
print("Exported tables:")
for path in all_written:
    print(" -", path.relative_to(ROOT))
print("Manifest files:", len(manifest["files"]))
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Rebuild the exact browser figure

This executes the preserved source builder against the frozen payloads. The
output is the exact D3 implementation used for the interactive figure, with a
case selector and draggable time-window slider."""
    ),
    code(
        """
browser_output = ROOT / "outputs" / "real-decoder-contrast.html"
subprocess.run(
    [
        sys.executable,
        str(ROOT / "reference" / "build_decoder_contrast_visualization.py"),
        "--smc221", str(ROOT / "data" / "figure_payloads" / "smc_221.json"),
        "--smc117", str(ROOT / "data" / "figure_payloads" / "smc_117.json"),
        "--gtzan-blues", str(ROOT / "data" / "figure_payloads" / "gtzan_blues_00023.json"),
        "--gtzan-metal", str(ROOT / "data" / "figure_payloads" / "gtzan_metal_00026.json"),
        "--gtzan-pop", str(ROOT / "data" / "figure_payloads" / "gtzan_pop_00053.json"),
        "--output", str(browser_output),
    ],
    check=True,
)
print("Wrote", browser_output)
display(IFrame(src="outputs/real-decoder-contrast.html", width="100%", height=1100))
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Validation notes

- SMC has beat annotations but no reference downbeat labels in this protocol;
  its GroundTruth diamonds are hollow. GTZAN also shows filled downbeat diamonds.
- PLPDP is the released algorithm with its default 30-300 BPM range.
- The two SMC examples use the shared illustration-tuned DBN. GTZAN uses the
  matched 30-300 BPM benchmark configuration.
- All displayed cases are post-hoc mechanism illustrations, not an unbiased
  estimate of aggregate benchmark performance.
- IBI curves compare local spacings and can look close despite phase-shifted or
  inserted/deleted beat events. Use F1/CMLt/AMLt for formal evaluation."""
    ),
]

destination = ROOT / "figure1_reproduction.ipynb"
nbf.write(notebook, destination)
print(destination)
