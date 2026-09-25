import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from delta_contracts.config import Settings
from delta_contracts.devices import CommandRequest, Registration
from delta_contracts.storage import utcnow
from delta_core.db import Base
from delta_core.main import create_app
from delta_core.devices.models import Device

TOKEN = "test-token-only-123456"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
REGISTER = dict(type="register", device_uid="test-uid", hostname="test-host", display_name="Test PC", os="macos",
                architecture="arm64", username="test-user", agent_version="0.1.0", capabilities=["system_info", "open_url"])


@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(delta_token=TOKEN, database_url=f"sqlite:///{tmp_path}/core.db", command_timeout=1))
    Base.metadata.create_all(app.state.engine)
    return app


def test_registration_heartbeat_dispatch_and_disconnect(app):
    with TestClient(app) as client:
        with client.websocket_connect('/ws/agents', headers=HEADERS) as socket:
            socket.send_json(REGISTER)
            ack = socket.receive_json()
            device_id = ack['device_id']
            assert client.get('/api/v1/devices', headers=HEADERS).json()[0]['status'] == 'online'
            before = client.get(f'/api/v1/devices/{device_id}', headers=HEADERS).json()['last_seen']
            socket.send_json({'type': 'heartbeat'})
            # A command round trip orders the preceding heartbeat processing.
            with ThreadPoolExecutor() as pool:
                future = pool.submit(client.post, f'/api/v1/devices/{device_id}/commands',
                                     json={'action': 'system_info'}, headers=HEADERS)
                command = socket.receive_json()
                socket.send_json({'type': 'command_result', 'command_id': 'unrelated-id', 'success': True, 'message': 'ignored'})
                socket.send_json({'type': 'command_result', 'command_id': command['command_id'],
                                  'success': True, 'message': 'Info received', 'data': {'os': 'macos'}})
                response = future.result(timeout=5)
            assert response.status_code == 200
            assert response.json()['data']['os'] == 'macos'
            details = client.get(f'/api/v1/devices/{device_id}', headers=HEADERS).json()
            assert details['last_seen'] >= before
            assert len(details['recent_commands']) == 2
            assert client.post(f'/api/v1/devices/{device_id}/commands', headers=HEADERS,
                               json={'action': 'open_url', 'payload': {'url': 'file:///etc/passwd'}}).status_code == 422
        assert client.get(f'/api/v1/devices/{device_id}', headers=HEADERS).json()['status'] == 'offline'
        assert client.post(f'/api/v1/devices/{device_id}/commands', headers=HEADERS,
                           json={'action': 'system_info'}).json()['error_code'] == 'DEVICE_OFFLINE'
        with client.websocket_connect('/ws/agents', headers=HEADERS) as socket:
            socket.send_json(REGISTER)
            assert socket.receive_json()['device_id'] == device_id
        assert len(client.get('/api/v1/devices', headers=HEADERS).json()) == 1


async def test_expiry_and_connection_replacement(app):
    manager = app.state.devices
    first = AsyncMock()
    device_id, old = await manager.register(Registration(**REGISTER), first)
    second = AsyncMock()
    _, current = await manager.register(Registration(**REGISTER), second)
    manager.disconnect(device_id, old)
    assert manager.get(device_id)['status'] == 'online'
    with Session(app.state.engine) as session:
        session.get(Device, device_id).last_seen = utcnow() - timedelta(minutes=1)
        session.commit()
    await manager.expire()
    assert manager.get(device_id)['status'] == 'offline'
    second.close.assert_awaited_once()


async def test_timeout_is_not_reported_as_success(app):
    manager = app.state.devices
    device_id, connection = await manager.register(Registration(**REGISTER), AsyncMock())
    result = await manager.dispatch(device_id, CommandRequest(action='system_info'))
    assert not result['success']
    assert result['error_code'] == 'COMMAND_TIMEOUT'
    assert not connection.pending


def test_websocket_requires_token(app):
    with TestClient(app) as client:
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws/agents'):
                pass
