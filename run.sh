#!/usr/bin/env bash
# One command to run the machine.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q -r requirements.txt
./.venv/bin/python -m machine.run "$@"
