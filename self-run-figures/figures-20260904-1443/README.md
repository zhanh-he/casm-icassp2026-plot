# CASM figures — reproducible bundle (2026-09-04 14:43)

This directory contains the exact source data and plotting code for the six
CASM mechanism figures. It is designed for repeated paper revisions: rendering
does not require the original activation caches, the CASM repository, Kaya, or
Gadi.

## Fastest way to redraw Figure 5

Figure 5 is the 1F/2F/4F/7F calibration-scale figure.

```bash
cd /Users/jollibear/Documents/icassp2027casm/self-run-figures/figures-20260904-1443
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
├── validate_mechanism_evidence.py  # data/provenance checks
├── run_mechanism_ablation.py       # upstream experiment runner
├── evaluate_locked_combinations_final0.py
│                                     # locked GTZAN-final0 evaluation runner
├── chart_contracts.md
├── mechanism_evidence_report.md
├── data/                           # exact figure inputs + raw audit exports
│   └── final0_experiment_provenance/ # lock, protocol, inventory, QA, outputs
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

### D. Re-run the final0 calibration-scale evaluation

`evaluate_locked_combinations_final0.py` reproduces the corrected GTZAN side
of Figure 5 when the recorded Beat This final0 cache and code snapshot are
available. It evaluates the 64 configurations selected only from SMC folds
1--7 (22 unique configurations) on all 993 GTZAN final0 tracks. The selection
lock is written before the script inventories or scores GTZAN. The resulting
tables, lock, protocol, inventory, and QA report are archived under
`data/final0_experiment_provenance/`. The exact command form is:

```bash
python evaluate_locked_combinations_final0.py \
  --project-root /media/mengh/SharedData/zhanh/auto_structbeat/runs/20260831_casm_ranked_frozen_v1/code_snapshot \
  --sealed-driver /media/mengh/SharedData/zhanh/auto_structbeat/runs/20260831_casm_ranked_frozen_v1/code_snapshot/run_driver/run_casm_ranked_protocol.py \
  --locked-combinations data/calibration_fixed_panel.csv \
  --gtzan-final0-cache /media/mengh/SharedData/zhanh/auto_structbeat/caches/pilot/beat_this_final0_gtzan \
  --crosscheck-csv data/final0_experiment_provenance/independent_final0_crosscheck.csv \
  --output /media/mengh/SharedData/zhanh/auto_structbeat/runs/FRESH_OUTPUT_DIRECTORY \
  --workers 12 --trim-seconds 5 --verify-result-hashes
```

The output directory must be new: the runner refuses to overwrite a completed
experiment.

## Validation and provenance

After every render, `validate_mechanism_evidence.py` checks that all methods use
identical piece panels, reconstructs aggregate metrics from raw rows, verifies
the confidence-to-duration-cost algebra, confirms CASM events remain on
retained maxima, checks the paired-bootstrap metadata, and audits the Figure 5
final0 lock, panel size, summaries, hashes, and checkpoint identity. See
`qa_reference/qa_report.md` for the reference run, which passes **188/188
checks**.

The final0 evaluation was also cross-checked against an older, independently
run final0 experiment for the four overlapping configurations; every reported
metric agreed exactly (maximum absolute discrepancy 0.0).

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
