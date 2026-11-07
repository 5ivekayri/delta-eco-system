#!/bin/sh
# Restore original Core source/provider and restart Delta services.
set -eu
RUNTIME_DIR=${XDG_RUNTIME_DIR:?User session required}
systemctl --user stop delta-llm-bridge.service || true
rm -f "$RUNTIME_DIR/systemd/user/delta-local.service.d/llm-bridge.conf"
systemctl --user daemon-reload
systemctl --user restart delta-local.service
