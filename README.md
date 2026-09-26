# Δ Delta Digital Ecosystem

Локально-ориентированная персональная AI-экосистема. Техническое задание: [prompt.rtf](prompt.rtf), текстовая копия: [docs/REQUIREMENTS.txt](docs/REQUIREMENTS.txt).

**Статус:** фазы 1–5 проверены; доступны задачи, устройства, рабочие пространства и текстовый Assistant. По умолчанию используется mock-провайдер; реальный запрос OpenRouter пока не проверен. Это ещё не готовый MVP. Краткий прогресс: [PROGRESS.txt](PROGRESS.txt). Реализованные и оставшиеся этапы перечислены в [чеклисте](docs/IMPLEMENTATION_CHECKLIST.md).

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

## Документация

- [Архитектура](docs/ARCHITECTURE.md)
- [Границы MVP](docs/MVP_SCOPE.md)
- [Этапы и результаты проверок](docs/IMPLEMENTATION_CHECKLIST.md)
- [Правила разработки](AGENTS.md)

Task CRUD, Service Registry и рабочие пространства реализованы. Assistant в mock-режиме умеет создавать задачи через Tool Registry; голос и IoT остаются в следующих фазах. Запуск Windows/Linux пока проверяется через mocks.

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

По умолчанию `LLM_PROVIDER=mock`: попробуйте «покажи устройства», «покажи сервисы», «покажи задачи» или «добавь задачу протестировать API». Для «открой Dark Weather» сначала создайте пространство с этим именем и привязкой к online-устройству. Команда «открой диплом» выбирает пространство `Master Thesis`. Свет и температура станут доступны после фазы IoT.

Для OpenRouter задайте в локальном `.env` `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY` и `OPENROUTER_MODEL`, затем выполните `docker compose up -d delta-core`. API-ключ не вводится в браузер. Реальный запрос к OpenRouter пока не проверен; HTTP-контракт и ошибки покрыты тестовым транспортом. При недоступности модели после выполнения действия Assistant сохраняет и показывает фактические результаты без повторного запуска действия.
