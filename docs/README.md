# CASM Decoder Listening Demo

Static GitHub Pages demo for the finalized SMC 221/117 decoder-contrast figure.

The page preserves the exact D3 visualization and adds synchronized Web Audio
audition for GroundTruth, Direct, Fixed Semi-Markov, adjusted DBN, and CASM.
Clicks are synthesized from the frozen event arrays in `data/cases.json`.

SMC waveform audio is not redistributed. Visitors can load an authorized local
audio file, which remains in the browser and can be mixed with any click path.
Without a waveform, every event path remains audible as a click-only track.

Rebuild generated data and the wrapped visualization from the source bundle:

```bash
python self-run-figures/figure1-20260902-1210/tools/build_github_demo.py
```

Serve locally:

```bash
python -m http.server 8765 --directory docs
```

Then open <http://localhost:8765/>.
