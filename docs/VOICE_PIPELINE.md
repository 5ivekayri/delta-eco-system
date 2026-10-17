# Voice pipeline

Voice input and local Piper output are implemented. No continuous listening or wake word.

## Use

Open http://localhost:8080, sign in through Settings with `DELTA_TOKEN`, and open Assistant. Click **Голос**, allow microphone access, speak, then click **Остановить и отправить запись**. Recognition and Assistant processing start immediately after stopping; results and the recognized transcript appear in the chat. **Отменить запись** discards audio before submission. Recording stops automatically at 60 seconds by default.

Only localhost or HTTPS can access the microphone. If permission is denied, allow the microphone in browser site settings or use text. Leaving Assistant stops microphone tracks. Leaving during a submitted request aborts the browser's wait, but an already running server action may still complete; consult history before retrying.

Whisper loads once at application startup and uses local CPU/int8 inference (float32 fallback when int8 is unsupported), beam size 1, VAD and no word timestamps. Audio remains within the local Core service; recognized text first goes to LocalIntentRouter. Confident supported commands execute locally without an LLM; fallback text is sent to the configured LLM (OpenRouter when selected). Audio is not retained by Delta. Multipart temporary uploads are closed after reading; decoded samples are bounded by the recording duration. The transcript is stored as `user_message` in Assistant history and as an STT activity event.

Common Russian commands can bypass OpenRouter entirely. Developer mode shows Local route / LLM route, local routing time and confidence. See [LOCAL_INTENT_ROUTING.md](LOCAL_INTENT_ROUTING.md) for supported phrases, threshold configuration, the 40-command benchmark and small/base STT results. Whisper small remains the default.

## Docker setup

Core includes the locked STT dependencies; Tasks does not install them. Model downloads are an explicit setup operation, never performed during a voice request:

```sh
docker compose up --build -d
docker compose exec -T delta-core python -m delta_core.voice.provision
docker compose restart delta-core
```

