# Δ Delta Digital Ecosystem

Локально-ориентированная персональная AI-экосистема. Техническое задание: [prompt.rtf](prompt.rtf), текстовая копия: [docs/REQUIREMENTS.txt](docs/REQUIREMENTS.txt).

**Статус:** 10 фаз локальной разработки завершены; доступны задачи, устройства, рабочие пространства, текстовый Assistant и голосовой ввод через локальный Whisper. По умолчанию LLM — mock; цепочка Whisper → OpenRouter → Tool проверена на этой установке. Приёмка на всех целевых ОС ещё не завершена. Краткий прогресс: [PROGRESS.txt](PROGRESS.txt). Реализованные и оставшиеся этапы перечислены в [чеклисте](docs/IMPLEMENTATION_CHECKLIST.md).

## Структура

```text
apps/delta-core/            FastAPI Core
apps/delta-tasks/           отдельный FastAPI Task Service
apps/delta-agent/           host Agent и адаптеры Windows/macOS/Linux
apps/delta-control-center/  React + TypeScript + Vite
shared/contracts/          общие контракты и инфраструктура
docker/                    образы и инициализация PostgreSQL
docs/                      требования, архитектура, ход реализации
tests/                     backend tests
```

## Docker Compose

Требуются Docker Engine/Desktop и Compose v2. Скопируйте `.env.example` в `.env`. Заполните `DELTA_TOKEN`, `POSTGRES_PASSWORD`, `CORE_DB_PASSWORD`, `TASKS_DB_PASSWORD` независимыми случайными hex-строками (например, `python3 -c 'import secrets; print(secrets.token_hex(24))'`). Минимальная длина токена — 16 символов. Hex-пароли не требуют URL-экранирования в строках подключения.

```sh
docker compose up --build -d
docker compose ps
```

- Control Center: http://localhost:8080
- Core health: http://localhost:8000/health
- Tasks health через gateway: http://localhost:8080/tasks-api/health
- API docs: http://localhost:8000/docs

Введите `DELTA_TOKEN` в Settings; он хранится только в текущей browser session. PostgreSQL не публикует порт на хост. Core и Tasks используют отдельные базы/пользователей; Tasks доступен через gateway и внутреннюю сеть Compose.

Инициализация пользователей БД выполняется только при первом запуске пустого volume. Последующее изменение пароля в `.env` не меняет пароль внутри существующей БД. Для остановки без удаления данных: `docker compose down`.

Локальная установка на этом компьютере: [LOCAL_SETUP.md](LOCAL_SETUP.md).

## Локальная разработка

Python 3.12+, uv, Node.js 22. Для полноценной работы нужен PostgreSQL. SQLite используется только в изолированных тестах базовой инфраструктуры.

```sh
uv sync --extra test
uv run pytest
uv build
cd apps/delta-control-center
npm ci
npm test
npm run build
npm run dev
```

Для browser smoke test с запущенными Core и Vite: `npm run test:e2e`. По умолчанию используется установленный Google Chrome. Общая проверка сборок и unit tests: `sh scripts/check.sh` (uv и npm должны быть в PATH).

Backend factories: `uvicorn delta_core.main:create_app --factory --port 8000` и `uvicorn delta_tasks.main:create_app --factory --port 8001`. Каждому процессу передайте его `DATABASE_URL` и общий `DELTA_TOKEN` через окружение; Tasks дополнительно `SERVICE_NAME=delta-tasks`. Vite проксирует `/core` и `/tasks-api` на эти порты.

## Документация и спецификации

Начните с [развёртывания на Linux](docs/LINUX_DEPLOYMENT.md).

