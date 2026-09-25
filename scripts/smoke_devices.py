"""Exercise real host Agent ↔ running Core. Executes system_info only."""
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root / '.env')
token = values['DELTA_TOKEN']
headers = {'Authorization': f'Bearer {token}'}
environment = {**os.environ, 'DELTA_TOKEN': token}
with httpx.Client(base_url='http://127.0.0.1:8000', headers=headers, timeout=20) as client:
    agent = subprocess.Popen([sys.executable, '-m', 'delta_agent.main', '--name', 'Delta local verification',
                              '--config-dir', str(root / '.runtime' / 'smoke-agent')], cwd=root, env=environment)
    try:
        device = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            response = client.get('/api/v1/devices')
            response.raise_for_status()
            device = next((d for d in response.json() if d['display_name'] == 'Delta local verification' and d['status']=='online'), None)
            if device:
                break
            time.sleep(.25)
        assert device, 'Agent did not connect'
        response = client.post(f"/api/v1/devices/{device['id']}/commands", json={'action':'system_info'})
        response.raise_for_status()
        assert response.json()['success'], response.json()
        assert response.json()['data']['os'] in {'macos','windows','linux'}
        time.sleep(11)
        updated = client.get(f"/api/v1/devices/{device['id']}").json()
        assert updated['last_seen'] > device['last_seen'], 'Heartbeat did not advance'
        print('Real host registration, command/result and heartbeat passed.')
    finally:
        agent.terminate()
        agent.wait(timeout=10)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if client.get(f"/api/v1/devices/{device['id']}").json()['status'] == 'offline':
            print('Disconnect → offline passed.')
            break
        time.sleep(.25)
    else:
        raise AssertionError('Device remained online after disconnect')