The second command downloads the configured multilingual model to the persistent `whisper-models` volume. The current default is `small` (Systran's CTranslate2 conversion of Whisper small). Switching models requires repeating provisioning and restarting Core. Inference uses `local_files_only=True`. A missing model returns `STT_UNAVAILABLE`; the server never silently substitutes a mock transcript.

Configuration in `.env`:

```dotenv
STT_PROVIDER=whisper
WHISPER_MODEL=small
WHISPER_LANGUAGE=ru
VOICE_MAX_SECONDS=60
```

For local Python development install `uv sync --extra test --extra stt`, provision with `uv run python -m delta_core.voice.provision`, and run Core with its database settings. `WHISPER_CACHE_DIR` defaults to `.runtime/whisper`; Compose sets it to `/models/whisper`. Optional packages/wheels depend on the host platform; the provided Linux Docker image is the verified environment on this Mac.

Provider implementation reference: [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Model metadata and license: [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small). The model is MIT-licensed; the installed cache occupies approximately 464 MiB (measured on this installation). Models are not committed to Git.

For deterministic tests only:

```dotenv
STT_PROVIDER=mock
MOCK_STT_TRANSCRIPT=покажи устройства
```

The UI visibly identifies mock mode. Mock ignores the audio contents and returns the configured phrase; it is never an automatic fallback. No speech recognition claim is made for mock mode.

## API and limits

- `GET /api/v1/assistant/voice/config`: authenticated provider name, duration and byte limits.
- `POST /api/v1/assistant/voice`: authenticated multipart `audio` file and optional UUID `device_id`. Accepted MIME types: WebM/Opus, Ogg/Opus, MP4, WAV and MP3. MIME type alone is not trusted: the real provider decodes and validates the audio.
- Default maximum: 10 MiB of audio, 60 seconds after decoding. A body limit of audio maximum + 64 KiB multipart overhead is enforced before form parsing, including requests without Content-Length.
- CPU recognition runs in a worker thread; only one Whisper recognition job runs at a time. Overlap returns `STT_BUSY`, without queuing multiple expensive jobs.
- Success returns `transcript`, `assistant_text`, `tool_calls`, `tool_results`, `stt_provider`, TTS metadata and optional WAV audio. A synthesis failure preserves the text and completed actions.
- If the LLM fails after transcription, an error response also includes `transcript`; the UI shows it and places it in the editable text field. Requests are not retried automatically.

Errors: `EMPTY_AUDIO`, `INVALID_AUDIO_TYPE`, `INVALID_AUDIO`, `AUDIO_TOO_LARGE`, `AUDIO_TOO_LONG`, `STT_BUSY`, `STT_UNAVAILABLE`, `EMPTY_TRANSCRIPT`, `TRANSCRIPT_TOO_LONG`. Every STT failure leaves text chat available and executes no Assistant tools.

Browser status labels reflect actual known stages: waiting for permission, recording, and combined recognition/processing. The synchronous voice endpoint does not report individual server stages, so the UI does not invent progress between inference and tool execution.

Text and completed tool results survive synthesis or playback failures. Replaying a spoken result never reruns the tool.

Latency instrumentation, FAST/SMART execution paths, separate model settings and measured results: [VOICE_LATENCY.md](VOICE_LATENCY.md).

## Local Piper output (phase 7)

Voice replies are synthesized locally using `PiperTTSProvider`. The Russian ONNX
voice and JSON configuration load once during startup; inference runs off the
async event loop. Model downloads never occur during a request. The provider
interface also supports an explicitly selected mock (short silent WAV) and
`TTS_PROVIDER=disabled`. Missing/broken models preserve text and completed tools;
there is no automatic substitution of mock audio.

Core installs the locked `voice` dependencies from `requirements-voice.lock`;
Tasks does not install speech dependencies. Piper models have a separate persistent
volume. To install the default Russian voice:

```sh
docker compose up --build -d
docker compose exec -T delta-core python -m delta_core.voice.provision_tts
docker compose restart delta-core
```

Use `--force` with the provision command to replace a damaged/partial model.
For local Python use `uv sync --extra test --extra voice` and configure a local
`PIPER_MODEL` path. The verified speech runtime is the Linux Core container.

```dotenv
TTS_PROVIDER=piper
# Compose defaults to this path when PIPER_MODEL is empty:
PIPER_MODEL=/models/piper/ru_RU-irina-medium.onnx
TTS_MAX_CHARS=1500
TTS_MAX_SECONDS=60
TTS_TIMEOUT_SECONDS=10
```

TTS reads plain prose rather than Markdown headings/formatting, links or code
blocks. The full original answer remains visible. An answer over the configured
character limit is left as text rather than silently cutting off the spoken
answer. Synthesis is chunked into bounded text segments and WAV duration is
bounded. Only one Piper job runs at a time; overlap returns `TTS_BUSY` as a speech
fallback, not a failed assistant action. A timeout ends the HTTP wait; the CPU
worker keeps its lock until inference finishes, preventing overlapping jobs.

Successful `/assistant/voice` replies include `audio_available=true`,
`audio_mime=audio/wav`, `audio_base64` and `tts_provider`. TTS failures return HTTP
200 with the already completed text/tool result, `audio_available=false`,
`tts_error` and `tts_message`. Error codes include `TTS_UNAVAILABLE`, `TTS_BUSY`,
`TTS_TOO_LONG`, `TTS_EMPTY_TEXT`, `TTS_TIMEOUT`. Existing `tts_ms` and total latency
include synthesis; playback duration is excluded from total response latency.
Text-only `/assistant/message` requests remain text-only.

The browser attempts to play a voice reply automatically. If browser autoplay
policy blocks playback, use **Прослушать ответ**. **Остановить** stops speech;
replay uses the same in-memory WAV and never calls the assistant/tools again.
Starting another recording, submitting text, or navigating away stops playback
and releases the object URL. Playback failures preserve the visible text. Audio
is not stored in PostgreSQL or server files; replay is available for the latest
voice response in the current page session. Reloaded history remains text-only.

Implementation reference: [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md).
The default voice is [ru_RU-irina-medium](https://huggingface.co/rhasspy/piper-voices/tree/main/ru/ru_RU/irina/medium),
22,050 Hz. Its [model card](https://huggingface.co/rhasspy/piper-voices/blob/main/ru/ru_RU/irina/medium/MODEL_CARD)
identifies RHVoice as the dataset source and lists the dataset license as unknown;
this is distinct from the repository's MIT metadata. Models remain outside Git.

### Verified latency and playback

On the installed Whisper small + Piper Irina pipeline, three local device-list
requests completed in 3.48 / 3.66 / 3.59 seconds with TTS taking 569 / 637 / 669 ms.
All three used zero LLM completions. Chrome MediaRecorder with synthetic Russian
microphone audio returned the spoken response in 3329 ms after recording stopped,
including 525 ms TTS. Native audio playback decoded a 5.77-second WAV; stop, replay
and navigation cleanup passed with only one voice request. Playback duration is
not part of the 3329 ms response latency. Physical microphone/speaker quality
still requires the user's listening check.

### Ошибки OpenRouter (2026-10-17)

HTTP 200 не гарантирует успешный ответ модели: OpenRouter может вернуть объект
`error` с кодом 503 при перегрузке upstream-провайдера. Адаптер проверяет его до
разбора `choices` и показывает отдельные сообщения для авторизации, баланса,
лимитов, перегрузки, таймаута и некорректного ответа. Сырые сообщения провайдера
не передаются в UI, чтобы не раскрывать служебные данные.

Для явных ошибок 500/502/503/504 выполняется максимум одна повторная попытка
инференса через 300 ms. Ключевые ошибки и 429 не повторяются автоматически.
Вызовы инструментов возвращаются только после успешного разбора всего ответа;
обрезанные ответы (`finish_reason=length`) отклоняются без выполнения команд.

В текущей локальной установке модели переключены с перегруженной
`nvidia/nemotron-3-ultra-550b-a55b:free` на `openrouter/free`. Этот бесплатный
маршрутизатор выбирает модель с поддержкой запрошенных возможностей; конкретная
модель может меняться. Это не гарантирует доступность или одинаковую задержку.
Документация: https://openrouter.ai/openrouter/free/apps

## Голоса, окончание речи и обратная связь — 2026-10-17

Настройки вынесены на отдельную страницу **Настройки ассистента**. В чате нет
выбора голоса и параметров записи. Предыдущая реализация с системными голосами
заменена серверным Qwen3-TTS; голоса ОС не нужны. См. [установку на Linux](NEURAL_VOICE.md).

- Qwen3-TTS CustomVoice 0.6B: Serena, Vivian, Ryan, Aiden; язык Russian.
- Piper Irina: быстрый режим и резерв при занятости/ошибке/тайм-ауте нейромодели.
- Модель загружается один раз при старте; запросы не скачивают веса.
- Выбор передаётся как `voice_id`; ответ содержит фактические `tts_provider`,
  `voice_id` и при замене `tts_fallback_reason`. `tts_ms` включает попытку нейросинтеза
  и резерв. Один inference одновременно; тайм-аут не разблокирует работающий поток.
- Прослушивание примера (`preview=true`) не заменяет выбранный голос резервом.
  Endpoint `/api/v1/assistant/voice/synthesize` не вызывает Assistant/tools.
- Предпочтения сохраняются в localStorage конкретного браузера.
- Старый `tts_mode=system` поддержан для совместимости API; новый клиент его не посылает.

Автоотправка использует локальную оценку энергии микрофона: минимум 250 ms
непрерывного сигнала выше порога, затем пауза по умолчанию 1,8 s (1,2/2,5 s).
Одиночные щелчки игнорируются; 10 s без речи отменяют запись без отправки.
Это энергетический детектор, а не семантическое определение окончания фразы;
в шумном помещении можно отключить автоотправку на странице настроек.

После записи сразу появляются анимация, текст «Секунду, обрабатываю» и локальный
звуковой сигнал. Запрос не ждёт окончания сигнала. Индикация не обещает успех действия
и не имитирует неизвестные серверные этапы; после 15 s сообщает об ожидании.
Поддержан reduced motion. Физическое качество микрофона/звучания оценивает пользователь.
