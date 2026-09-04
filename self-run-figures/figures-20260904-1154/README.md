# CASM figures — reproducible bundle (2026-09-04 11:54)

This directory contains the exact source data and plotting code for the six
CASM mechanism figures. It is designed for repeated paper revisions: rendering
does not require the original activation caches, the CASM repository, Kaya, or
Gadi.

## Fastest way to redraw Figure 5

Figure 5 is the 1F/2F/4F/7F calibration-scale figure.

```bash
cd /Users/jollibear/Documents/casm-datascaling-plot/self-run-figures/figures-20260904-1154
./setup_and_render.sh --only fig05
```

The first call creates `.venv` and installs the exact package versions used on
`lab5090`. Later calls can skip setup:

```bash
./render_and_validate.sh --only fig05
```

The regenerated files appear as:

```text
figures/fig05_calibration_scale.png
figures/fig05_calibration_scale.pdf
figures/fig05_calibration_scale.svg
```

To render all six figures:

```bash
./render_and_validate.sh
```

If a suitable Python environment already exists, select it explicitly:

```bash
PYTHON=/path/to/python ./render_and_validate.sh --only fig05
```

On `lab5090`, the original environment was:

```bash
PYTHON=/home/mengh/miniconda3/envs/auto-structbeat/bin/python \
  ./render_and_validate.sh --only fig05
```

## Where to edit Figure 5

- Main function: `figure_calibration_scale()` in
  `plot_mechanism_evidence.py`.
- Shared font, line, grid, and export settings: `setup_style()`.
- Source rows: `data/calibration_fixed_panel.csv`.
- Aggregated audit table: `data/calibration_summary.csv`.
- Reference output: `reference_figures/fig05_calibration_scale.*`.

The jitter and bootstrap random generators use the fixed seed `20260904`, and
the environment is pinned in `requirements.txt`.

## Directory map

```text
.
├── README.md
├── requirements.txt
├── setup_and_render.sh             # create a local venv, then render
├── render_and_validate.sh          # render with an existing environment
├── plot_mechanism_evidence.py      # all six figures; supports --only
├── validate_mechanism_evidence.py  # 179 data/provenance checks
├── run_mechanism_ablation.py       # upstream experiment runner
├── chart_contracts.md
├── mechanism_evidence_report.md
├── data/                           # exact figure inputs + raw audit exports
├── reference_figures/              # shipped 2026-09-04 render
├── qa_reference/                   # QA result for the shipped inputs
├── figures/                        # newly regenerated figures
└── qa/                             # newly regenerated QA report
```

## Reproduction levels

### A. Reproduce the figures from archived data

Use `render_and_validate.sh`. This is self-contained apart from Python and the
four packages in `requirements.txt`. All source data read by the plotting
script are under `data/`.

### B. Recompute bootstrap and numeric summaries

This happens automatically every time the plotting script runs. It rewrites:

- `data/paired_bootstrap.csv` using 5,000 paired resamples;
- `data/numeric_summary.json` from the archived edge and piece tables.

### C. Re-run the upstream decoding experiment

`run_mechanism_ablation.py` is included for provenance, but a full upstream
rerun additionally requires the `auto_structbeat` repository, model activation
caches, annotations, and the Frozen-4F parameter file at their recorded remote
paths. Those paths and the parameter SHA-256 are recorded in
`data/protocol.json`. This is deliberately separated from ordinary figure
editing: no remote cache is needed to redraw any figure.

## Validation and provenance

After every render, `validate_mechanism_evidence.py` checks that all methods use
identical piece panels, reconstructs aggregate metrics from raw rows, verifies
the confidence-to-duration-cost algebra, confirms CASM events remain on
retained maxima, and checks the paired-bootstrap metadata. The reference run
passes **179/179 checks**; see `qa_reference/qa_report.md`.

The copied data comprise 2,637 panel-track instances, 26,370 method-track
metric rows, 321,617 retained candidates, and 147,000 decoded CASM edges.

## Figure names

1. `fig01_input_conditioned_stiffness`
2. `fig02_real_track_mechanism`
3. `fig03_ablation_matrix`
4. `fig04_decoder_operating_points`
5. `fig05_calibration_scale`
6. `fig06_gain_risk`

Every figure is exported to PNG (320 dpi), vector PDF, and SVG.
