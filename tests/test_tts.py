import asyncio
import base64
from io import BytesIO
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import wave

import pytest
from fastapi.testclient import TestClient
from delta_contracts.config import Settings
from delta_contracts.errors import DeltaError
from delta_core.main import create_app
from delta_core.db import Base
from delta_core.voice.tts import MockTTSProvider, PiperTTSProvider, speech_text


def fake_voice():
    chunk = SimpleNamespace(sample_rate=22050, sample_width=2, sample_channels=1, audio_int16_bytes=b'\x10\x00' * 2205)
    return SimpleNamespace(config=SimpleNamespace(espeak_voice='ru',sample_rate=22050),
                           synthesize=Mock(side_effect=lambda text: iter([chunk])))


@pytest.fixture
def piper(tmp_path, monkeypatch):
    path = tmp_path / 'ru_RU-irina-medium.onnx'
    path.write_bytes(b'model')
    (tmp_path / (path.name + '.json')).write_text('{}')
    voice = fake_voice()
    factory = Mock(return_value=voice)
    monkeypatch.setitem(sys.modules, 'piper', SimpleNamespace(PiperVoice=SimpleNamespace(load=factory)))
    return PiperTTSProvider(str(path)), voice, factory


async def test_load_once_reuse_and_real_wav_contract(piper):
    provider, voice, factory = piper
    await provider.startup()
    await provider.startup()
    for _ in range(2):
        audio = await provider.synthesize('**Задача** добавлена.')
        with wave.open(BytesIO(audio),'rb') as wav:
            assert wav.getframerate() == 22050
            assert wav.getnchannels() == 1 and wav.getnframes() > 0
    factory.assert_called_once()
    assert factory.call_args.kwargs['use_cuda'] is False
    assert voice.synthesize.call_args.args[0] == 'Задача добавлена.'


async def test_missing_model_does_not_load_or_download_on_requests(monkeypatch, tmp_path):
    factory = Mock(side_effect=AssertionError('No loading during requests'))
    monkeypatch.setitem(sys.modules, 'piper', SimpleNamespace(PiperVoice=SimpleNamespace(load=factory)))
    provider = PiperTTSProvider(str(tmp_path/'missing.onnx'))
    await provider.startup()
    await provider.startup()
    for _ in range(2):
        with pytest.raises(DeltaError,match='Озвучивание недоступно'):
            await provider.synthesize('Привет')
    factory.assert_not_called()


async def test_wrong_language_startup_failure_never_uses_voice(piper):
    provider, voice, factory = piper
    voice.config.espeak_voice = 'ar'
    await provider.startup()
    assert provider._voice is None and provider.startup_error
    with pytest.raises(DeltaError):
        await provider.synthesize('Привет')
    voice.synthesize.assert_not_called()


async def test_text_duration_limits_and_busy(piper):
    provider, voice, _ = piper
    await provider.startup()
    provider._lock.acquire()
    try:
        with pytest.raises(DeltaError) as error:
            await provider.synthesize('Привет')
        assert error.value.code == 'TTS_BUSY'
    finally:
        provider._lock.release()
    with pytest.raises(DeltaError) as error:
        await provider.synthesize('я' * 1501)
    assert error.value.code == 'TTS_TOO_LONG'
    voice.synthesize.assert_not_called()
    provider.max_seconds = 0
    with pytest.raises(DeltaError) as error:
        await provider.synthesize('Привет')
    assert error.value.code == 'TTS_TOO_LONG'
    assert not provider._lock.locked()


