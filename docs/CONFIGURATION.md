# Конфигурация установки

Источники истины: [шаблон окружения](../.env.example), [Compose](../docker-compose.yml),
[backend Settings](../shared/contracts/delta_contracts/config.py).
Таблица описывает именно Docker Compose. При прямом запуске Python передайте
переменные процессу; `.env` не является универсальным менеджером окружения.

| Переменные | Назначение / default Compose |
|---|---|
| `DELTA_TOKEN` | Обязательный общий секрет UI, API, Tasks и Agent; минимум 16 символов |
| `POSTGRES_PASSWORD` | Пароль администратора PostgreSQL, только инициализация |
| `CORE_DB_PASSWORD`, `TASKS_DB_PASSWORD` | Раздельные роли/БД; используйте независимые hex-пароли |
| `DELTA_UI_PORT` | Порт UI на loopback, 8080 |
| `LLM_PROVIDER` | `mock` по умолчанию; `openrouter` для реального fallback |
| `OPENROUTER_API_KEY` | Ключ только на backend |
| `OPENROUTER_MODEL` | Резервная модель для обеих ролей |
| `DELTA_ROUTER_MODEL` | Быстрый tool-capable router; пусто → резервная модель |
| `DELTA_ASSISTANT_MODEL` | Ответы/рассуждение; пусто → резервная модель |
| `DELTA_ROUTER_MAX_TOKENS` | Бюджет router, 512 |
| `DELTA_LOCAL_INTENT_THRESHOLD` | Порог локального маршрута, 0.9 |
| `STT_PROVIDER` | `whisper`; `mock` только для тестов |
| `WHISPER_MODEL`, `WHISPER_LANGUAGE` | `small`, `ru`; не менять default без benchmark |
| `VOICE_MAX_SECONDS` | Максимум записи, 60 секунд |
| `MOCK_STT_TRANSCRIPT` | Только при явном mock STT |
| `TTS_PROVIDER` | `piper`; также `qwen`, `disabled`, `mock` |
| `PIPER_MODEL` | Пусто → `/models/piper/ru_RU-irina-medium.onnx` |
| `TTS_MAX_CHARS`, `TTS_MAX_SECONDS`, `TTS_TIMEOUT_SECONDS` | 1500 символов, 60 секунд аудио, 10 секунд ожидания Piper |
| `INSTALL_NEURAL` | Build argument, `false`; `true` включает тяжёлые зависимости Qwen |
| `QWEN_MODEL_VOLUME` | `qwen-models` либо абсолютный каталог на сервере |
| `QWEN_TTS_DEVICE`, `QWEN_TTS_SPEAKER` | `cpu`, `serena`; CUDA требует отдельного образа/override |
| `QWEN_TTS_THREADS` | CPU-потоки, 4 |
| `QWEN_TTS_TIMEOUT_SECONDS` | Ответ ждёт Qwen 20 секунд, затем Piper |
| `QWEN_TTS_PREVIEW_TIMEOUT_SECONDS` | Пример выбранного голоса ждёт до 120 секунд без подмены |
| `SERVICE_CONFIGS` | Необязательный JSON списка сервисов; default `null`, Tasks определяется штатно |

Compose сам задаёт `DATABASE_URL` отдельно каждому backend, `TASKS_URL`, пути
`WHISPER_CACHE_DIR=/models/whisper`, `QWEN_TTS_MODEL=/models/qwen` и имя Tasks.
Не направляйте Core в базу Tasks. Наличие произвольной переменной в `.env` не
означает, что Compose передаст её контейнеру: проверяйте секцию `environment`.

После изменения runtime-переменных: `docker compose up -d` (пересоздание).
Один `restart` не перечитывает окружение контейнера. После изменения build arguments:
`docker compose up --build -d`. После provision модели достаточно restart Core.
Выбор голоса/автоотправки хранится в браузере на странице «Настройки ассистента»;
он не меняет серверную конфигурацию и не устанавливает модели.