| Раздел | Спецификация |
|---|---|
| Установка Linux, сеть, HTTPS, Agent | [LINUX_DEPLOYMENT.md](docs/LINUX_DEPLOYMENT.md) |
| Переменные окружения и профили | [CONFIGURATION.md](docs/CONFIGURATION.md) |
| Backup, restore, обновление, диагностика | [OPERATIONS.md](docs/OPERATIONS.md) |
| Приёмка релиза | [RELEASE_ACCEPTANCE.md](docs/RELEASE_ACCEPTANCE.md) |
| Архитектура и границы MVP | [ARCHITECTURE.md](docs/ARCHITECTURE.md), [MVP_SCOPE.md](docs/MVP_SCOPE.md) |
| Контекст диалога и ссылки на задачи | [ASSISTANT_CONTEXT.md](docs/ASSISTANT_CONTEXT.md) |
| Голосовой pipeline и нейроголоса | [VOICE_PIPELINE.md](docs/VOICE_PIPELINE.md), [NEURAL_VOICE.md](docs/NEURAL_VOICE.md) |
| Маршрутизация и измерения | [LOCAL_INTENT_ROUTING.md](docs/LOCAL_INTENT_ROUTING.md), [VOICE_LATENCY.md](docs/VOICE_LATENCY.md) |
| Agent и интеграция сервисов | [DEVICE_PROTOCOL.md](docs/DEVICE_PROTOCOL.md), [SERVICE_INTEGRATION.md](docs/SERVICE_INTEGRATION.md) |
| Activity и IoT | [ACTIVITY_AND_SERVICES.md](docs/ACTIVITY_AND_SERVICES.md), [VIRTUAL_IOT.md](docs/VIRTUAL_IOT.md) |
| Безопасность | [SECURITY.md](docs/SECURITY.md) |
| Демо и прогресс | [DEMO_AND_ACCEPTANCE.md](docs/DEMO_AND_ACCEPTANCE.md), [IMPLEMENTATION_CHECKLIST.md](docs/IMPLEMENTATION_CHECKLIST.md) |
| Дальнейшие планы и правила | [FUTURE_ROADMAP.md](docs/FUTURE_ROADMAP.md), [AGENTS.md](AGENTS.md) |

При изменении поведения, API, конфигурации или развёртывания обновляйте связанную
спецификацию; новые документы добавляйте в эту таблицу. Отделяйте проверенные результаты
от запланированных функций и указывайте ограничения/способ проверки.

Task CRUD, Service Registry, рабочие пространства, голосовой Assistant с Piper и виртуальный IoT реализованы. Простые команды выполняются через Tool Registry без LLM. Запуск Windows/Linux пока проверяется через mocks.

## Host Agent

После установки Python-зависимостей задайте `DELTA_TOKEN` в окружении и запустите Agent **на хосте**:

```sh
uv run python -m delta_agent.main --name "My computer" --allow-root /absolute/path/to/projects
```

Windows: задайте `$env:DELTA_TOKEN` в PowerShell и передайте Windows-путь в `--allow-root`. Без разрешённых корней Agent отклоняет открытие каталогов. Повторяйте `--allow-root` для нескольких каталогов. Открытие произвольных файлов/исполняемых файлов не поддерживается. `vscode` и `browser` — разрешённые логические идентификаторы приложений.

По умолчанию Core WebSocket: `ws://127.0.0.1:8000/ws/agents`; изменить через `--url` или `DELTA_CORE_WS`. UID хранится в `~/.delta-agent/device_uid`. Остановка: Ctrl+C. Для другого компьютера потребуется явно настроенный сетевой доступ к Core; опубликованный Compose-порт по умолчанию доступен только локально.

Settings → token → Devices показывает реальный Agent. Device Details позволяет запросить system info и открыть example.com. Самопроверка без открытия приложений: `uv run python scripts/smoke_devices.py` (использует токен из `.env`, запускает Agent, запрашивает system info, проверяет heartbeat и завершает процесс).

## Workspaces

