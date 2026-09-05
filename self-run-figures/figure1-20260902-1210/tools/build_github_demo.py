#!/usr/bin/env python3
"""Build the static GitHub listening demo from the frozen Figure 1 payloads."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


FIGURE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = REPO_ROOT / "docs"
AUDIO_CONFIG_PATH = FIGURE_ROOT / "config" / "public_demo_audio.json"


def sanitize(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def versioned_asset(relative_path: str) -> str:
    path = DOCS_ROOT / relative_path
    return f"{relative_path}?v={sha256(path)[:12]}" if path.is_file() else relative_path


audio_config = json.loads(AUDIO_CONFIG_PATH.read_text(encoding="utf-8"))
cases = []
for case, label, rank, summary in (
    (
        "smc_117",
        "SMC 117",
        234,
        "Adjusted DBN reduces dense-path failures, yet unstable IBI transitions remain; CASM follows the local intervals.",
    ),
    (
        "smc_221",
        "SMC 221",
        301,
        "Adjusted DBN recovers a plausible variable-tempo path but remains less continuous than CASM.",
    ),
    (
        "gtzan_blues_00023",
        "GTZAN · Blues 00023",
        None,
        "CASM improves both event accuracy and metrical continuity over all four comparison decoders on this clean held-out track.",
    ),
    (
        "gtzan_metal_00026",
        "GTZAN · Metal 00026",
        None,
        "Direct and PLPDP are already strong, while CASM still recovers the most accurate and continuous beat path.",
    ),
    (
        "gtzan_pop_00053",
        "GTZAN · Pop 00053",
        None,
        "A difficult track for every decoder: CASM remains clearly ahead in F1 and continuity without changing the shared front-end.",
    ),
):
    payload_path = FIGURE_ROOT / "data" / "figure_payloads" / f"{case}.json"
    case_id = case.replace("_", "-")
    audio_selection = audio_config["cases"].get(case_id)
    cases.append(
        {
            "id": case_id,
            "label": label,
            "screen_rank": rank,
            "summary": summary,
            "public_audio": (
                {
                    "url": versioned_asset(f"audio/{audio_selection['output_file']}"),
                    "start_seconds": audio_selection["start_seconds"],
                    "duration_seconds": audio_selection["duration_seconds"],
                    "source_file": audio_selection["source_file"],
                }
                if audio_selection
                else None
            ),
            "data": sanitize(json.loads(payload_path.read_text(encoding="utf-8"))),
        }
    )

data_path = DOCS_ROOT / "data" / "cases.json"
data_path.parent.mkdir(parents=True, exist_ok=True)
data_path.write_text(
    json.dumps(cases, ensure_ascii=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)

fragment_path = FIGURE_ROOT / "reference" / "real-decoder-contrast.html"
fragment = fragment_path.read_text(encoding="utf-8")
base_style = """
<style>
:root {
  --foreground: #202327;
  --muted-foreground: #747a81;
  --popover-foreground: #202327;
  --popover: #ffffff;
  --border: #dce1e5;
  --viz-series-1: #409eff;
  --viz-series-2: #ff7a3d;
  --viz-series-3: #59c879;
  --viz-series-4: #d89b31;
  --viz-series-5: #9270ed;
  --viz-series-6: #2bb8b2;
  --font-sans: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--foreground);
  background: #fff;
  font-family: var(--font-sans);
}
* { box-sizing: border-box; }
html, body { margin: 0; min-width: 320px; background: #fff; }
body { padding: 2px 0 12px; }
.text-small { font-size: 12px; line-height: 1.45; }
.tabular-nums { font-variant-numeric: tabular-nums; }
.text-end { text-align: right; }
.form-label { color: var(--foreground); font-size: 12px; font-weight: 650; }
.form-select {
  display: block;
  width: 100%;
  min-height: 36px;
  margin-top: 5px;
  padding: 6px 32px 6px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  color: var(--foreground);
  font: inherit;
}
.form-range { accent-color: var(--viz-series-6); }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { padding: 8px 7px; border-bottom: 1px solid var(--border); }
.table th { font-weight: 680; text-align: left; }
.table th.text-end, .table td.text-end { text-align: right; }
</style>
"""
visualization = (
    "<!doctype html>\n<html lang=\"en\">\n<head>\n"
    "<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
    "<title>CASM decoder contrast visualization</title>\n"
    f"{base_style}</head>\n<body>\n{fragment}\n</body>\n</html>\n"
)
visualization_path = DOCS_ROOT / "visualization.html"
visualization_path.write_text(visualization, encoding="utf-8")

manifest = {
    "source_figure_fragment": str(fragment_path.relative_to(REPO_ROOT)),
    "source_figure_sha256": sha256(fragment_path),
    "case_data_sha256": sha256(data_path),
    "visualization_sha256": sha256(visualization_path),
    "case_count": len(cases),
    "audio_source": audio_config["source_archive_url"],
    "audio_download_mirror": audio_config["download_mirror_url"],
    "audio_download_script": audio_config["download_script_url"],
    "audio_citation": audio_config["citation"],
    "gtzan_audio_source": audio_config["gtzan_source_url"],
    "gtzan_audio_download_mirror": audio_config["gtzan_download_mirror_url"],
    "gtzan_audio_citation": audio_config["gtzan_citation"],
    "audio_policy": "Only the two selected SMC examples and three selected GTZAN examples are published; neither complete dataset is mirrored.",
    "audio_files": {
        selection["output_file"]: sha256(DOCS_ROOT / "audio" / selection["output_file"])
        for selection in audio_config["cases"].values()
        if (DOCS_ROOT / "audio" / selection["output_file"]).is_file()
    },
}
(DOCS_ROOT / "data" / "manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)

print(data_path)
print(visualization_path)
