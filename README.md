# CASM Decoder Listening Demo

## Public demo

Open the public GitHub Pages site directly in any modern browser:

**https://zhanh-he.github.io/casm-icassp2026-plot/**

No clone, download, or local web server is required. The public demo includes
the SMC 221/117 visualization and synchronized click-track audition for
GroundTruth, Direct, Fixed Semi-Markov, adjusted DBN, and CASM.

Each public case includes its complete 40-second SMC MIREX performance. Original
plays the music alone; GroundTruth and every decoder overlay their events on
exactly the same recording. The figure still opens on the selected 18-second
analysis window, while the slider can audition any valid interval in either case.

## Source layout

- `docs/`: public GitHub Pages site.
- `self-run-figures/figure1-20260902-1210/`: exact Figure 1 reproduction bundle.
- `Paper/`: paper workspace.

Local development instructions are in [`docs/README.md`](docs/README.md).

To change the published audio coverage, edit
`self-run-figures/figure1-20260902-1210/config/public_demo_audio.json`, then run:

```bash
python self-run-figures/figure1-20260902-1210/tools/build_demo_audio.py \
  self-run-figures/figure1-20260902-1210/local_audio
python self-run-figures/figure1-20260902-1210/tools/build_github_demo.py
```
