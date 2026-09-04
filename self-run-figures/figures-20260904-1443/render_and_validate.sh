#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON:-}"

if [[ -z "$python_bin" ]]; then
    if [[ -x "$script_dir/.venv/bin/python" ]]; then
        python_bin="$script_dir/.venv/bin/python"
    else
        python_bin="python3"
    fi
fi

"$python_bin" "$script_dir/plot_mechanism_evidence.py" \
    --data-dir "$script_dir/data" \
    --figure-dir "$script_dir/figures" \
    "$@"

"$python_bin" "$script_dir/validate_mechanism_evidence.py" \
    --data-dir "$script_dir/data" \
    --report-dir "$script_dir/qa"

echo "Figures: $script_dir/figures"
echo "QA:      $script_dir/qa/qa_report.md"
