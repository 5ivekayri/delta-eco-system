"""Local speech recognition; model downloads are an explicit setup operation."""
from abc import ABC, abstractmethod
import asyncio
from io import BytesIO
from threading import Lock

from delta_contracts.errors import DeltaError


class STTProvider(ABC):
    name: str

    async def startup(self):
        """Prepare reusable resources before serving requests."""

    @abstractmethod
    async def transcribe(self, audio: bytes) -> str:
        """Return recognized text, or raise a structured DeltaError."""


class MockSTTProvider(STTProvider):
    name = 'mock'

    def __init__(self, transcript: str):
        self.transcript = transcript

    async def transcribe(self, audio: bytes) -> str:
        return self.transcript


class WhisperSTTProvider(STTProvider):
    name = 'whisper'

    def __init__(self, model: str, cache_dir: str, max_seconds: int, language: str | None = "ru"):
        self.model_name = model
        self.cache_dir = cache_dir
        self.max_seconds = max_seconds
        self.language = language
        self._model = None
        self._lock = Lock()
        self._startup_attempted = False
        self.startup_error = None
        self.compute_type = None

    async def startup(self):
        await asyncio.to_thread(self._load_model)

    def _load_model(self):
        with self._lock:
            if self._startup_attempted:
                return
            self._startup_attempted = True
            try:
                import ctranslate2
                from faster_whisper import WhisperModel
                supported = ctranslate2.get_supported_compute_types('cpu')
                self.compute_type = 'int8' if 'int8' in supported else 'float32'
                self._model = WhisperModel(self.model_name, device='cpu', compute_type=self.compute_type,
                                           cpu_threads=2, download_root=self.cache_dir, local_files_only=True)
            except Exception:
                self.startup_error = 'Модель Whisper не готова. Установите модель и перезапустите Core; текстовый чат доступен.'

    async def transcribe(self, audio: bytes) -> str:
        return await asyncio.to_thread(self._transcribe, audio)

    def _decode(self, audio: bytes):
        try:
            import av
            import numpy as np
        except ImportError:
            raise DeltaError('STT_UNAVAILABLE', 'Whisper не установлен. Текстовый чат доступен.', 503)
        try:
            # Decode incrementally so compressed long uploads cannot expand without a bound.
            parts = []
            samples = 0
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            with av.open(BytesIO(audio)) as container:
                stream = next((s for s in container.streams if s.type == 'audio'), None)
                if stream is None:
                    raise ValueError('No audio stream')
                for frame in container.decode(stream):
                    for converted in resampler.resample(frame):
                        samples += converted.samples
                        if samples > self.max_seconds * 16000:
                            raise DeltaError('AUDIO_TOO_LONG', f'Запись должна быть не длиннее {self.max_seconds} секунд.', 413)
                        parts.append(converted.to_ndarray().flatten())
                for converted in resampler.resample(None):
                    samples += converted.samples
                    if samples > self.max_seconds * 16000:
                        raise DeltaError('AUDIO_TOO_LONG', f'Запись должна быть не длиннее {self.max_seconds} секунд.', 413)
                    parts.append(converted.to_ndarray().flatten())
            if not samples:
                raise ValueError('No samples')
            waveform = np.concatenate(parts).astype(np.float32) / 32768.0
        except DeltaError:
            raise
        except Exception:
            raise DeltaError('INVALID_AUDIO', 'Не удалось прочитать аудио. Запишите сообщение ещё раз.', 422)
        return waveform

    def _transcribe(self, audio: bytes) -> str:
        # Do not queue multiple expensive jobs on a CPU-only personal installation.
        if not self._lock.acquire(blocking=False):
            raise DeltaError('STT_BUSY', 'Распознавание уже выполняется. Попробуйте чуть позже.', 429)
        try:
            waveform = self._decode(audio)
            if self._model is None:
                raise DeltaError('STT_UNAVAILABLE', self.startup_error or 'Whisper не инициализирован; перезапустите Core.', 503)
            try:
                segments, _ = self._model.transcribe(waveform, language=self.language, beam_size=1,
                                                     vad_filter=True, word_timestamps=False,
                                                     condition_on_previous_text=False, temperature=0)
                return ' '.join(segment.text.strip() for segment in segments).strip()
            except Exception:
                raise DeltaError('STT_UNAVAILABLE', 'Whisper не смог распознать запись. Текстовый чат доступен.', 503)
        finally:
            self._lock.release()
