import asyncio
import threading
from unittest.mock import AsyncMock

import pytest
from delta_contracts.config import Settings
from delta_contracts.errors import DeltaError
from delta_core.voice.neural import NeuralTTSProvider


def provider(**kwargs):
    return NeuralTTSProvider(Settings(_env_file=None, delta_token="test-token-123456789", database_url="sqlite://", **kwargs), AsyncMock())


@pytest.mark.asyncio
async def test_success_selected_voice_without_fallback(monkeypatch):
    p = provider()
    calls = []
    def generate(text, speaker):
        calls.append((text, speaker))
        return b'wav'
    monkeypatch.setattr(p, '_generate', generate)
    audio, metadata = await p.synthesize_profile('**Готово**', 'ryan')
    assert audio == b'wav'
    assert metadata == {'tts_provider': 'qwen', 'voice_id': 'ryan'}
    assert calls == [('Готово', 'ryan')]
    p.fallback.synthesize.assert_not_called()


@pytest.mark.asyncio
async def test_missing_model_falls_back_but_preview_does_not():
    p = provider()
    p.fallback.synthesize.return_value = b'piper'
    audio, metadata = await p.synthesize_profile('Готово', 'serena')
    assert audio == b'piper'
    assert metadata['tts_fallback_reason'] == 'TTS_UNAVAILABLE'
    with pytest.raises(DeltaError):
        await p.synthesize_profile('Готово', 'serena', strict=True)
    p.fallback.synthesize.assert_awaited_once_with('Готово')


@pytest.mark.asyncio
async def test_busy_model_immediately_uses_fast_voice():
    p = provider()
    p._lock.acquire()
    try:
        _, metadata = await p.synthesize_profile('Готово')
        assert metadata['tts_fallback_reason'] == 'TTS_BUSY'
    finally:
        p._lock.release()


@pytest.mark.asyncio
async def test_timeout_does_not_queue_another_inference(monkeypatch):
    p = provider(qwen_tts_timeout_seconds=.1)
    released = threading.Event()
    def generate(text, speaker):
        if not p._lock.acquire(blocking=False):
            raise DeltaError('TTS_BUSY', 'busy', 503)
        try:
            released.wait(3)
            return b'wav'
        finally:
            p._lock.release()
    monkeypatch.setattr(p, '_generate', generate)
    try:
        _, first = await p.synthesize_profile('Один')
        _, second = await p.synthesize_profile('Два')
        assert first['tts_fallback_reason'] == 'TTS_TIMEOUT'
        assert second['tts_fallback_reason'] == 'TTS_BUSY'
    finally:
        released.set()
        await asyncio.sleep(.02)


@pytest.mark.asyncio
async def test_explicit_piper_and_invalid_voice_never_call_neural(monkeypatch):
    p = provider()
    generate = AsyncMock()
    monkeypatch.setattr(p, '_generate', generate)
    await p.synthesize_profile('Готово', 'piper')
    with pytest.raises(DeltaError):
        await p.synthesize_profile('Готово', '../../model')
    generate.assert_not_called()
    p.fallback.synthesize.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_loads_once_offline_at_startup(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock
    model = Mock()
    loader = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(set_num_threads=Mock(), float32='float32', bfloat16='bfloat16'))
    monkeypatch.setitem(sys.modules, 'qwen_tts', SimpleNamespace(Qwen3TTSModel=SimpleNamespace(from_pretrained=loader)))
    p = provider(qwen_tts_model=str(tmp_path))
    await p.startup()
    await p.startup()
    loader.assert_called_once()
    assert loader.call_args.kwargs['local_files_only'] is True
    assert p._model is model


@pytest.mark.asyncio
async def test_preview_has_separate_budget_from_interactive_reply(monkeypatch):
    import time
    p = provider(qwen_tts_timeout_seconds=.1, qwen_tts_preview_timeout_seconds=1)
    def generate(text, speaker):
        time.sleep(.15)
        return b'wav'
    monkeypatch.setattr(p, '_generate', generate)
    audio, metadata = await p.synthesize_profile('Привет', 'serena', strict=True)
    assert audio == b'wav' and metadata['tts_provider'] == 'qwen'
    p.fallback.synthesize.assert_not_called()
    _, metadata = await p.synthesize_profile('Привет', 'serena')
    assert metadata['tts_fallback_reason'] == 'TTS_TIMEOUT'
