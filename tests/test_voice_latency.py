import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from delta_contracts.config import Settings
from delta_contracts.devices import EmptyPayload
from delta_contracts.errors import DeltaError
from delta_contracts.tools import ToolCall
from delta_core.assistant.service import AssistantService
from delta_core.db import Base
from delta_core.llm.base import LLMTurn
from delta_core.llm.openrouter import OpenRouterLLMProvider
from delta_core.main import create_app
from delta_core.tools.registry import LocalTool, ToolRegistry
from delta_core.voice.stt import WhisperSTTProvider
from delta_core.voice.telemetry import VoiceTimings


@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/core.db', service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    return app


@pytest.mark.parametrize('message,name,data', [
    ('создай задачу проверить API', 'tasks.create', {'title':'проверить API'}),
    ('заверши задачу 123', 'tasks.complete', {'title':'проверить API', 'status':'done'}),
    ('открой диплом', 'workspaces.launch', {'success':True, 'results':[{'success':True}], 'message':'Launched'}),
    ('покажи устройства', 'devices.list', [{'display_name':'Mac', 'status':'online'}]),
    ('включи свет', 'iot.set_light', {'enabled':True}),
])
async def test_fast_path_exactly_one_tool_and_one_completion(app, message, name, data):
    handler = AsyncMock(return_value=data)
    registry = ToolRegistry(app.state.services)
    registry.register(LocalTool(name, name, EmptyPayload, handler, []))
    router = SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(calls=[ToolCall(name=name)])))
    smart = SimpleNamespace(respond=AsyncMock(side_effect=AssertionError('Unexpected second LLM completion')))
    timings = VoiceTimings()
    response = await AssistantService(app.state.engine, registry, smart, router).message(message, timings=timings)
    assert response['execution_path'] == 'fast'
    assert response['tool_results'][0]['success']
    assert response['assistant_text']
    handler.assert_awaited_once()
    router.respond.assert_awaited_once()
    smart.respond.assert_not_called()
    assert timings.router_calls == 1 and timings.response_generation_calls == 0


async def test_smart_summary_keeps_full_pipeline_and_never_reexecutes(app):
    handler = AsyncMock(return_value=[])
    registry = ToolRegistry(app.state.services)
    registry.register(LocalTool('devices.list', 'List devices', EmptyPayload, handler, []))
    smart = SimpleNamespace(respond=AsyncMock(side_effect=[LLMTurn(calls=[ToolCall(name='devices.list')]), LLMTurn(text='Объяснение')]))
    router = SimpleNamespace(respond=AsyncMock(side_effect=AssertionError('Not a simple command')))
    result = await AssistantService(app.state.engine, registry, smart, router).message('Покажи устройства и объясни их состояние')
    assert result['execution_path'] == 'smart' and result['assistant_text'] == 'Объяснение'
    assert smart.respond.await_count == 2
    handler.assert_awaited_once()
    router.respond.assert_not_called()
    assert smart.respond.call_args_list[1].args[0][-1]['role'] == 'tool'


@pytest.mark.parametrize('data', [{'success':False, 'message':'Partial launch'}, {'success':True, 'results':[]}])
async def test_partial_or_unknown_result_uses_smart_without_replaying(app, data):
    handler = AsyncMock(return_value=data)
    registry = ToolRegistry(app.state.services)
    registry.register(LocalTool('workspaces.launch', 'Launch', EmptyPayload, handler, []))
    router = SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(calls=[ToolCall(name='workspaces.launch')])))
    smart = SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(text='Проверьте привязку пространства.')))
    result = await AssistantService(app.state.engine, registry, smart, router).message('открой диплом')
    assert result['execution_path'] == 'smart'
    assert smart.respond.await_count == 1
    handler.assert_awaited_once()


async def test_smart_duplicate_new_call_id_does_not_repeat_action(app):
    handler = AsyncMock(return_value={'title':'Done'})
    registry = ToolRegistry(app.state.services)
    registry.register(LocalTool('tasks.create', 'Create', EmptyPayload, handler, []))
    provider = SimpleNamespace(respond=AsyncMock(side_effect=[
        LLMTurn(calls=[ToolCall(id='first', name='tasks.create')]),
        LLMTurn(calls=[ToolCall(id='new-id', name='tasks.create')]),
    ]))
    result = await AssistantService(app.state.engine, registry, provider).message('создай задачу и объясни')
    handler.assert_awaited_once()
    assert len(result['tool_results']) == 1
    assert 'Повторное' in result['assistant_text']


@pytest.mark.parametrize('supported,expected', [({'int8','float32'}, 'int8'), ({'float32'}, 'float32')])
async def test_whisper_constructed_once_at_startup_and_reused(monkeypatch, tmp_path, supported, expected):
    model = SimpleNamespace(transcribe=Mock(side_effect=lambda *a, **kw: (iter([SimpleNamespace(text='команда')]), None)))
    factory = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=factory))
    monkeypatch.setitem(sys.modules, 'ctranslate2', SimpleNamespace(get_supported_compute_types=lambda device:supported))
    provider = WhisperSTTProvider('base', str(tmp_path), 60, 'ru')
    monkeypatch.setattr(provider, '_decode', lambda audio: 'decoded-audio')
    await provider.startup()
    await provider.startup()
    assert await provider.transcribe(b'one') == 'команда'
    assert await provider.transcribe(b'two') == 'команда'
    factory.assert_called_once()
    assert factory.call_args.kwargs['compute_type'] == expected
    assert factory.call_args.kwargs['local_files_only'] is True
    assert model.transcribe.call_count == 2
    assert model.transcribe.call_args.kwargs == dict(language='ru', beam_size=1, vad_filter=True,
        word_timestamps=False, condition_on_previous_text=False, temperature=0)


