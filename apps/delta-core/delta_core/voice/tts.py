"""Local speech synthesis. Models load at startup; requests never download assets."""
from abc import ABC, abstractmethod
import asyncio
from html import unescape
from io import BytesIO
from pathlib import Path
import re
from threading import Lock
import wave

from delta_contracts.errors import DeltaError


def speech_text(text: str) -> str:
    """Read prose rather than Markdown markers, URLs or code fences."""
    text = re.sub(r'```.*?(?:```|$)', ' Код приведён в текстовом ответе. ', text, flags=re.S)
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'(?m)^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)', '', text)
    text = re.sub(r'[*_`~|\[\]]', '', unescape(text))
    return ' '.join(text.split()).strip()


class TTSProvider(ABC):
    name: str

    async def startup(self):
        pass

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Return PCM WAV bytes or raise DeltaError; never execute assistant actions."""


class MockTTSProvider(TTSProvider):
    """Explicit test fixture: valid silent WAV, never impersonates spoken synthesis."""
    name = 'mock'

    async def synthesize(self, text: str) -> bytes:
        output = BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b'\0\0' * 4410)
        return output.getvalue()


class PiperTTSProvider(TTSProvider):
    name = 'piper'

    def __init__(self, model_path: str, max_chars: int = 1500, max_seconds: int = 60):
        self.model_path = model_path
        self.max_chars = max_chars
        self.max_seconds = max_seconds
        self._voice = None
        self._lock = Lock()
        self._startup_attempted = False
        self.startup_error = None

    async def startup(self):
        await asyncio.to_thread(self._load)

    def _load(self):
        with self._lock:
            if self._startup_attempted:
                return
            self._startup_attempted = True
            try:
                path = Path(self.model_path)
                if not self.model_path or not path.is_file() or not Path(str(path) + '.json').is_file():
                    raise FileNotFoundError('Piper model/config missing')
                from piper import PiperVoice
                self._voice = PiperVoice.load(str(path), use_cuda=False)
                # Russian eSpeak voices need no network resources during inference.
                if self._voice.config.espeak_voice != 'ru':
                    self._voice = None
                    raise ValueError('Configure a Russian Piper voice')
            except Exception:
                self._voice = None
                self.startup_error = 'Озвучивание недоступно. Установите русскую модель Piper и перезапустите Core.'

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self._synthesize, text)

    def _synthesize(self, text: str) -> bytes:
        if not self._lock.acquire(blocking=False):
            raise DeltaError('TTS_BUSY', 'Озвучивание занято; текстовый ответ сохранён.', 503)
        try:
            if self._voice is None:
                raise DeltaError('TTS_UNAVAILABLE', self.startup_error or 'Piper не инициализирован.', 503)
            if len(text) > self.max_chars:
                raise DeltaError('TTS_TOO_LONG', 'Ответ слишком длинный для озвучивания; прочитайте полный текст.', 422)
            text = speech_text(text)
            if not text:
                raise DeltaError('TTS_EMPTY_TEXT', 'В ответе нет текста для озвучивания.', 422)
            # Bound per-inference text and total returned audio, not just input bytes.
            parts = []
            while len(text) > 250:
                split = text.rfind(' ', 0, 251)
                split = split if split > 0 else 250
                parts.append(text[:split])
                text = text[split:].lstrip()
            parts.append(text)
            output = BytesIO()
            samples = 0
            rate = self._voice.config.sample_rate
            with wave.open(output, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                for part in parts:
                    for chunk in self._voice.synthesize(part):
                        data = chunk.audio_int16_bytes
                        if chunk.sample_rate != rate or chunk.sample_width != 2 or chunk.sample_channels != 1:
                            raise ValueError('Unsupported Piper audio format')
                        samples += len(data) // 2
                        if samples > rate * self.max_seconds:
                            raise DeltaError('TTS_TOO_LONG', 'Озвучивание превышает лимит; прочитайте полный текст.', 422)
                        wav.writeframes(data)
            if not samples:
                raise DeltaError('TTS_UNAVAILABLE', 'Не удалось получить звук; текстовый ответ сохранён.', 503)
            return output.getvalue()
        except DeltaError:
            raise
        except Exception:
            raise DeltaError('TTS_UNAVAILABLE', 'Не удалось озвучить ответ; текст сохранён.', 503)
        finally:
            self._lock.release()
