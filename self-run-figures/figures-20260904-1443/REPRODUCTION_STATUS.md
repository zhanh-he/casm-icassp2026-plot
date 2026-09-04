# Reproduction status

Verified on 2026-09-04 using the pinned `lab5090` environment:

- all six figures rendered successfully from this directory's `data/`;
- all six regenerated PNG files are byte-identical to `reference_figures/`;
- the independent data/provenance audit passes 188/188 checks;
- Figure 5 uses Beat This GTZAN final0 on all 993 tracks;
- all 64 fold-combination selections were fixed from SMC folds 1--7 before
  GTZAN evaluation and reduce to 22 unique configurations;
- four configurations shared with an older independent final0 experiment agree
  exactly across all reported metrics (maximum absolute discrepancy 0.0).

Reference/regenerated PNG SHA-256:

```text
64f06c6e0c358f1fe22d969aac0525734d9dac7dbbad5401178407e8d631f942  fig01_input_conditioned_stiffness.png
96f4ef1992016a96532c2da9382d83174a4b2da8fdbf122de3b881720f726390  fig02_real_track_mechanism.png
35e689e65ef79ea4a41795d50136c08d135b984f1e432b772d29f2d20e67ddcb  fig03_ablation_matrix.png
10b8a266be2d392f440aa75edcb540c6f280a8811863a9d798db71a110ff7927  fig04_decoder_operating_points.png
b117ccbb956e0e7c193b2587ab1a8b8c5e021233e843a546332b0a49353da77b  fig05_calibration_scale.png
b6f458824da24544dbe430ddc3b53083b07dbbcc78a9e322038151766b4ea743  fig06_gain_risk.png
```

Figure 5 input SHA-256:

```text
906e8979fc6998a6fef2c3f214a43d153f9ac7fb586d1bb27e5d56b6e1cf6286  calibration_fixed_panel.csv
71bc9dbc4493ff8fad29a120f6e0bc41e8d26c0132b9cbbddd8298ea3c9c819e  calibration_summary.csv
```
