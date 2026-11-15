from concurrent.futures import ThreadPoolExecutor
import json
import time
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from delta_contracts.tools import ToolCall
from delta_core.activity.models import ActivityEvent
from delta_core.assistant.models import Interaction
from delta_core.llm.base import LLMTurn
from test_devices import app, HEADERS, REGISTER


def test_terminal_routes_explicit_target_and_redacts_durable_data(app):
    call = ToolCall(id='run-1', name='devices.run_command', arguments={
        'device_name': 'Linux PC', 'command': 'printf private-command-body', 'timeout_seconds': 30})
    app.state.assistant.provider.respond = AsyncMock(side_effect=[LLMTurn(calls=[call]), LLMTurn(text='Код завершения 0.')])
    with TestClient(app) as client:
        with client.websocket_connect('/ws/agents', headers=HEADERS) as mac:
            mac.send_json(REGISTER)
            selected = mac.receive_json()['device_id']
            with client.websocket_connect('/ws/agents', headers=HEADERS) as linux:
                linux.send_json({**REGISTER, 'device_uid': 'linux-terminal', 'display_name': 'Linux PC',
                                 'os': 'linux', 'capabilities': ['run_command', 'command_access']})
                target = linux.receive_json()['device_id']
                with ThreadPoolExecutor() as pool:
                    future = pool.submit(client.post, '/api/v1/assistant/message', headers=HEADERS,
                                         json={'message': 'Выполни команду на Linux PC', 'device_id': selected})
                    command = linux.receive_json()
                    assert command['action'] == 'run_command'
                    assert command['payload']['command'] == 'printf private-command-body'
                    assert command['expires_at'] > time.time() + 25
                    linux.send_json({'type': 'command_result', 'command_id': command['command_id'],
                        'success': True, 'message': 'exit 0', 'data': {'exit_code': 0, 'stdout': 'private-output-body'}})
                    response = future.result(timeout=5)
                assert response.status_code == 200
                assert response.json()['tool_calls'][0]['arguments']['device_name'] == 'Linux PC'
    # Output is available to the current inference, but not stored automatically.
    messages = app.state.assistant.provider.respond.call_args.args[0]
    assert 'private-output-body' in json.dumps(messages)
    with Session(app.state.engine) as db:
        for event in db.scalars(select(ActivityEvent)):
            encoded = json.dumps(event.details)
            assert 'private-command-body' not in encoded and 'private-output-body' not in encoded
        history = db.scalar(select(Interaction))
        assert 'private-command-body' not in json.dumps(history.tool_calls)
        assert 'private-output-body' not in json.dumps(history.tool_results)


async def test_missing_target_and_old_client_cannot_execute(app):
    from delta_contracts.devices import Registration
    no_target = await app.state.tools.execute(ToolCall(id='1', name='devices.run_command', arguments={'command':'true'}))
    assert not no_target.success and no_target.error_code == 'DEVICE_REQUIRED'
    device, _ = await app.state.devices.register(Registration(**{**REGISTER, 'os':'linux'}), AsyncMock())
    denied = await app.state.tools.execute(ToolCall(id='2', name='devices.run_command', arguments={'device_id':device,'command':'true'}))
    assert not denied.success and denied.error_code == 'CAPABILITY_NOT_SUPPORTED'
    access = await app.state.tools.execute(ToolCall(id='3', name='devices.command_access', arguments={'device_id':device}))
    assert access.data['mode'] == 'off'


async def test_platform_and_remote_privilege_selection_rejected(app):
    from delta_contracts.devices import Registration
    device, _ = await app.state.devices.register(Registration(**REGISTER), AsyncMock())
    result = await app.state.tools.execute(ToolCall(id='1',name='devices.run_command',arguments={'device_id':device,'command':'true'}))
    assert not result.success and result.error_code == 'PLATFORM_UNSUPPORTED'
    result = await app.state.tools.execute(ToolCall(id='2',name='devices.run_command',arguments={'device_id':device,'command':'true','mode':'user'}))
    assert not result.success and result.error_code == 'TOOL_VALIDATION_ERROR'


def test_terminal_endpoint_requires_auth(app):
    with TestClient(app) as client:
        response = client.post('/api/v1/devices/nonexistent/commands', json={'action':'run_command','payload':{'command':'true'}})
        assert response.status_code == 401
