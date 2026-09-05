# SMC MIREX and GTZAN listening examples

The demo contains two complete 40-second mono MP3 examples from SMC MIREX and
three complete 30-second mono examples from GTZAN:

| Demo case | Source file | Source interval |
|---|---|---:|
| SMC 117 | `SMC_117.wav` | 0.00-40.00 s |
| SMC 221 | `SMC_221.wav` | 0.00-40.00 s |
| GTZAN Blues 00023 | `blues.00023.wav` | 0.00-30.00 s |
| GTZAN Metal 00026 | `metal.00026.wav` | 0.00-30.00 s |
| GTZAN Pop 00053 | `pop.00053.wav` | 0.00-30.00 s |

Dataset citation:

> Holzapfel, A.; Davies, M. E. P.; Zapata, J. R.; Oliveira, J. L.; Gouyon, F.
> "Selective Sampling for Beat Tracking Evaluation." IEEE Transactions on
> Audio, Speech, and Language Processing, 20(9), 2539-2548, 2012.
> https://doi.org/10.1109/TASL.2012.2205244

Original dataset URL:
`http://smc.inescporto.pt/data/SMC_MIREX.zip`

Public author mirror used for recovery:
`https://bit.ly/33SlutJ`

The maintained download recipe is available in
[`nicolaus625/CMI-bench`](https://github.com/nicolaus625/CMI-bench/blob/main/data/SMC/download_smc.sh).

GTZAN citation:

> Tzanetakis, G.; Cook, P. "Musical Genre Classification of Audio Signals."
> IEEE Transactions on Speech and Audio Processing, 10(5), 293-302, 2002.

GTZAN dataset page: `http://marsyas.info/downloads/datasets.html`. The source
waveforms used by this demo were recovered from the public GTZAN mirror at
`https://huggingface.co/datasets/m-a-p/GTZAN`.

The visualization initially opens on selected 18-second analysis windows, but
the complete audio for all five examples supports playback after moving the
slider. The remainder of either dataset is not mirrored here.
