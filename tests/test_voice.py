from io import BytesIO
import wave
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from delta_contracts.config import Settings
from delta_contracts.errors import DeltaError
from delta_core.main import create_app
from delta_core.db import Base
from delta_core.voice.stt import WhisperSTTProvider

TOKEN = 'test-token-only-123456'


def wav():
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\0\0' * 1600)
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(delta_token=TOKEN, database_url=f'sqlite:///{tmp_path}/voice.db',
                              service_configs=[], stt_provider='mock', voice_max_bytes=4096))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app, headers={'Authorization': f'Bearer {TOKEN}'}) as connection:
        yield connection


def test_voice_pipeline_history_and_metadata(client):
    response = client.post('/api/v1/assistant/voice', files={'audio': ('voice.wav', wav(), 'audio/wav')})
    assert response.status_code == 200
    body = response.json()
    assert body['transcript'] == 'покажи устройства'
    assert body['stt_provider'] == 'mock' and body['audio_available'] is False
    assert body['tool_results'][0]['tool'] == 'devices.list'
    assert body['tool_results'][0]['success']
    history = client.get('/api/v1/assistant/history').json()
    assert history[-1]['user_message'] == body['transcript']
    assert client.get('/api/v1/assistant/voice/config').json()['max_bytes'] == 4096


@pytest.mark.parametrize('data,mime,status,code', [
    (b'', 'audio/wav', 422, 'EMPTY_AUDIO'),
    (b'text', 'text/plain', 415, 'INVALID_AUDIO_TYPE'),
    (b'0' * 4097, 'audio/wav', 413, 'AUDIO_TOO_LARGE'),
])
def test_rejected_audio_never_calls_stt(client, data, mime, status, code):
    client.app.state.stt.transcribe = AsyncMock()
    response = client.post('/api/v1/assistant/voice', files={'audio': ('audio', data, mime)})
    assert response.status_code == status
    assert response.json()['error_code'] == code
    client.app.state.stt.transcribe.assert_not_called()
    assert client.get('/api/v1/assistant/history').json() == []


def test_chunked_upload_limit_before_multipart(client):
    client.app.state.stt.transcribe = AsyncMock()
    response = client.post('/api/v1/assistant/voice', content=iter([b'0' * 35000, b'0' * 35000]),
                           headers={'Content-Type': 'multipart/form-data; boundary=boundary'})
    assert response.status_code == 413
    client.app.state.stt.transcribe.assert_not_called()


def test_voice_auth_and_device_validation(client):
    assert client.post('/api/v1/assistant/voice', headers={'Authorization': 'bad'},
                       files={'audio': ('audio', wav(), 'audio/wav')}).status_code == 401
    assert client.post('/api/v1/assistant/voice', data={'device_id': 'not-a-uuid'},
                       files={'audio': ('audio', wav(), 'audio/wav')}).status_code == 422


@pytest.mark.parametrize('failure', [None, DeltaError('STT_UNAVAILABLE', 'Model missing', 503)])
def test_stt_failure_does_not_execute_actions_and_text_survives(client, failure):
    client.app.state.stt.transcribe = AsyncMock(return_value=' ', side_effect=failure)
    response = client.post('/api/v1/assistant/voice', files={'audio': ('audio', wav(), 'audio/wav')})
    assert response.status_code == (503 if failure else 422)
    assert client.get('/api/v1/assistant/history').json() == []
    text = client.post('/api/v1/assistant/message', json={'message': 'покажи устройства'})
    assert text.status_code == 200 and text.json()['tool_results'][0]['success']


def test_transcript_survives_llm_error(client):
    client.app.state.assistant.message = AsyncMock(side_effect=DeltaError('LLM_UNAVAILABLE', 'offline', 503))
    response = client.post('/api/v1/assistant/voice', files={'audio': ('audio', wav(), 'audio/wav')})
    assert response.status_code == 503
    assert response.json()['transcript'] == 'покажи устройства'


async def test_whisper_busy_does_not_wait_for_another_job(tmp_path):
    provider = WhisperSTTProvider('small', str(tmp_path), 60)
    provider._lock.acquire()
    try:
        with pytest.raises(DeltaError) as error:
            await provider.transcribe(wav())
        assert error.value.code == 'STT_BUSY'
    finally:
        provider._lock.release()


def test_system_voice_skips_server_synthesis_without_repeating_tools(client):
    client.app.state.tts=type('TTS',(),{'synthesize':AsyncMock(return_value=wav())})()
    response=client.post('/api/v1/assistant/voice',data={'tts_mode':'system'},files={'audio':('voice.wav',wav(),'audio/wav')})
    assert response.status_code==200
    body=response.json()
    assert body['tts_mode']=='system' and body['timings']['tts_status']=='client'
    assert body['audio_available'] is False and len(body['tool_results'])==1
    client.app.state.tts.synthesize.assert_not_called()


def test_speech_fallback_only_synthesizes_never_calls_assistant(client):
    client.app.state.assistant.message=AsyncMock()
    client.app.state.tts=type('TTS',(),{'synthesize':AsyncMock(return_value=wav())})()
    response=client.post('/api/v1/assistant/voice/synthesize',json={'text':'Готово'})
    assert response.status_code==200 and response.json()['audio_base64']
    client.app.state.assistant.message.assert_not_called()
    client.app.state.tts.synthesize.assert_awaited_once_with('Готово')
    assert client.post('/api/v1/assistant/voice/synthesize',json={'text':'Готово'},headers={'Authorization':'bad'}).status_code==401
    for body in [{'text':''},{'text':'x'*10001},{'text':'ok','tool':'tasks.create'}]:
        assert client.post('/api/v1/assistant/voice/synthesize',json=body).status_code==422


def test_speech_fallback_disabled_and_timeout(client):
    assert client.post('/api/v1/assistant/voice/synthesize',json={'text':'Готово'}).status_code==503
    client.app.state.tts=type('TTS',(),{'synthesize':AsyncMock(side_effect=TimeoutError)})()
    assert client.post('/api/v1/assistant/voice/synthesize',json={'text':'Готово'}).json()['error_code']=='TTS_TIMEOUT'


def test_neural_voice_selection_and_fallback_never_repeat_action(client):
    from delta_core.voice.neural import NeuralTTSProvider
    tts = NeuralTTSProvider(client.app.state.settings, AsyncMock())
    tts.synthesize_profile = AsyncMock(return_value=(wav(), {'tts_provider':'piper','voice_id':'piper','tts_fallback_reason':'TTS_BUSY'}))
    client.app.state.tts = tts
    assistant = client.app.state.assistant
    assistant.message = AsyncMock(wraps=assistant.message)
    response = client.post('/api/v1/assistant/voice', data={'voice_id':'serena'}, files={'audio':('voice.wav',wav(),'audio/wav')})
    assert response.status_code == 200
    assert response.json()['tts_fallback_reason'] == 'TTS_BUSY'
    assert len(response.json()['tool_results']) == 1
    assistant.message.assert_awaited_once()
    assert tts.synthesize_profile.call_args.args[1:] == ('serena', False)
    assert client.post('/api/v1/assistant/voice', data={'voice_id':'invalid'}, files={'audio':('voice.wav',wav(),'audio/wav')}).status_code == 422
    assistant.message.assert_awaited_once()
