#!/usr/bin/env bash
set -euo pipefail

if [[ -d .venv ]]; then
  source .venv/bin/activate
fi

export PYTHONUNBUFFERED=1
python -m app.main