Создайте пространство, откройте его карточку и выберите устройство. Привязка хранит каталог **на этом устройстве**, приложения и сайты. Сохранение повторной привязки к тому же устройству обновляет её. Кнопка запуска доступна при наличии сохранённой привязки и online-устройства. Каталог должен входить в `--allow-root` Agent. Результат запуска показывает частичные ошибки; неуспешный запуск не выдаётся за успешный.

В Tasks можно выбрать пространство при создании/редактировании и фильтровать задачи по нему. Удаление пространства удаляет его привязки, но сохраняет задачи: связи между независимыми БД не каскадируют.

## Text Assistant

В Assistant доступны история последних 50 взаимодействий и выбор текущего компьютера. Settings → Developer mode раскрывает выбранные инструменты, аргументы, сервис, результат и время выполнения. История сохраняется в PostgreSQL и загружается после обновления страницы.

По умолчанию `LLM_PROVIDER=mock`: попробуйте «покажи устройства», «покажи сервисы», «покажи задачи» или «добавь задачу протестировать API». Для «открой Dark Weather» сначала создайте пространство с этим именем и привязкой к online-устройству. В mock fallback команда «открой диплом» выбирает пространство `Master Thesis`. Команды «Включи рабочий свет» и «Какая температура?» работают с виртуальным IoT.

Для OpenRouter задайте в локальном `.env` `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY` и `OPENROUTER_MODEL`, затем выполните `docker compose up -d delta-core`. API-ключ не вводится в браузер. HTTP-контракт и ошибки покрыты тестовым транспортом; реальный OpenRouter проверен вместе с голосовой командой списка устройств. При недоступности модели после выполнения действия Assistant сохраняет и показывает фактические результаты без повторного запуска действия.

## Голосовой ввод

В Assistant нажмите **Голос**, разрешите микрофон и произнесите команду. Нажмите **Остановить и отправить запись**: появится распознанный текст и ответ Assistant. **Отменить запись** удаляет запись без отправки. Лимит по умолчанию — 60 секунд.

Для первого запуска модели: `docker compose exec -T delta-core python -m delta_core.voice.provision` после сборки контейнеров, затем `docker compose restart delta-core`. Локальная модель Whisper small распознаёт русский язык; инструкция, ограничения и mock-режим описаны в [VOICE_PIPELINE.md](docs/VOICE_PIPELINE.md).

Ответы на голосовые команды озвучивает локальный Piper. Установите русский голос: `docker compose exec -T delta-core python -m delta_core.voice.provision_tts`, затем перезапустите Core. В браузере доступны остановка и повторное прослушивание; если автозапуск звука заблокирован, нажмите **Прослушать ответ**. При ошибке озвучивания остаются текст и выполненное действие. `TTS_PROVIDER=disabled` отключает озвучку; `mock` выдаёт только тестовую тишину.

## Задержка голосовых команд

Whisper загружается при старте Core. Прямые команды используют FAST PATH: маршрутизатор → инструмент → ответ по результату без второго LLM-запроса. Для анализа, составных запросов и нестандартных результатов сохраняется SMART PATH.

`DELTA_ROUTER_MODEL` задаёт модель для быстрых команд, `DELTA_ASSISTANT_MODEL` — для развёрнутых ответов. Если значение не задано, используется `OPENROUTER_MODEL`. Для замеров включите Settings → Developer mode **до** голосового запроса: появятся upload, STT, router, tool, response generation, TTS и total. Полный отчёт и воспроизводимый benchmark: [VOICE_LATENCY.md](docs/VOICE_LATENCY.md).

## Локальная маршрутизация команд

Простые русские команды сначала обрабатывает `LocalIntentRouter`. При уверенности не ниже `DELTA_LOCAL_INTENT_THRESHOLD=0.9` инструмент вызывается без OpenRouter; неоднозначные и сложные запросы используют LLM fallback. В Developer mode видны **Local route / LLM route**, время локальной маршрутизации и confidence.

