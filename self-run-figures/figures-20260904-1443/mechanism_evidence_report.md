# CASM mechanism experiments and visualization notes

## Bottom line

The new experiments support a precise claim: **CASM is not parameter-free; it replaces target-specific decoder tuning with a frozen, input-conditioned correction policy.** Its novelty is therefore not a smaller parameter count. The distinction is that the frozen constants define how local rhythmic evidence is converted into a per-candidate target period, uncertainty, and duration precision, whereas those effective controls vary automatically within every track.

This claim is directly testable. Replacing CASM's input-conditioned precision with a fixed precision loses 1.64/1.77 CMLt/AMLt percentage points on Beat This--SMC OOF and 2.60/3.37 points on MSCNN-lite--SMC OOF. The corresponding losses remain positive on both GTZAN panels. Thus, the adaptive part is not merely a verbal reinterpretation of a fixed-parameter decoder.

At the same time, the evidence rules out several overclaims. Real CASM edges mostly occupy the relaxed part of the response curve; one-endpoint context performs almost identically to two-endpoint averaging; and the TCN mechanism panel is final0 rather than OOF. Those facts should be disclosed, not hidden.

## Experimental protocol

- Compute: `lab5090` (RTX 5090); Kaya and Gadi were checked, but the 5090 host already held the required activation caches and gave the shortest turnaround.
- Frozen CASM configuration: the pre-existing Frozen-4F parameter file, SHA-256 `251c96b23223b2e4ddef7f4ab85592663a1c27fcd6d62b1a5d1ef5625ed01f71`.
- Five fixed activation panels: Beat This/SMC OOF (217 tracks), MSCNN-lite/SMC OOF (217), Beat This/GTZAN seed0 (993), MSCNN-lite/GTZAN (993), and an explicitly exploratory TCN/SMC final0 panel (217).
- Ten decoders on identical cached activations: Direct, full CASM, fixed-precision local target, strength-only ambiguity, width-only ambiguity, one-endpoint context, CASM without safeguards, default DBN, DBN with CASM-matched 30--300 BPM support, and PLPDP.
- Total output: 2,637 panel-track instances, 26,370 method-track metric rows, 321,617 retained candidates, and 147,000 decoded CASM edges.
- Statistics: paired per-track differences and 5,000 paired bootstrap resamples with seed 20260904.
- Integrity: 196/196 independent checks pass, covering exact panel matching, aggregate reconstruction, response-law closure, duration-cost closure, event anchoring to retained maxima, trace provenance, and the separately locked CASM/DBN GTZAN-final0 calibration-scale evaluations.

SMC has no downbeat annotations; its downbeat fields are intentionally undefined. The GTZAN seed0 and TCN final0 panels are mechanism panels, not substitutes for the paper's formal multi-seed/OOF estimates.

## Figure-by-figure interpretation

### Figure 1: input-conditioned duration stiffness

The fixed Frozen-4F law is

\[
\sigma(c)=\sigma_0+(1-c)\sigma_u,
\qquad
w(c)=\frac{\lambda c}{2\sigma(c)^2},
\]

with \(\sigma_0=0.12\), \(\sigma_u=0.4\), and \(\lambda=4\). The global parameters fix the response curve, but every edge receives its own \(c_{ij}\), hence its own \(\sigma_{ij}\) and \(w_{ij}\).

Across 147,000 real decoded edges, median \(c_{ij}=0.108\), the 90th percentile is 0.178, the 99.5th percentile is 0.340, and the maximum is 0.602. The theoretical coefficient is 138.89 at \(c=1\), but the empirical median, 99.5th percentile, and maximum are only 0.951, 4.623, and 15.473. CASM therefore behaves mainly as a **graded soft constraint**, not as a frequently activated hard metronome.

This is an important refinement to the methodology narrative: the value of the nonlinear law is its ability to allocate different constraint strength from the same frozen configuration, not an assertion that the maximum stiffness is routinely reached.

### Figure 2: real-track mechanism traces

On `smc/smc_037`, CASM uses a confident local period to reject incompatible activation maxima while retaining actual maxima as event locations. Relative to Direct, the selected track gains 7.8 Beat-F1 points and 23.5 CMLt points. On `smc/smc_287`, the local period evidence is ambiguous, the effective coefficient collapses toward zero, and CASM effectively defers to the observation stream; Direct and CASM are identical in the shown metrics.

These windows were selected post hoc to expose the mechanism. They are explanatory examples, not independent performance estimates. Failure traces are also retained in the reproducibility bundle (`smc/smc_266` and `gtzan_classical_00051`) so the visualization is auditable rather than cherry-pick-only.

### Figure 3: mechanism ablations

Full CASM relative to Direct gives the following paired macro changes:

