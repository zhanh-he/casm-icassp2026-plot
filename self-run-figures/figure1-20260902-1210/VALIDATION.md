# Validation Record

Validated on 2026-09-04 with the isolated `.venv` documented in `README.md`.

- Both raw OOF caches contain 2,001 beat logits and 2,001 downbeat logits.
- Both spectrograms have shape 2,001 x 128 and dtype float16.
- Ground-truth arrays in the OOF cache and frozen figure payload match.
- `sigmoid(raw_logits)` and the payload probabilities differ by at most 5e-6,
  explained by five-decimal JSON serialization.
- The rebuilt D3 HTML is byte-identical to the frozen reference.
- The notebook executed every code cell without an exception.
- Both static case figures were visually inspected for clipping and overlap.

Expected selected-window IBI MAE values:

| Case | Direct | Fixed Semi-Markov | DBN adjusted | CASM |
| --- | ---: | ---: | ---: | ---: |
| SMC 221, 6.14-24.14 s | 0.304386 | 0.212127 | 0.284283 | 0.144559 |
| SMC 117, 21.48-39.48 s | 0.211634 | 0.130188 | 0.105487 | 0.097110 |

Run the regression checks with:

```bash
.venv/bin/python tools/validate_bundle.py
```

These windows and the adjusted DBN are explanatory selections, not unbiased
aggregate benchmark measurements.
