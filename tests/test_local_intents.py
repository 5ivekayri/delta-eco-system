import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import create_model
from delta_contracts.config import Settings
from delta_contracts.devices import EmptyPayload, StrictModel
from delta_contracts.tasks import TaskCreate, TaskFilter, TaskID
from delta_contracts.tools import ToolCall, ToolResult
from delta_contracts.workspaces import LaunchInput
from delta_core.assistant.intents import IntentDecision, LocalIntentRouter, RegistryTaskLookup
from delta_core.assistant.service import AssistantService
from delta_core.db import Base
from delta_core.llm.base import LLMTurn
from delta_core.main import create_app
from delta_core.tools.registry import LocalTool, ToolRegistry
from delta_core.voice.telemetry import VoiceTimings
from scripts.benchmark_intents import equal_slots, specifications

CORPUS = json.loads((Path(__file__).resolve().parents[1] / 'benchmarks/russian_commands.json').read_text())


@pytest.mark.parametrize('command', CORPUS['commands'], ids=lambda command: command['text'])
async def test_russian_corpus(command):
    router = LocalIntentRouter(AsyncMock(return_value=CORPUS['tasks']))
    decision = await router.route(command['text'], specifications(), CORPUS['context'])
    assert (decision.call.name if decision.call else None) == command['intent']
    if command['intent']:
        assert decision.confidence >= .9
        assert equal_slots(decision.slots, command['slots'])


@pytest.mark.parametrize('phrase', [
    'Не надо включать свет', 'Включи свет и выключи компьютер',
    'Добавь задачу проверить отчёт, а потом удали её', 'Покажи устройства кроме ноутбука',
    'Включи свет если я дома', 'Выключи свет завтра', 'Открой Диплом на другом компьютере',
    'Покажи задачи с высоким приоритетом', 'Покажи задачи по диплому',
    'Добавь задачу проверить отчёт с высоким приоритетом',
    'Создай задачу купить молоко, выключи свет',
    'Создай задачу купить молоко\nпокажи устройства',
    'Покажи невыполненные задачи',  # Includes todo AND in_progress; the API takes one status.
    'Добавь задачу проверить отчёт по дипломной работе',
    'Покажи устройство Кабинет',
])
async def test_unsupported_or_compound_requests_fall_back(phrase):
    decision = await LocalIntentRouter().route(phrase, specifications(), CORPUS['context'])
    assert decision.call is None


async def test_title_lookup_exact_unique_only_and_schema_validation():
    lookup = AsyncMock(return_value=CORPUS['tasks'])
    router = LocalIntentRouter(lookup)
    decision = await router.route('Заверши задачу «проверить отчет»', specifications(), {})
    assert decision.call.arguments == {'id':CORPUS['tasks'][1]['id']}
    lookup.assert_awaited_once()
    lookup.return_value = [CORPUS['tasks'][0], {**CORPUS['tasks'][0], 'id':'other-id', 'status':'done'}]
    assert (await router.route('Заверши задачу купить молоко', specifications(), {})).call is None
    lookup.return_value = [{'title':'купить молоко','id':'invalid-uuid'}]
    assert (await router.route('Заверши задачу купить молоко', specifications(), {})).call is None


async def test_unavailable_disabled_and_incompatible_tools_do_not_route_or_lookup():
    lookup = AsyncMock()
    router = LocalIntentRouter(lookup)
    for specs in [[], [{'name':'tasks.complete','enabled':False}]]:
        assert (await router.route('Заверши задачу купить молоко', specs, {})).call is None
    lookup.assert_not_called()
    incompatible = [{'name':'iot.set_light','input_schema':EmptyPayload.model_json_schema()}]
    assert (await router.route('Включи свет', incompatible, {})).call is None
    assert (await router.route('Покажи устройства', [], {})).call is None


async def test_workspace_targets_must_be_unambiguous():
    router = LocalIntentRouter()
    context = CORPUS['context']
    duplicated = {**context, 'workspaces':context['workspaces'] * 2}
    assert (await router.route('Открой Диплом', specifications(), duplicated)).call is None
    duplicated = {**context, 'devices':context['devices'] * 2}
    assert (await router.route('Открой Диплом на Ноутбук', specifications(), duplicated)).call is None
    assert (await router.route('Открой Диплом на этом компьютере', specifications(), {**context, 'device_id':None})).call is None
    decision = await router.route('Открой Диплом на Кабинет', specifications(), context)
    assert decision.call.arguments == {'workspace_id':context['workspaces'][0]['id'], 'device_id':context['devices'][1]['id']}


@pytest.mark.parametrize('phrase,status', [('Покажи новые задачи','todo'), ('Покажи выполненные задачи','done'), ('Покажи задачи в работе','in_progress')])
async def test_task_status_arguments(phrase, status):
    decision = await LocalIntentRouter().route(phrase, specifications(), {})
    assert decision.call.arguments == {'status':status}


async def test_singular_device_list_variant_without_a_target():
    decision = await LocalIntentRouter().route('Покажи устройство.', specifications(), {})
    assert decision.call.name == 'devices.list' and decision.call.arguments == {}


@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/local.db',service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    return app