| Activation panel | Beat F1 | CMLt | AMLt |
|---|---:|---:|---:|
| Beat This / SMC OOF | +0.24 | +2.34 | +2.71 |
| MSCNN-lite / SMC OOF | +0.45 | +3.30 | +4.39 |
| TCN / SMC final0 (exploratory) | +0.91 | +4.06 | +4.83 |
| Beat This / GTZAN seed0 | +0.06 | +0.35 | +0.34 |
| MSCNN-lite / GTZAN | +0.33 | +1.51 | +2.34 |

For CASM versus Direct, the 95% paired-bootstrap interval excludes zero for CMLt and AMLt on both OOF SMC panels and both GTZAN panels. Beat-F1 evidence is smaller: the interval excludes zero on MSCNN-lite/SMC and MSCNN-lite/GTZAN, but not on Beat This/SMC or Beat This/GTZAN.

The most decisive ablation is **local target, fixed precision**. Relative to that variant, full CASM changes CMLt/AMLt by:

| Activation panel | \(\Delta\)CMLt | \(\Delta\)AMLt |
|---|---:|---:|
| Beat This / SMC OOF | +1.64 | +1.77 |
| MSCNN-lite / SMC OOF | +2.60 | +3.37 |
| TCN / SMC final0 (exploratory) | +3.50 | +4.23 |
| Beat This / GTZAN seed0 | +1.14 | +1.19 |
| MSCNN-lite / GTZAN | +0.48 | +0.68 |

Every listed continuity difference has a 95% paired-bootstrap interval above zero. This is the clearest experimental answer to “CASM also has many parameters, so what is different?” The data-conditioned precision contributes beyond merely estimating a local tempo and feeding it to a conventional fixed-strength cost.

The strength-only and width-only variants show that neither ambiguity statistic alone universally reproduces the full behavior, although their separation from CASM is panel-dependent. Conversely, one-endpoint context is nearly indistinguishable from full two-endpoint averaging. We should not sell endpoint averaging as a central novelty; it is better described as a symmetric implementation choice.

### Figure 4: decoder operating points and the DBN tuning issue

Changing only DBN's tempo support from 55--215 to 30--300 BPM does not produce a stable directional effect:

- Beat This/SMC: +1.19 Beat-F1 and +3.27 CMLt points.
- MSCNN-lite/SMC: -4.09 Beat-F1 and -7.01 CMLt points.
- TCN/SMC final0: -3.47 Beat-F1 and -5.04 CMLt points.
- Beat This/GTZAN: +0.54 Beat-F1 but only +0.13 CMLt, whose bootstrap interval includes zero.
- MSCNN-lite/GTZAN: -1.03 Beat-F1 and -1.96 CMLt points.

This is exactly the argument we need, stated carefully. A wider tempo range is not intrinsically “fairer” or better; the appropriate DBN operating point depends on the frontend and corpus. Choosing it after viewing target-set outcomes is precisely the form of target-aware decoder tuning we want to avoid. CASM does not prove DBN obsolete—DBN still attains higher AMLt in several panels—but it offers a different deployment contract: one frozen correction policy that moves between observation-following and continuity-seeking behavior from the activation itself.

### Figure 5: calibration-fold scale

Figure 5 now places CASM beside a fresh DBN calibration experiment rather than an unmatched published or TCN-derived result. Both methods use the same Beat This frontend, the same 7/21/35/1 subsets of SMC folds 1--7, the same primary 0.0005 Beat-F1 equivalence band followed by CMLt and AMLt tie-breaks, the same macro-piece aggregation, and the same fixed SMC-fold0 and Beat This **GTZAN-final0** panels. For DBN, 52 preregistered global settings vary minimum tempo, maximum tempo, and transition strength. Its 64 choices reduce to 19 configurations and are locked before either fixed panel is inventoried or scored. Direct scores reproduce the CASM experiment exactly.

The main result is a difference in selection sensitivity, not a generic “more data is worse” story. Across SMC-fold0 selections, the 1F population standard deviations for CASM are 0.30/0.91/0.83 points in Beat F1/CMLt/AMLt; the corresponding DBN deviations are 1.72/6.82/7.34 points. At 4F they are 0.19/0.45/0.30 for CASM versus 1.62/6.47/5.85 for DBN. The same ordering holds on GTZAN final0: at 4F, DBN's standard deviations are 0.39/0.82/1.15 points, versus 0.01/0.06/0.05 for CASM. The figure therefore supplies direct empirical support for the claim that the frozen CASM policy is less dependent on which labelled folds happened to calibrate it under these stated search spaces.

The means expose a second, musically useful point. DBN's GTZAN transfer improves steadily from 1F to 7F, but its held-out SMC Beat F1 and CMLt do not: the 7F choice reaches 58.00 F1 and 44.16 CMLt on SMC fold0, while reaching 89.18 and 81.58 on GTZAN final0. A single global tempo/transition setting can therefore transfer differently across corpora even when selected automatically. CASM's tighter clustering is consistent with its design: fixed constants govern an activation-conditioned response rather than choosing one effective rigidity for every excerpt. This experiment supports that mechanism-level interpretation but does not by itself prove causality.

