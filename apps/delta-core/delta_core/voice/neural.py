"""Optional, server-local Qwen3 speech. No browser/OS or paid API dependency."""
import asyncio
import logging
from io import BytesIO
from pathlib import Path
from threading import Lock

from delta_contracts.errors import DeltaError
from .tts import TTSProvider, speech_text

SPEAKERS = {'serena': 'Serena', 'vivian': 'Vivian', 'ryan': 'Ryan', 'aiden': 'Aiden'}
VOICE_IDS = {'auto', 'piper', *SPEAKERS}


class NeuralTTSProvider(TTSProvider):
    name = 'qwen'

    def __init__(self, settings, fallback):
        self.settings = settings
        self.fallback = fallback
        self._model = None
        self._lock = Lock()
        self._startup_attempted = False
        self.startup_error = None

    async def startup(self):
        await self.fallback.startup()
        await asyncio.to_thread(self._load)

    def _load(self):
        with self._lock:
            if self._startup_attempted:
                return
            self._startup_attempted = True
            try:
                import torch
                from qwen_tts import Qwen3TTSModel
                path = Path(self.settings.qwen_tts_model)
                if not path.is_dir():
                    raise FileNotFoundError('Provision Qwen model first')
                torch.set_num_threads(self.settings.qwen_tts_threads)
                device = self.settings.qwen_tts_device
                self._model = Qwen3TTSModel.from_pretrained(
                    str(path), device_map=device,
                    dtype=torch.float32 if device == 'cpu' else torch.bfloat16,
                    attn_implementation='sdpa', local_files_only=True,
                )
            except Exception:
                logging.getLogger(__name__).exception('Failed to load local Qwen3-TTS')
                self._model = None
                self.startup_error = 'Qwen3-TTS не загружен. Проверьте установку модели и зависимости сервера.'

    def _generate(self, text, speaker):
        # Non-blocking admission also protects against timed-out threads still running.
        if not self._lock.acquire(blocking=False):
            raise DeltaError('TTS_BUSY', 'Нейросинтез занят.', 503)
        try:
            if self._model is None:
                raise DeltaError('TTS_UNAVAILABLE', self.startup_error or 'Модель не загружена.', 503)
            import numpy as np
            import soundfile as sf
            wavs, rate = self._model.generate_custom_voice(
                text=text, language='Russian', speaker=SPEAKERS[speaker],
                max_new_tokens=min(2048, self.settings.tts_max_seconds * 12),
            )
            samples = np.asarray(wavs[0])
            if not samples.size or samples.size > rate * self.settings.tts_max_seconds or not np.isfinite(samples).all():
                raise DeltaError('TTS_INVALID_AUDIO', 'Некорректный результат нейросинтеза.', 503)
            output = BytesIO()
            sf.write(output, samples, rate, format='WAV', subtype='PCM_16')
            return output.getvalue()
        finally:
            self._lock.release()

    async def synthesize_profile(self, text, voice='auto', strict=False):
        if voice not in VOICE_IDS:
            raise DeltaError('INVALID_VOICE', 'Неизвестный голос.', 422)
        if len(text) > self.settings.tts_max_chars:
            raise DeltaError('TTS_TOO_LONG', 'Ответ слишком длинный для озвучивания.', 422)
        text = speech_text(text)
        if not text:
            raise DeltaError('TTS_EMPTY_TEXT', 'Нет текста для озвучивания.', 422)
        if voice == 'piper':
            return await self.fallback.synthesize(text), {'tts_provider': 'piper', 'voice_id': 'piper'}
        speaker = self.settings.qwen_tts_speaker if voice == 'auto' else voice
        try:
            audio = await asyncio.wait_for(asyncio.to_thread(self._generate, text, speaker),
                                           self.settings.qwen_tts_preview_timeout_seconds if strict else self.settings.qwen_tts_timeout_seconds)
            return audio, {'tts_provider': 'qwen', 'voice_id': speaker}
        except asyncio.CancelledError:
            raise
        except Exception as error:
            code = error.code if isinstance(error, DeltaError) else 'TTS_TIMEOUT' if isinstance(error, TimeoutError) else 'TTS_UNAVAILABLE'
            # A preview must never silently substitute a different voice.
            if strict:
                raise DeltaError(code, 'Выбранный нейроголос недоступен или занят. Попробуйте позднее.', 503) from None
            audio = await self.fallback.synthesize(text)
            return audio, {'tts_provider': 'piper', 'voice_id': 'piper', 'tts_fallback_reason': code}

    async def synthesize(self, text):
        audio, _ = await self.synthesize_profile(text)
        return audio
