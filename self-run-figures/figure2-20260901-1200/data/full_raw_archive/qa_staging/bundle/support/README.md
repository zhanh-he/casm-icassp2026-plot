# Fixed-fold0 exhaustive CASM scaling figure builder

This directory contains the reproducible static builder for the locked 3×3
figure. It contains no provisional or fabricated result rows.

## Analytical layout

- Rows: GTZAN Beat full dataset (`N=993`), GTZAN Downbeat full dataset
  (`N=993`), SMC Beat fold0 (`N=27`).
- Columns: F1, CMLt, AMLt.
- X categories: Beat This Direct, CASM 1F, CASM 2F, CASM 4F, CASM 7F.
- CASM scatter counts: `7 / 21 / 35 / 1`; Direct has one deterministic point.
- The dark-blue line connects the equal-weight arithmetic mean of each x
  category. Light-blue dots retain every development-fold combination.
- Every panel uses a raw-score lower limit of `Direct - 0.02`, displayed as
  two percentage points below Direct. The first labeled y tick is exactly the
  Direct score. No broken-axis mark is drawn.

## Canonical input table

Default path:

`input/fixed_fold0_exhaustive_combination_panel_scores.csv`

The header-only contract is in `EXPECTED_INPUT_SCHEMA.csv`. Extra columns are
allowed but ignored. Required fields are:

| Field | Contract |
|---|---|
| `schema_version` | Literal `structbeat.casm.fixed-fold0-combination-panel.v1` |
| `score_unit` | Literal `raw_0_1`; the builder converts to percent for plotting |
| `method` | `beat_this_direct` or `casm` |
| `scale` | Direct=`0`; CASM=`1`, `2`, `4`, or `7` |
| `combination_id` | Stable unique ID; Direct must be `direct` |
| `tuning_folds` | Sorted semicolon list such as `1;3;6;7`; blank for Direct |
| `evaluation_panel` | `gtzan_final1` or `smc_fold0` |
| `evaluation_piece_count` | Exactly `993` or `27`, matching the panel |
| `checkpoint_id` | `beat_this_final1` for GTZAN; `beat_this_oof_fold0` for SMC |
| `candidate_hash` | Required for CASM; may repeat if subsets select the same candidate; blank for Direct |
| `config_hash` | Required for every row; must match across GTZAN/SMC for Direct and for each CASM subset |
| metric columns | Raw `[0,1]`; all six required for GTZAN, Beat three only for SMC |

The canonical table therefore has exactly 130 rows:

- 2 evaluation panels × 1 Direct row;
- 2 evaluation panels × 64 CASM rows;
- within each panel the builder requires the complete combination sets
  `C(7,1)=7`, `C(7,2)=21`, `C(7,4)=35`, and `C(7,7)=1`.

Validation is intentionally strict. Fold0 in a tuning subset, a missing or
duplicate subset, mixed checkpoints/seeds inside a panel, percent-valued input,
SMC downbeat values, or GTZAN/SMC hash disagreement causes a hard failure. The
builder also refuses to silently crop a score below the locked `Direct - 0.02`
lower boundary. Automatic labeled ticks never exceed the 100% metric bound.

## Commands

The builder uses NumPy and Matplotlib. On this Mac, the reproducible invocation
is `uv run --with numpy --with matplotlib`; on lab5090, an activated project
environment that already provides those packages may call `python3` directly.

Validate the real table before drawing:

```bash
uv run --with numpy --with matplotlib \
  build_fixed_fold0_exhaustive_scaling_figure.py \
  --input /absolute/path/to/fixed_fold0_exhaustive_combination_panel_scores.csv \
  --validate-only
```

Render PNG and editable SVG plus the exact family-summary table and checksum
manifest:

```bash
uv run --with numpy --with matplotlib \
  build_fixed_fold0_exhaustive_scaling_figure.py \
  --input /absolute/path/to/fixed_fold0_exhaustive_combination_panel_scores.csv \
  --output-dir /absolute/path/to/figure-output
```

For later appearance revisions, copy `axis_overrides.template.json`, set a
panel-specific `top_tick_pct` and/or `tick_count`, and pass it with
`--axis-overrides`. Null values preserve automatic first-pass upper ticks. Use
`--hide-mean-labels` if exact center labels become visually crowded.

Generated files are:

- `casm_fixed_fold0_exhaustive_combination_scaling_3x3.png`
- `casm_fixed_fold0_exhaustive_combination_scaling_3x3.svg`
- `plotted_family_summary.csv`
- `FIGURE_MANIFEST.json`
- `FIGURE_MANIFEST.sha256`

The manifest records input and builder hashes, output hashes, exact axis
domains/ticks, fixed panel sizes, and the locked combination counts. The figure
caption explicitly limits GTZAN final1 to a post-hoc/test-conditioned
sensitivity analysis.
