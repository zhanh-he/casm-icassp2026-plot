# CASM Decoder Listening Demo

## Public demo

Open the public GitHub Pages site directly in any modern browser:

**https://zhanh-he.github.io/casm-icassp2026-plot/**

No clone, download, or local web server is required. The public demo includes
the SMC 221/117 visualization and synchronized click-track audition for
GroundTruth, Direct, Fixed Semi-Markov, adjusted DBN, and CASM.

Each public case includes a selected 18-second SMC MIREX performance excerpt.
Original plays the music alone; GroundTruth and every decoder overlay their
events on exactly the same recording. Visitors may replace the built-in excerpt
with an authorized local file, which remains in the browser and is not uploaded.

## Source layout

- `docs/`: public GitHub Pages site.
- `self-run-figures/figure1-20260902-1210/`: exact Figure 1 reproduction bundle.
- `Paper/`: paper workspace.

Local development instructions are in [`docs/README.md`](docs/README.md).

To change the published listening windows, edit
`self-run-figures/figure1-20260902-1210/config/public_demo_audio.json`, then run:

```bash
python self-run-figures/figure1-20260902-1210/tools/build_demo_audio.py \
  self-run-figures/figure1-20260902-1210/local_audio
python self-run-figures/figure1-20260902-1210/tools/build_github_demo.py
```