async def test_cancelled_wait_keeps_single_worker_lock(piper):
    provider, voice, _ = piper
    await provider.startup()
    entered, release = Event(), Event()
    def synthesize(text):
        entered.set()
        release.wait(5)
        return iter([])
    voice.synthesize.side_effect = synthesize
    task = asyncio.create_task(provider.synthesize('Привет'))
    try:
        assert await asyncio.to_thread(entered.wait,2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(DeltaError) as error:
            await provider.synthesize('Второй запрос')
        assert error.value.code == 'TTS_BUSY'
    finally:
        release.set()
    for _ in range(100):
        if not provider._lock.locked():
            break
        await asyncio.sleep(.01)
    assert not provider._lock.locked()


def test_markdown_plain_speech():
    assert speech_text('## Готово\n**Задача** добавлена. [Ссылка](https://example.com)') == 'Готово Задача добавлена. Ссылка'
    text = speech_text('```python\nprint("secret code")\n```\n- Один\n- Два')
    assert 'print' not in text and 'Один' in text and 'Два' in text
    assert speech_text('[[phonemes]]') == 'phonemes'


@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(delta_token='test-token-only-123456',database_url=f'sqlite:///{tmp_path}/tts.db',service_configs=[],tts_provider='mock'))
    Base.metadata.create_all(app.state.engine)
    return app


def test_mock_voice_pipeline_synthesizes_once_and_preserves_history(app):
    app.state.tts.synthesize = AsyncMock(wraps=app.state.tts.synthesize)
    handler = app.state.tools.local['devices.list'].handler
    app.state.tools.local['devices.list'].handler = AsyncMock(wraps=handler)
    with TestClient(app,headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        body = client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')}).json()
        assert body['audio_available'] and body['tts_provider'] == 'mock'
        assert body['audio_mime'] == 'audio/wav'
        assert body['timings']['tts_status'] == 'ok' and body['timings']['router_calls'] == 0
        with wave.open(BytesIO(base64.b64decode(body['audio_base64'])),'rb') as wav:
            assert wav.getnframes() > 0
        app.state.tts.synthesize.assert_awaited_once()
        app.state.tools.local['devices.list'].handler.assert_awaited_once()
        saved = client.get('/api/v1/assistant/history').json()
        assert saved[-1]['assistant_text'] == body['assistant_text']
        assert 'audio_base64' not in saved[-1]
        assert client.get('/api/v1/assistant/voice/config').json()['tts_provider'] == 'mock'


@pytest.mark.parametrize('failure,code', [
    (DeltaError('TTS_BUSY','Занято',503),'TTS_BUSY'),
    (DeltaError('TTS_TOO_LONG','Слишком длинный ответ',422),'TTS_TOO_LONG'),
    (RuntimeError('bad model'),'TTS_UNAVAILABLE'),
])
def test_tts_errors_never_repeat_tool_or_lose_text(app, failure, code):
    handler = app.state.tools.local['devices.list'].handler
    app.state.tools.local['devices.list'].handler = AsyncMock(wraps=handler)
    app.state.tts.synthesize = AsyncMock(side_effect=failure)
    with TestClient(app,headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        response = client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')})
        body = response.json()
        assert response.status_code == 200
        assert not body['audio_available'] and body['tts_error'] == code and body['assistant_text']
        assert body['tool_results'][0]['success'] and body['timings']['tts_status'] == 'unavailable'
        app.state.tools.local['devices.list'].handler.assert_awaited_once()
        assert len(client.get('/api/v1/assistant/history').json()) == 1


def test_timeout_returns_text_without_waiting_for_speech(app):
    app.state.settings.tts_timeout_seconds = .1
    async def slow(text):
        await asyncio.sleep(5)
    app.state.tts.synthesize = slow
    with TestClient(app,headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        body = client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')}).json()
        assert body['tts_error'] == 'TTS_TIMEOUT' and body['assistant_text']
        assert body['timings']['tts_ms'] < 1500


def test_lifespan_initializes_tts_once(app):
    app.state.tts.startup = AsyncMock()
    with TestClient(app):
        app.state.tts.startup.assert_awaited_once()


def test_missing_piper_model_keeps_voice_and_text_routes_usable(tmp_path):
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/missing.db',
                              service_configs=[], tts_provider='piper', piper_model=str(tmp_path/'missing.onnx')))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app,headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        body = client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'fake','audio/wav')}).json()
        assert body['tts_error'] == 'TTS_UNAVAILABLE' and body['tts_provider'] == 'piper'
        assert body['assistant_text'] and body['tool_results'][0]['success']
        assert not body['audio_available']
        assert client.post('/api/v1/assistant/message',json={'message':'Покажи устройства'}).status_code == 200
