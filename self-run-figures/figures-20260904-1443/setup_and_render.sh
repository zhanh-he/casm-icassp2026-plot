#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m venv "$script_dir/.venv"
"$script_dir/.venv/bin/python" -m pip install -r "$script_dir/requirements.txt"
PYTHON="$script_dir/.venv/bin/python" "$script_dir/render_and_validate.sh" "$@"
