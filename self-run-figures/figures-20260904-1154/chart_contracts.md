# CASM mechanism figure contracts

## Figure 1 — input-conditioned stiffness

- Question: does one Frozen-4F configuration actually instantiate different
  structural constraints from different activation sequences?
- Takeaway: the deterministic response curve is fixed, but real edge margins
  occupy different ranges across datasets/backbones and produce a broad range
  of effective duration coefficients.
- Form: three-panel research figure: response curve, empirical edge-margin
  ECDF, and per-piece effective-coefficient distribution.
- Data: every structured-path edge from 2,637 cached tracks across five panels.
- Renderer/output: static Matplotlib; PNG/PDF/SVG; final QA on PNG.
- Palette: one blue root for CASM, gold/orange for SMC comparators, greys for
  references; line style and direct labels supplement color.

## Figure 2 — real-track mechanism traces

- Question: what does CASM change in a real successful case, and what does it
  do when periodic evidence is ambiguous?
- Takeaway: in the selected SMC improvement window, the path follows retained
  activation maxima while suppressing an inconsistent local sequence; in the
  ambiguous example, low margin yields low stiffness and CASM defers to Direct.
- Form: two-column, three-row trace figure showing activation/events, local
  target tempo versus reference IBI, and margin/effective coefficient.
- Data: actual Beat This OOF activation caches and reference beats.
- Renderer/output: static Matplotlib; PNG/PDF/SVG; final QA on PNG.
- Palette: blue CASM, charcoal truth, orange Direct, olive PLPDP; event rows and
  marker shapes preserve grayscale legibility.

## Figure 3 — mechanism ablation matrix

- Question: which parts of ambiguity conditioning account for the observed
  F1/continuity operating point?
- Takeaway: local targeting alone is insufficient; strength-only and
  width-only variants generally underperform the coupled rule on SMC, while
  removing safeguards trades some F1 for continuity rather than uniformly
  improving the decoder.
- Form: three aligned diverging heatmaps for paired macro deltas versus Direct
  in Beat F1, CMLt, and AMLt.
- Data: five activation panels, 217 SMC tracks or 993 GTZAN tracks per panel.
- Renderer/output: static Matplotlib; PNG/PDF/SVG; final QA on PNG.
- Palette: blue positive, orange negative, white zero; signed labels included.

## Figure 4 — post-processor operating points

- Question: does CASM replace every prior decoder, or occupy a distinct
  F1–continuity trade-off?
- Takeaway: CASM consistently moves Direct toward higher continuity with small
  F1 changes on these panels; DBN, PLPDP, and support-matched DBN occupy
  different points, with no universal winner.
- Form: small-multiple scatter, Beat F1 versus AMLt, one panel per
  backbone/dataset pair.
- Data: the same fixed cached activations; five decoders per panel.
- Renderer/output: static Matplotlib; PNG/PDF/SVG; final QA on PNG.
- Palette: two-root cap plus distinct marker shapes and direct labels.

## Figure 5 — calibration scale stability

- Question: does selecting on more SMC folds improve the point estimate, or
  mainly reduce dependence on fold composition?
- Takeaway: the cross-combination spread contracts from 1F to 4F, while mean
  performance is metric-dependent and not monotonic.
- Form: box/strip distributions across all fold combinations, faceted by
  target panel and metric.
- Data: 7 one-fold, 21 two-fold, 35 four-fold selections plus one seven-fold
  configuration, all evaluated on fixed SMC-fold0 and GTZAN-final1 panels.
- Renderer/output: static Matplotlib; PNG/PDF/SVG; final QA on PNG.
- Palette: blue scale progression with charcoal Direct reference.

## Figure 6 — gain versus regression risk

- Question: do CASM's fallback and count-ratio safeguards reduce harmful
  overcorrection, even when an unconstrained decoder has a larger mean gain?
- Takeaway: safeguards consistently reduce the fraction of tracks degraded by
  more than five percentage points, at the cost of some peak mean correction.
- Form: two-panel scatter for Beat F1 and AMLt; arrows connect the no-safeguard
  decoder to full CASM on each fixed activation panel.
- Data: paired piece-level scores from 2,637 panel-track instances.
- Renderer/output: static Matplotlib; PNG/PDF/SVG; final QA on PNG.
- Palette: panel identity uses five approved roots; marker shape distinguishes
  fixed precision, no safeguards, and full CASM without relying on color.
