import base64
import asyncio
import json
import logging
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from delta_contracts.errors import DeltaError
from .telemetry import VoiceTimings
from .neural import NeuralTTSProvider, SPEAKERS

VoiceId = Literal["auto", "piper", "serena", "vivian", "ryan", "aiden"]

async def synthesize(request, text, voice_id="auto", strict=False):
    tts = request.app.state.tts
    settings = request.app.state.settings
    if isinstance(tts, NeuralTTSProvider):
        return await asyncio.wait_for(tts.synthesize_profile(text, voice_id, strict),
                                     (settings.qwen_tts_preview_timeout_seconds if strict else settings.qwen_tts_timeout_seconds) + settings.tts_timeout_seconds)
    if strict and voice_id not in {"auto", "piper"}:
        raise DeltaError("TTS_UNAVAILABLE", "Нейроголос не установлен на сервере.", 503)
    output = await asyncio.wait_for(tts.synthesize(text), settings.tts_timeout_seconds)
    return output, {"tts_provider": settings.tts_provider, "voice_id": "piper",
                    **({"tts_fallback_reason": "TTS_UNAVAILABLE"} if voice_id in SPEAKERS else {})}


router = APIRouter(prefix='/api/v1/assistant')
AUDIO_TYPES = {'audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav', 'audio/x-wav', 'audio/mpeg'}


@router.get('/voice/config')
def voice_config(request: Request):
    settings = request.app.state.settings
    return {'provider': settings.stt_provider, 'max_seconds': settings.voice_max_seconds,
            'max_bytes': settings.voice_max_bytes, 'tts_provider': settings.tts_provider,
            'neural_ready': isinstance(request.app.state.tts, NeuralTTSProvider) and request.app.state.tts._model is not None,
            'voices': [{'id': 'piper', 'name': 'Irina · Piper', 'kind': 'fast'},
                       *[{'id': key, 'name': value + ' · Qwen3-TTS', 'kind': 'neural'} for key, value in SPEAKERS.items()]]}


@router.post('/voice')
async def voice(request: Request, background_tasks: BackgroundTasks, audio: UploadFile = File(...), device_id: UUID | None = Form(None), tts_mode: Literal['server','piper','system'] = Form('server'), voice_id: VoiceId = Form('auto')):
    settings = request.app.state.settings
    timings = getattr(request.state, 'voice_timings', None) or VoiceTimings()
    assistant = request.app.state.assistant
    target = str(device_id) if device_id else None
    events = []
    background_tasks.add_task(assistant.write_events, events)
    transcript = None
    try:
        try:
            if (audio.content_type or '').split(';', 1)[0].lower() not in AUDIO_TYPES:
                raise DeltaError('INVALID_AUDIO_TYPE', 'Поддерживается запись WebM, Ogg, MP4, WAV или MP3.', 415)
            data = await audio.read(settings.voice_max_bytes + 1)
        finally:
            await audio.close()
        if len(data) > settings.voice_max_bytes:
            raise DeltaError('AUDIO_TOO_LARGE', 'Аудиозапись слишком большая.', 413)
        if not data:
            raise DeltaError('EMPTY_AUDIO', 'Запись пустая. Повторите запись.', 422)
        events.append(('VOICE_REQUEST', 'Voice input received', {'device_id': target,
                       'details': {'bytes': len(data), 'provider': settings.stt_provider}}))
        try:
            with timings.measure('stt_ms'):
                transcript = (await request.app.state.stt.transcribe(data)).strip()
            if not transcript:
                raise DeltaError('EMPTY_TRANSCRIPT', 'Речь не распознана. Попробуйте говорить ближе к микрофону.', 422)
            if len(transcript) > 10000:
                raise DeltaError('TRANSCRIPT_TOO_LONG', 'Распознанный текст слишком длинный. Сократите запись.', 422)
        except DeltaError as error:
            events.append(('STT_FAILED', error.message, {'device_id':target, 'details':{'error_code':error.code}}))
            raise
        events.append(('STT_COMPLETED', transcript, {'device_id':target}))
        result = await assistant.message(transcript, target, timings=timings, background=background_tasks)
        result.update(transcript=transcript, stt_provider=settings.stt_provider, audio_available=False)
        # Text/history and completed actions survive synthesis failures. Never retry tools.
        tts = getattr(request.app.state, 'tts', None)
        result['tts_provider'] = settings.tts_provider
        result['tts_mode'] = tts_mode
        if tts_mode == 'system':
            timings.tts_status = 'client'
        if tts is not None and tts_mode != 'system':
            try:
                with timings.measure('tts_ms'):
                    output, metadata = await synthesize(request, result['assistant_text'], voice_id)
                    result.update(metadata)
                result.update(audio_available=True, audio_base64=base64.b64encode(output).decode('ascii'), audio_mime='audio/wav')
                timings.tts_status = 'ok'
            except Exception as error:
                timings.tts_status = 'unavailable'
                result['tts_error'] = error.code if isinstance(error, DeltaError) else 'TTS_TIMEOUT' if isinstance(error, TimeoutError) else 'TTS_UNAVAILABLE'
                result['tts_message'] = error.message if isinstance(error, DeltaError) else 'Не удалось озвучить ответ. Текст и результаты действий сохранены.'
                events.append(('TTS_FAILED', result['tts_message'], {'details':{'error_code':result['tts_error']}}))
        result['timings'] = timings.snapshot()
        return result
    except DeltaError as error:
        body = {'success':False, 'error_code':error.code, 'message':error.message, 'timings':timings.snapshot()}
        if transcript and len(transcript) <= 10000:
            body['transcript'] = transcript
        return JSONResponse(body, status_code=error.status, background=background_tasks)
    finally:
        logging.getLogger(__name__).info(json.dumps({'event':'voice_timing', 'request_id':getattr(request.state,'request_id',None), **timings.snapshot()}))


class SynthesisInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=10000)
    voice_id: VoiceId = "auto"
    preview: bool = False


@router.post('/voice/synthesize')
async def synthesize_only(body: SynthesisInput, request: Request):
    """Playback fallback only: never route an intent or execute an assistant tool."""
    tts = getattr(request.app.state, 'tts', None)
    if tts is None:
        raise DeltaError('TTS_UNAVAILABLE', 'Локальное озвучивание отключено. Текст ответа сохранён.', 503)
    try:
        output, metadata = await synthesize(request, body.text, body.voice_id, body.preview)
    except TimeoutError:
        raise DeltaError('TTS_TIMEOUT', 'Озвучивание не успело завершиться. Текст ответа сохранён.', 503) from None
    except DeltaError:
        raise
    except Exception:
        raise DeltaError('TTS_UNAVAILABLE', 'Озвучивание недоступно. Текст ответа сохранён.', 503) from None
    return {'audio_base64':base64.b64encode(output).decode('ascii'), 'audio_mime':'audio/wav',
            **metadata}