Корпус из 40 команд, результаты маршрутизации и сравнение Whisper small/base: [LOCAL_INTENT_ROUTING.md](docs/LOCAL_INTENT_ROUTING.md). Модель по умолчанию остаётся `small`: `base` быстрее, но хуже распознаёт этот корпус. Инструменты виртуального IoT зарегистрированы в Core.

## Виртуальный IoT

В разделе **Virtual IoT** доступны рабочий свет, температура, освещённость и движение. Свет переключается вручную или командами Assistant, состояние сохраняется после перезапуска. Значения датчиков — фиксированная эмуляция: 23 °C, 30%, движение обнаружено. Физические устройства не подключены.

Попробуйте «Включи рабочий свет», «Выключи свет», «Какая температура?», «Покажи освещённость» и «Есть ли движение?». Эти команды используют локальный маршрут без LLM; голосовые ответы озвучивает Piper. API и архитектура адаптера: [VIRTUAL_IOT.md](docs/VIRTUAL_IOT.md).

## Overview, Activity и демо

Overview показывает реальные количества устройств, сервисов, рабочих пространств
и открытых задач. При ошибке отдельного API его данные помечаются как устаревшие.
Activity содержит фильтруемую историю, загрузку более ранних событий и обновление
каждые 5 секунд. Developer mode раскрывает детали. [Контракт и ограничения](docs/ACTIVITY_AND_SERVICES.md).

Для демо запустите `uv run python scripts/seed_demo.py`: он добавит недостающие
пространства и задачи, сохранив существующие данные. Привязки к реальным устройствам
настраиваются вручную. [Сценарии, команды проверки и границы приёмки](docs/DEMO_AND_ACCEPTANCE.md).

Если порт 8080 занят, задайте `DELTA_UI_PORT=8081` в `.env` и выполните
`docker compose up -d`. UI будет доступен на http://localhost:8081, Core — на
прежнем порту 8000. Для browser tests используйте `DELTA_UI_URL`, для seed и
voice smoke/benchmark — `--url http://127.0.0.1:8081`.

Проверка установки голосовых моделей в новые пустые тома:
`uv run python scripts/check_clean_install.py --voice-audio path/to/devices-command.wav`.
Файл должен содержать «Покажи устройства». Скрипт скачивает модели, проверяет
реальную голосовую цепочку и завершает только отдельное тестовое окружение.

### Выбор голоса и автоотправка

Откройте отдельную страницу **Настройки ассистента**: выберите серверный нейроголос
Qwen3-TTS или быстрый Piper Irina, прослушайте пример. В «Авто» нейросинтез при
перегрузке переключается на Piper. Это локальные модели на Linux-сервере, без
системных голосов macOS и без платного TTS API. [Установка нейроголосов](docs/NEURAL_VOICE.md).

Запись отправляется после паузы 1,8 секунды; паузу можно увеличить или оставить
ручную отправку. После записи сразу появляются анимация обработки и короткий сигнал.
Подробности: [голосовой интерфейс](docs/VOICE_PIPELINE.md).

### Контекст диалога

Assistant использует предыдущие сообщения и результаты действий в текстовом и
голосовом режиме. После создания задачи можно сказать «переименуй её в Отчёт»,
«поставь ей высокий приоритет» и «заверши её». Неоднозначные ссылки требуют
уточнения. [Границы контекста и проверенные сценарии](docs/ASSISTANT_CONTEXT.md).

Аккаунты и вход: [ACCOUNTS.md](docs/ACCOUNTS.md). На этой установке вход по логину/паролю; старый development token используется только между сервисами.

Создание воркспейсов голосом и текстом: [сценарии и контракт](docs/WORKSPACE_VOICE_CREATION.md).

[Управление приложениями и описание экрана](docs/DESKTOP_ACTIONS.md)

[OpenRouter/local LLM bridge](tools/llm-bridge/README.md).

[Документы, версии и ИИ](docs/DOCUMENTS.md)

[Workspace Studio: код, документы, хранение и превью](docs/WORKSPACE_STUDIO.md).
