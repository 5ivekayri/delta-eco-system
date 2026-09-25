#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv run --extra test pytest -q
uv build
cd apps/delta-control-center
npm test
npm run build
# Browser smoke checks additionally require local Core and Vite servers:
# npx playwright test
