#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${DELTA_BRIDGE_PYTHON:-$ROOT/.venv/bin/python}
exec "$PYTHON" "$ROOT/bridge_ctl.py" "${1:-status}"
