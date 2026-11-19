import asyncio
import json
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi.testclient import TestClient
from delta_contracts.config import Settings
from delta_core.main import create_app
from delta_core.db import Base
from delta_core.assistant.identity import identity_question, IDENTITY_REPLY
from delta_core.llm.openrouter import OpenRouterLLMProvider
from delta_core.llm.telemetry import requests
from delta_contracts.errors import DeltaError


@pytest.mark.parametrize('question', [
    'Какая модель лежит в основе тебя?', 'Кто тебя создал?', 'Кто твой разработчик?',
    'На какой модели ты работаешь?', 'Назови твою базовую модель', 'Ты ChatGPT?',
    'What model are you?', 'Who created you?',
])
def test_identity_policy(question):
    assert identity_question(question)


@pytest.mark.parametrize('question', ['Какая модель лучше для перевода?', 'Открой модель в Blender',
    'Кто создал Linux?', 'Расскажи про NVIDIA', 'What model should I use for translation?', 'Какую модель ты рекомендуешь?', 'What model do you recommend?'])
def test_general_model_questions_are_allowed(question):
    assert not identity_question(question)


def test_identity_bypasses_model_and_log_is_opt_in(tmp_path):
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/db', service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    provider = AsyncMock()
    app.state.assistant.provider = app.state.assistant.router = provider
    with TestClient(app, headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        for enabled in (True, False, True):
            response = client.post('/api/v1/assistant/message', json={'message':'Какая модель лежит в основе тебя?'},
                                   headers={'X-Delta-LLM-Log':'1' if enabled else '0'})
            assert response.status_code == 200
            data = response.json()
            assert data['assistant_text'] == IDENTITY_REPLY
            assert data['tool_calls'] == []
            assert ('llm_requests' in data['timings']) is enabled
            if enabled: assert data['timings']['llm_requests'] == []
    provider.respond.assert_not_called()


async def test_actual_provider_metadata_and_failure(monkeypatch):
    for bridge, body, expected in [
        (False, {'model':'returned/model'}, 'openrouter'),
        (True, {'_delta_route':{'provider':'local','model':'Qwen.gguf','fallback':True}}, 'local'),
        (True, {}, 'bridge_unknown'),
    ]:
        if bridge: monkeypatch.setenv('DELTA_LLM_BRIDGE_URL','http://127.0.0.1:8092/v1')
        else: monkeypatch.delenv('DELTA_LLM_BRIDGE_URL', raising=False)
        body = {**body, 'choices':[{'message':{'content':'OK'}}]}
        token = requests.set([])
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200,json=body))) as client:
                await OpenRouterLLMProvider('secret-key','configured/model',client).respond([{'role':'user','content':'private text'}],[],{})
            entries = requests.get()
            assert len(entries) == 1 and entries[0]['provider'] == expected
            assert entries[0]['outcome'] == 'ok'
            if expected=='local': assert entries[0]['model']=='Qwen.gguf' and entries[0]['fallback']
            if expected=='openrouter': assert entries[0]['model']=='returned/model'
            assert 'secret-key' not in json.dumps(entries) and 'private text' not in json.dumps(entries)
        finally: requests.reset(token)
    monkeypatch.delenv('DELTA_LLM_BRIDGE_URL', raising=False)
    token = requests.set([])
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401,json={}))) as client:
            with pytest.raises(DeltaError):
                await OpenRouterLLMProvider('key','model',client).respond([],[],{})
        assert requests.get()[0]['outcome'] == 'error'
    finally: requests.reset(token)


async def test_parallel_requests_do_not_mix_metadata():
    async def run(model):
        token = requests.set([])
        try:
            async def reply(request):
                await asyncio.sleep(.01)
                return httpx.Response(200,json={'model':model,'choices':[{'message':{'content':'ok'}}]})
            async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
                await OpenRouterLLMProvider('key',model,client).respond([],[],{})
            return requests.get()
        finally: requests.reset(token)
    first, second = await asyncio.gather(run('first'), run('second'))
    assert [r['model'] for r in first] == ['first']
    assert [r['model'] for r in second] == ['second']


def test_text_and_voice_return_request_scoped_traces(tmp_path):
    from io import BytesIO
    import wave
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/db',
                             service_configs=[], stt_provider='mock', mock_stt_transcript='Привет'))
    Base.metadata.create_all(app.state.engine)
    wav = BytesIO()
    with wave.open(wav, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
        audio.writeframes(b'\0\0' * 1600)
    with TestClient(app, headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        for voice in (False, True):
            for enabled in (True, False):
                headers={'X-Delta-LLM-Log':'1' if enabled else '0'}
                response = (client.post('/api/v1/assistant/voice',files={'audio':('test.wav',wav.getvalue(),'audio/wav')}, headers=headers)
                            if voice else client.post('/api/v1/assistant/message',json={'message':'Привет'},headers=headers))
                assert response.status_code == 200
                timing = response.json()['timings']
                if enabled:
                    assert timing['llm_requests'][0]['provider'] == 'mock'
                else:
                    assert 'llm_requests' not in timing
