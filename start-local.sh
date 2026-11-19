#!/bin/sh
set -eu
cd "$(dirname "$0")"
if systemctl --user is-active --quiet delta-local.service; then
  echo 'Delta уже запущена: http://192.168.0.28:8081'
  exit 0
fi
systemd-run --user --unit=delta-local --collect --property="WorkingDirectory=$PWD" "$PWD/.venv/bin/python" "$PWD/scripts/manage_local.py" start
echo 'Delta запускается: http://192.168.0.28:8081. Журнал: journalctl --user -u delta-local'