async def test_failed_startup_never_downloads_or_retries_in_request(monkeypatch, tmp_path):
    factory = Mock(side_effect=RuntimeError('no model'))
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=factory))
    monkeypatch.setitem(sys.modules, 'ctranslate2', SimpleNamespace(get_supported_compute_types=lambda device:{'int8'}))
    provider = WhisperSTTProvider('missing', str(tmp_path), 60)
    monkeypatch.setattr(provider, '_decode', lambda audio: 'decoded')
    await provider.startup()
    for _ in range(2):
        with pytest.raises(DeltaError) as error:
            await provider.transcribe(b'audio')
        assert error.value.code == 'STT_UNAVAILABLE'
    factory.assert_called_once()


def test_application_initializes_stt_before_accepting_requests(app):
    app.state.stt.startup = AsyncMock()
    with TestClient(app):
        app.state.stt.startup.assert_awaited_once()


async def test_activity_is_deferred_but_history_is_durable(app):
    from sqlalchemy.orm import Session
    from delta_core.assistant.models import Interaction
    tasks = BackgroundTasks()
    assistant = app.state.assistant
    write = Mock(wraps=assistant.write_events)
    assistant.write_events = write
    response = await assistant.message('покажи устройства', background=tasks)
    write.assert_not_called()
    with Session(app.state.engine) as session:
        assert session.get(Interaction, response['id']) is not None
    await tasks()
    write.assert_called_once()
    assert any(event[0] == 'TOOL_COMPLETED' for event in write.call_args.args[0])


async def test_router_uses_role_model_and_low_latency_options():
    def handler(request):
        body = json.loads(request.content)
        assert body['model'] == 'router-model'
        assert body['max_tokens'] == 512
        assert body['provider'] == {'sort':'latency'}
        assert body['reasoning'] == {'enabled':False}
        return httpx.Response(200,json={'choices':[{'message':{'content':'Уточните команду'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenRouterLLMProvider('fake', 'router-model', client, router=True, max_tokens=512)
        assert (await provider.respond([],[],{})).text == 'Уточните команду'


def test_separate_model_settings_share_only_the_llm_client(tmp_path):
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/models.db',
        llm_provider='openrouter', delta_router_model='fast-model', delta_assistant_model='smart-model', service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app):
        assert app.state.assistant.router.model == 'fast-model'
        assert app.state.assistant.provider.model == 'smart-model'
        assert app.state.assistant.router.client is app.state.assistant.provider.client
        assert app.state.assistant.router.client is not app.state.http
        assert 'authorization' not in app.state.llm_http.headers


def test_voice_timings_and_optional_tts_preserve_single_execution(app):
    # Retain coverage of the LLM fallback's original one-completion fast path.
    app.state.assistant.local_router = None
    app.state.tts = SimpleNamespace(synthesize=AsyncMock(return_value=b'test-wav-bytes'))
    app.state.stt.transcribe = AsyncMock(return_value='покажи устройства')
    with TestClient(app, headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        result = client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')}).json()
        assert result['audio_available']
        timings = result['timings']
        assert timings['tts_status'] == 'ok' and timings['execution_path'] == 'fast'
        assert timings['response_generation_calls'] == 0 and timings['router_calls'] == 1
        assert all(timings[name] >= 0 for name in ['upload_ms','stt_ms','router_ms','tool_ms','response_generation_ms','tts_ms','server_total_ms'])
        app.state.tts.synthesize.assert_awaited_once_with(result['assistant_text'])
        assert len(result['tool_results']) == 1
        app.state.tts.synthesize = AsyncMock(side_effect=RuntimeError('offline'))
        result = client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')}).json()
        assert result['tool_results'][0]['success'] and not result['audio_available']
        assert result['timings']['tts_status'] == 'unavailable'


def test_stt_error_has_timings_without_claiming_tts_ran(app):
    app.state.stt.transcribe = AsyncMock(side_effect=DeltaError('STT_UNAVAILABLE','offline',503))
    with TestClient(app, headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        response = client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')})
        assert response.status_code == 503
        assert response.json()['timings']['stt_ms'] >= 0
        assert response.json()['timings']['tts_status'] == 'not_configured'


def test_failed_activity_write_cannot_fail_completed_voice_response(app, monkeypatch):
    import delta_core.assistant.service as service_module
    def broken(*args, **kwargs):
        raise RuntimeError('Activity storage unavailable')
    monkeypatch.setattr(service_module, 'record_event', broken)
    with TestClient(app, headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        result = client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')})
        assert result.status_code == 200 and result.json()['tool_results'][0]['success']
        assert len(client.get('/api/v1/assistant/history').json()) == 1


async def test_activity_is_sent_after_http_response_body(app):
    events = []
    app.state.assistant.write_events = lambda batch: events.append('activity')
    async def observed(scope, receive, send):
        async def capture(message):
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                events.append('response_sent')
            await send(message)
        await app(scope, receive, capture)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=observed), base_url='http://test',
                                headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        response = await client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')})
    assert response.status_code == 200
    assert events.index('response_sent') < events.index('activity')
