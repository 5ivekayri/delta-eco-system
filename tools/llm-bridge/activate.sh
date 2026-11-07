#!/bin/sh
# Explicit activation: changes the running Core source overlay and restarts Delta services.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$ROOT/../.." && pwd)
OVERLAY=$REPO/apps/delta-core
RUNTIME_DIR=${XDG_RUNTIME_DIR:?Graphical user session required}
mkdir -p "$RUNTIME_DIR/systemd/user/delta-local.service.d"
cat > "$RUNTIME_DIR/systemd/user/delta-local.service.d/llm-bridge.conf" <<EOF
[Unit]
Wants=delta-llm-bridge.service
[Service]
Environment="PYTHONPATH=$OVERLAY:$REPO/shared/contracts"
Environment="DELTA_LLM_BRIDGE_URL=http://127.0.0.1:8092/v1"
EOF
systemctl --user daemon-reload
systemctl --user restart delta-local.service
count=0
until curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; do
 count=$((count+1))
 if [ "$count" -ge 90 ]; then echo 'Core did not become ready; inspect delta-local service logs.' >&2; exit 1; fi
 sleep 1
done
if ! systemctl --user is-active --quiet delta-llm-bridge.service; then "$ROOT/start.sh"; fi
printf '%s\n' 'Core bridge overlay activated. Original source folders unchanged.'
