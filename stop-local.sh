#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec .venv/bin/python scripts/manage_local.py stop
