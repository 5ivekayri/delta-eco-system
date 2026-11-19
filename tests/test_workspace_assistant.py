from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from delta_contracts.tools import ToolCall
from delta_core.llm.base import LLMTurn
from delta_core.assistant.responses import requested_action
from test_workspaces import setup
from test_voice import wav


def test_text_creation_and_duplicate(setup):
    app, client, _ = setup
    for index in range(2):
        response = client.post('/api/v1/assistant/message', json={
            'message': 'Создай рабочее пространство Диплом'})
        assert response.status_code == 200
        body = response.json()
        assert len(body['tool_results']) == 1
        assert body['tool_results'][0]['tool'] == 'workspaces.create'
        assert body['tool_results'][0]['success'] is (index == 0)
        if index == 0:
            assert 'Рабочее пространство создано: Диплом' in body['assistant_text']
        else:
            assert body['tool_results'][0]['error_code'] == 'WORKSPACE_EXISTS'
    assert len(client.get('/api/v1/workspaces').json()) == 1


def test_missing_name_clarifies(setup):
    _, client, _ = setup
    body = client.post('/api/v1/assistant/message', json={
        'message': 'Создай рабочее пространство'}).json()
    assert not body['tool_calls']
    assert '?' in body['assistant_text']
    assert client.get('/api/v1/workspaces').json() == []


def test_voice_llm_creation_with_binding(setup):
    app, client, device = setup
    transcript = 'Создай рабочее пространство Исследование с описанием Анализ данных и браузером на этом компьютере'
    app.state.stt.transcribe = AsyncMock(return_value=transcript)
    provider = AsyncMock()
    provider.respond.side_effect = [
        LLMTurn(calls=[ToolCall(name='workspaces.create', arguments={
            'name': 'Исследование', 'description': 'Анализ данных',
            'binding': {'device_id': device, 'apps': ['browser'], 'urls': ['https://example.com']}})]),
        LLMTurn(text='Рабочее пространство создано.'),
    ]
    app.state.assistant.provider = provider
    app.state.assistant.router = provider
    app.state.devices.dispatch = AsyncMock()
    response = client.post('/api/v1/assistant/voice', data={'device_id': device},
                           files={'audio': ('voice.wav', wav(), 'audio/wav')})
    assert response.status_code == 200
    body = response.json()
    assert body['transcript'] == transcript
    assert len(body['tool_results']) == 1 and body['tool_results'][0]['success']
    rows = client.get('/api/v1/workspaces').json()
    assert len(rows) == 1
    assert rows[0]['description'] == 'Анализ данных'
    assert rows[0]['bindings'][0]['device_id'] == device
    assert rows[0]['bindings'][0]['apps'] == ['browser']
    app.state.devices.dispatch.assert_not_called()
    specs = provider.respond.call_args_list[0].args[1]
    assert any(s['name'] == 'workspaces.create' for s in specs)
    history = client.get('/api/v1/assistant/history').json()
    assert history[-1]['tool_results'][0]['data']['id'] == rows[0]['id']


@pytest.mark.parametrize('overrides,code', [
    ({'device_id': str(uuid4())}, 'DEVICE_NOT_FOUND'),
    ({'apps': ['terminal']}, 'TOOL_VALIDATION_ERROR'),
    ({'urls': ['file:///etc/passwd']}, 'TOOL_VALIDATION_ERROR'),
    ({'apps': [], 'urls': []}, 'TOOL_VALIDATION_ERROR'),
])
async def test_invalid_binding_rolls_back(setup, overrides, code):
    app, client, device = setup
    result = await app.state.tools.execute(ToolCall(name='workspaces.create', arguments={
        'name': 'Invalid', 'binding': {'device_id': device, 'apps': ['browser'], **overrides}}))
    assert not result.success and result.error_code == code
    assert client.get('/api/v1/workspaces').json() == []


@pytest.mark.parametrize('text', [
    'Создай рабочее пространство Диплом', 'Пожалуйста, создай воркспейс Диплом',
    'Create a new workspace Thesis', 'Добавь новое пространство Учёба',
])
def test_creation_action_kind(text):
    assert requested_action(text) == 'workspaces.create'


def test_llm_cannot_claim_creation_without_tool(setup):
    app, client, _ = setup
    provider = AsyncMock()
    provider.respond.return_value = LLMTurn(text='Пространство создано!')
    app.state.assistant.router = provider
    result = client.post('/api/v1/assistant/message', json={
        'message': 'Создай воркспейс Диплом'}).json()
    assert 'Действие пока не выполнено' in result['assistant_text']
    assert client.get('/api/v1/workspaces').json() == []
