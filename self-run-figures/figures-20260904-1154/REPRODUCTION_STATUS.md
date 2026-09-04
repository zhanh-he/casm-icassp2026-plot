# Reproduction status

Verified on 2026-09-04 using the pinned `lab5090` environment:

- all six figures rendered successfully from this directory's `data/`;
- all six regenerated PNG files are byte-identical to `reference_figures/`;
- the independent data/provenance audit passes 179/179 checks;
- `render_and_validate.sh --only fig05` was separately tested.

Reference/regenerated PNG SHA-256:

```text
64f06c6e0c358f1fe22d969aac0525734d9dac7dbbad5401178407e8d631f942  fig01_input_conditioned_stiffness.png
96f4ef1992016a96532c2da9382d83174a4b2da8fdbf122de3b881720f726390  fig02_real_track_mechanism.png
35e689e65ef79ea4a41795d50136c08d135b984f1e432b772d29f2d20e67ddcb  fig03_ablation_matrix.png
10b8a266be2d392f440aa75edcb540c6f280a8811863a9d798db71a110ff7927  fig04_decoder_operating_points.png
d85db7cdfbf0a6f290577da2b30d52f1e7fcdc9a4a594cb9c0c0fb15de316099  fig05_calibration_scale.png
b6f458824da24544dbe430ddc3b53083b07dbbcc78a9e322038151766b4ea743  fig06_gain_risk.png
```
