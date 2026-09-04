# StructBeat Figure 1 Reproduction Bundle

This directory reproduces the two finalized real-case panels for SMC 221 and
SMC 117. It preserves the exact Beat This held-out OOF logits, unaugmented
input spectrograms, ground truth, Direct/Fixed Semi-Markov/adjusted DBN/CASM
event outputs, downbeat outputs, IBI tables, CASM local duration priors,
reliability proxies, metrics, and the original browser figure.

## Start here

Open and run `figure1_reproduction.ipynb`. The first parameter cell controls:

- `CASE_NAME`: `smc_221` or `smc_117`
- `WINDOW_START`: visible segment start in seconds
- `WINDOW_SECONDS`: visible segment duration
- `PROBABILITY_SOURCE`: `payload` for pixel-faithful replay or `raw_logits`
- `SHOW_LOCAL_TAU`: show/hide CASM's local duration proposal
- `AUDIO_OVERRIDE`: optional authorized local waveform path
- `EXPORT_AUDIO_CLIP`: save the selected waveform interval when audio exists

The selected window is applied to the spectrogram, activation, events, IBI
panels, and optional audio playback. SMC waveform audio is not bundled because
the Beat This data distribution used by this experiment contains precomputed
spectrograms and annotations, not redistributable waveform files.

## Exact browser replay

The original D3 rendering is preserved at
`reference/real-decoder-contrast.html`. Rebuild it from the frozen payloads:

```bash
python reference/build_decoder_contrast_visualization.py \
  --smc221 data/figure_payloads/smc_221.json \
  --smc117 data/figure_payloads/smc_117.json \
  --output outputs/real-decoder-contrast.html
```

The notebook also exports static PNG/PDF figures for both cases. The D3 replay
uses five-decimal probabilities embedded in the payload; the raw logits are
retained in `data/raw_cache/` and differ after sigmoid only by JSON rounding.

## Data map

- `data/raw_cache/`: exact Beat This OOF beat/downbeat logits and GT arrays
- `data/spectrograms/`: exact 2,001 x 128 model input for each case
- `data/figure_payloads/`: frozen final decoder outputs and plot metadata
- `data/tables/`: explicit events, IBIs, duration priors, and reliability CSVs
- `data/diagnostics/`: full-piece event/IBI diagnostic audit
- `data/manifest.json`: checksums, shapes, provenance, and DBN configuration
- `reference/`: exact D3 builder, original HTML, and source analysis scripts
- `src/figure1.py`: deterministic Python plotting and export implementation
- `outputs/`: executed notebook figures and rebuilt browser figure

## Environment

With `uv`:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/jupyter lab figure1_reproduction.ipynb
```

Or create the provided Conda environment:

```bash
conda env create -f environment.yml
conda activate casm-figure1
jupyter lab figure1_reproduction.ipynb
```

## Scientific warning

These cases were selected for mechanism explanation. The adjusted DBN setting
was selected on the displayed examples and must not be reported as an unbiased
aggregate DBN benchmark. Window IBI MAE is phase-insensitive and explanatory;
standard event F1/CMLt/AMLt remain the benchmark metrics.
