#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${DELTA_BRIDGE_PYTHON:-$ROOT/.venv/bin/python}
RUNTIME_DIR=${XDG_RUNTIME_DIR:?User session required}
mkdir -p "$RUNTIME_DIR/systemd/user"
cat > "$RUNTIME_DIR/systemd/user/delta-llm-bridge.service" <<EOF
[Unit]
Description=Delta OpenRouter and local LLM bridge
BindsTo=delta-local.service
PartOf=delta-local.service
After=delta-local.service
[Service]
ExecStart="$PYTHON" -m uvicorn bridge:create_app --factory --app-dir "$ROOT" --host 127.0.0.1 --port 8092 --no-access-log
KillMode=control-group
TimeoutStopSec=8
Restart=no
EOF
systemctl --user daemon-reload
systemctl --user start delta-llm-bridge.service