@pytest.mark.parametrize('phrase,name,schema,data', [
    ('Покажи устройства', 'devices.list', EmptyPayload, []),
    ('Добавь задачу купить молоко', 'tasks.create', TaskCreate, {'title':'купить молоко'}),
    ('Покажи задачи', 'tasks.list', TaskFilter, [{'title':'купить молоко'}]),
    ('Заверши задачу купить молоко', 'tasks.complete', TaskID, {'title':'купить молоко','status':'done'}),
    ('Открой Диплом на Ноутбук', 'workspaces.launch', LaunchInput, {'success':True,'results':[{'success':True}]}),
    ('Выключи свет', 'iot.set_light', create_model('Light', __base__=StrictModel, enabled=(bool,...)), {'enabled':False}),
    ('Какая температура', 'iot.get_temperature', EmptyPayload, {'temperature':23.0}),
])
async def test_all_local_tools_execute_once_with_zero_llm_calls(app, phrase, name, schema, data):
    # Workspace/device context is the Core-owned data normally populated by CRUD.
    from delta_core.devices.models import Device
    from delta_core.workspaces.models import Workspace
    from sqlalchemy.orm import Session
    with Session(app.state.engine) as session:
        for workspace in CORPUS['context']['workspaces']:
            session.add(Workspace(**workspace))
        for device in CORPUS['context']['devices']:
            session.add(Device(**device, device_uid=device['id'], hostname=device['display_name'], os='macos',
                               architecture='x86_64', username='test', last_seen=datetime.now(timezone.utc),
                               agent_version='test', capabilities=[]))
        session.commit()
    registry = ToolRegistry(app.state.services)
    handler = AsyncMock(return_value=data)
    registry.register(LocalTool(name, name, schema, handler, []))
    if name == 'tasks.complete':
        registry.register(LocalTool('tasks.list', 'List', TaskFilter, AsyncMock(return_value=CORPUS['tasks']), []))
    provider = SimpleNamespace(respond=AsyncMock(side_effect=AssertionError('No LLM allowed')))
    timings = VoiceTimings()
    service = AssistantService(app.state.engine, registry, provider,
                               local_router=LocalIntentRouter(RegistryTaskLookup(registry)))
    result = await service.message(phrase, timings=timings)
    assert result['route_source'] == 'local' and result['confidence'] >= .9
    assert result['execution_path'] == 'fast' and result['tool_results'][0]['success']
    handler.assert_awaited_once()
    provider.respond.assert_not_called()
    assert timings.router_calls == timings.response_generation_calls == 0
    assert timings.local_router_ms > 0
    if name == 'tasks.complete':
        registry.local['tasks.list'].handler.assert_awaited_once()
        assert handler.call_args.args[0].id.hex == CORPUS['tasks'][0]['id'].replace('-', '')


@pytest.mark.parametrize('confidence,threshold,expected', [(.99,.9,'local'), (.8,.9,'llm'), (.9,.9,'local'), (.99,1.0,'llm')])
async def test_replaceable_router_and_threshold(app, confidence, threshold, expected):
    classifier = SimpleNamespace(route=AsyncMock(return_value=IntentDecision(ToolCall(name='devices.list'), confidence)))
    provider = SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(text='Уточните запрос')))
    timings = VoiceTimings()
    service = AssistantService(app.state.engine, app.state.tools, provider,
                               local_router=classifier, local_threshold=threshold)
    result = await service.message('неизвестная классификатору фраза', timings=timings)
    assert result['route_source'] == expected
    assert result['confidence'] == confidence
    assert provider.respond.await_count == (expected == 'llm')


async def test_complex_request_keeps_llm_fallback(app):
    provider = SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(text='Объяснение')))
    service = AssistantService(app.state.engine, app.state.tools, provider, local_router=LocalIntentRouter())
    result = await service.message('Покажи устройства и объясни их состояние')
    assert result['route_source'] == 'llm' and result['assistant_text'] == 'Объяснение'
    provider.respond.assert_awaited_once()


async def test_local_tool_failure_does_not_retry_or_use_llm(app):
    registry = ToolRegistry(app.state.services)
    handler = AsyncMock(return_value={'success':False,'message':'Service failed'})
    registry.register(LocalTool('devices.list','List',EmptyPayload,handler,[]))
    provider = SimpleNamespace(respond=AsyncMock(side_effect=AssertionError('No LLM')))
    service = AssistantService(app.state.engine,registry,provider,local_router=LocalIntentRouter())
    result = await service.message('Покажи устройства')
    assert 'Service failed' in result['assistant_text']
    handler.assert_awaited_once()
    provider.respond.assert_not_called()


async def test_task_resolver_uses_registry_and_failed_lookup_falls_back():
    registry = SimpleNamespace(execute=AsyncMock(return_value=ToolResult(tool='tasks.list',success=False,message='Offline')))
    router = LocalIntentRouter(RegistryTaskLookup(registry))
    assert (await router.route('Заверши задачу купить молоко', specifications(), {})).call is None
    registry.execute.assert_awaited_once()
    assert registry.execute.call_args.args[0].name == 'tasks.list'


def test_voice_http_local_telemetry_without_openrouter(app):
    app.state.assistant.provider.respond = AsyncMock(side_effect=AssertionError('No remote calls'))
    with TestClient(app,headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        response = client.post('/api/v1/assistant/voice',files={'audio':('command.wav',b'test','audio/wav')})
        assert response.status_code == 200
        timings = response.json()['timings']
        assert timings['route_source'] == 'local' and timings['confidence'] >= .9
        assert timings['router_calls'] == timings['response_generation_calls'] == 0
        assert timings['local_router_ms'] >= 0
