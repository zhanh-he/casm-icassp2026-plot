#!/usr/bin/env bash

set -euo pipefail

# Always clean the LaTeX project containing this script, regardless of the
# caller's current working directory. The final PDF is intentionally kept.
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

find "$project_dir" -maxdepth 1 -type f \( \
  -name '*.aux' -o \
  -name '*.bbl' -o \
  -name '*.bcf' -o \
  -name '*.blg' -o \
  -name '*.dvi' -o \
  -name '*.fdb_latexmk' -o \
  -name '*.fls' -o \
  -name '*.glg' -o \
  -name '*.glo' -o \
  -name '*.gls' -o \
  -name '*.idx' -o \
  -name '*.ilg' -o \
  -name '*.ind' -o \
  -name '*.lof' -o \
  -name '*.log' -o \
  -name '*.lot' -o \
  -name '*.nav' -o \
  -name '*.out' -o \
  -name '*.run.xml' -o \
  -name '*.snm' -o \
  -name '*.synctex.gz' -o \
  -name '*.toc' -o \
  -name '*.vrb' -o \
  -name '*.xdv' \
\) -print -delete
