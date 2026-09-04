# CASM Decoder Listening Demo

## Public site

**https://zhanh-he.github.io/casm-icassp2026-plot/**

This is the public GitHub Pages demo. It can be opened directly without
cloning the repository or starting a local server.

The site presents the finalized SMC 221/117 decoder-contrast figure.

The page preserves the exact D3 visualization and adds synchronized Web Audio
audition for GroundTruth, Direct, Fixed Semi-Markov, adjusted DBN, and CASM.
Clicks are synthesized from the frozen event arrays in `data/cases.json`.

Each case includes a selected 18-second SMC MIREX performance excerpt. Original
plays the music alone; GroundTruth and every decoder overlay their events on
exactly the same recording. Visitors may replace the built-in excerpt with an
authorized local file, which remains in the browser and is not uploaded.

The published clips and their provenance are documented in
[`audio/ATTRIBUTION.md`](audio/ATTRIBUTION.md).

## Rebuild generated assets

Rebuild the data and wrapped visualization from the source bundle:

```bash
python self-run-figures/figure1-20260902-1210/tools/build_github_demo.py
```

## Optional local preview

The following commands are only for development and are not needed to use the
public demo:

```bash
python -m http.server 8765 --directory docs
```

Then open <http://localhost:8765/>.
