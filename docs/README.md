# CASM Decoder Listening Demo

## Public site

**https://zhanh-he.github.io/casm-icassp2026-plot/**

This is the public GitHub Pages demo. It can be opened directly without
cloning the repository or starting a local server.

The site presents the finalized SMC 221/117 decoder-contrast figure.

The page preserves the exact D3 visualization and adds synchronized Web Audio
audition for GroundTruth, Direct, Fixed Semi-Markov, adjusted DBN, and CASM.
Clicks are synthesized from the frozen event arrays in `data/cases.json`.

One-click audition buttons sit directly below the decoder score table. Music is
streamed through the browser's native MP3 player; the click and music gains are
fixed, so the public interface only exposes the controls needed for comparison.

Each case includes its complete 40-second SMC MIREX performance. Original plays
the music alone; GroundTruth and every decoder overlay their events on exactly
the same recording. The figure opens on the selected 18-second analysis window,
and the slider can audition every valid interval in either case.

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
