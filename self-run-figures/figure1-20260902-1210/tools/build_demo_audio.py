#!/usr/bin/env python3
"""Build compressed full-example audio for the public listening demo."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


FIGURE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = FIGURE_ROOT / "config" / "public_demo_audio.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "audio_root",
        type=Path,
        help="Directory containing the configured source WAV files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to build the public demo audio.")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    output_root = REPO_ROOT / "docs" / "audio"
    output_root.mkdir(parents=True, exist_ok=True)

    for case_id, selection in config["cases"].items():
        source = args.audio_root / selection["source_file"]
        output = output_root / selection["output_file"]
        duration = float(selection["duration_seconds"])
        fade_out_start = max(0.0, duration - 0.04)
        if not source.is_file():
            raise SystemExit(f"Missing source audio for {case_id}: {source}")
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(selection["start_seconds"]),
                "-t",
                str(duration),
                "-i",
                str(source),
                "-map_metadata",
                "-1",
                "-ac",
                "1",
                "-ar",
                "44100",
                "-af",
                f"afade=t=in:st=0:d=0.02,afade=t=out:st={fade_out_start}:d=0.04",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "112k",
                str(output),
            ],
            check=True,
        )
        print(output)


if __name__ == "__main__":
    main()