The defensible conclusion is consequently:

> Under matched calibration folds and fixed evaluation panels, CASM is markedly less sensitive than a 52-setting DBN global-timing sweep to fold composition. Increasing the calibration set does not guarantee monotonic held-out improvement for either decoder, and the single 7F point cannot establish a universal optimum.

The caveat matters: the raw search spaces are not identical because the decoders expose different controls. This experiment covers the DBN's central global timing axes and should not be described as an exhaustive result over every possible observation model or meter inventory.

### Figure 6: correction gain versus regression risk

Removing safeguards can increase average continuity, but it increases the fraction of tracks with a greater-than-five-point regression. For Beat F1, adding CASM's safeguards changes that risk as follows:

| Activation panel | No safeguards | CASM |
|---|---:|---:|
| Beat This / SMC OOF | 7.4% | 1.8% |
| MSCNN-lite / SMC OOF | 10.6% | 4.1% |
| TCN / SMC final0 (exploratory) | 10.1% | 5.1% |
| Beat This / GTZAN seed0 | 2.6% | 0.7% |
| MSCNN-lite / GTZAN | 6.8% | 3.2% |

The same direction holds for AMLt on all five panels. The safeguards are consequently best framed as a **risk-control layer**: they deliberately surrender some peak average correction to reduce severe per-track overcorrection. This also makes the “automatic transmission” metaphor technically meaningful—CASM estimates when to apply pressure and contains a fallback brake when the structured path becomes implausible.

## The strongest paper answer to the parameter-count objection

The following distinction should drive the methodology and discussion:

1. **We do not claim zero hyperparameters.** CASM has a candidate threshold, response-law constants, tempo support, and safety thresholds. Claiming otherwise would be easy to attack.
2. **A parameter list is not the same as a per-corpus tuning burden.** Once frozen, CASM's constants define a policy. It does not select a new tempo range, transition stiffness, or correction strength from each target corpus's labels.
3. **The effective decoder is input-conditioned.** Local period \(\tau_i\), ambiguity \(c_i\), uncertainty \(\sigma_i\), and duration coefficient \(w_i\) are recomputed from the activation at every candidate/edge. They are latent operating variables, not manually chosen test-set settings.
4. **The fixed-precision control tests this distinction.** If adaptivity were just rhetoric around many constants, the fixed-precision local-target decoder would be equivalent. It is consistently worse in continuity, especially on difficult SMC activations.
5. **The DBN range experiment exposes the alternative burden.** A seemingly simple global DBN change helps one frontend and seriously harms another on the same corpus. This is why a frozen evidence-to-rigidity mapping is useful.
6. **Safeguards define abstention, not only stronger regularization.** CASM can back off when confidence is low or the structured count is implausible. The gain--risk experiment shows that this brake materially reduces severe regressions.

A compact paper-ready formulation is:

> CASM is not parameter-free; rather, it is target-tuning-free under our evaluation protocol. Its frozen hyperparameters specify a shared evidence-to-constraint policy, while the effective period target and duration precision are inferred anew from each activation sequence. In contrast to selecting a corpus-specific transition rigidity or tempo support, CASM continuously interpolates between observation-driven peak picking and structure-driven correction, with explicit fallback when the structured path is implausible.

An even sharper sentence for the introduction is:

> The contribution is not fewer knobs, but moving the consequential knob turning from the experimenter to the evidence.

Use that last line sparingly; the longer formulation should carry the formal claim.

## Recommended paper use

- Main paper: Figure 1 or 2 for mechanism, Figure 3 for causal ablation, and a compact version of Figure 4 or 6 for the deployment argument.
- Supplement: full Figure 4, Figure 5, Figure 6, all representative traces including failures, and the paired-bootstrap table.
- Avoid presenting all six figures in the ICASSP main paper; they are an evidence bank from which to select after the narrative and page budget are fixed.
- Keep the phrases “target-tuning-free under our protocol,” “frozen input-conditioned policy,” and “risk-controlled correction.” Avoid unqualified “parameter-free,” “universally robust,” or “4F is optimal.”

## Artifact map

- Figures: `figures/fig01_input_conditioned_stiffness.{pdf,png,svg}` through `figures/fig06_gain_risk.{pdf,png,svg}`.
- Aggregate and paired statistics: `data/aggregate_metrics.csv`, `data/all_piece_metrics.csv.gz`, and `data/paired_bootstrap.csv`.
- Mechanism traces: `data/mechanism_candidates.csv.gz`, `data/mechanism_edges.csv.gz`, `data/mechanism_piece_summary.csv`, and `data/representative_traces/`.
- Protocol/provenance: `data/protocol.json`, `data/representatives.json`, and `data/final0_experiment_provenance/`.
- Independent audit: `qa/qa_report.md` and `qa/qa_report.json`.
- Reproduction: `run_mechanism_ablation.py`, `plot_mechanism_evidence.py`, and `validate_mechanism_evidence.py`.
