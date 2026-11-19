# Развёртывание Delta на Linux

**Аккаунты:** перед первым пользовательским входом примените миграции и создайте
администратора по [ACCOUNTS.md](ACCOUNTS.md). В текущем интерфейсе используется
логин/пароль; упоминания development token ниже относятся к внутренним сервисам
и старым CLI-сценариям, не к пользовательскому входу.

Руководство соответствует Compose в репозитории на 2026-10-17. Целевая конфигурация:
Linux x86_64, Docker Engine с Compose v2, Git; Python/Node на сервере для Docker-запуска
не нужны. CPU-профиль проверялся в Linux-контейнерах на macOS, отдельная приёмка
на физическом Linux-сервере и NVIDIA GPU ещё требуется. Это персональная установка
с общим токеном и общей историей, не многопользовательский SaaS.

## 1. Подготовка

Установите Docker Engine и плагин Compose средствами своей ОС. Проверьте:

```sh
docker version
docker compose version
git --version
```

Для CUDA-профиля нужен Compose с поддержкой `gpus`, NVIDIA-драйвер и NVIDIA
Container Toolkit. Начните с CPU/Piper. Объём RAM/VRAM не зафиксирован как проверенный
минимум: измерьте `docker stats` на целевой машине. Оставьте место под образы,
PostgreSQL, резервные копии и модели; одни веса Qwen занимают около 2,5 GB.

```sh
git clone https://github.com/5ivekayri/delta-eco-system.git
cd delta-eco-system
cp .env.example .env
chmod 600 .env
```

Заполните четыре независимых секрета: `DELTA_TOKEN`, `POSTGRES_PASSWORD`,
`CORE_DB_PASSWORD`, `TASKS_DB_PASSWORD`. Для каждого сгенерируйте новое значение:

```sh
openssl rand -hex 24
```

Оставьте `LLM_PROVIDER=mock` для первого запуска либо задайте `LLM_PROVIDER=openrouter`,
`OPENROUTER_API_KEY`, `DELTA_ROUTER_MODEL` и `DELTA_ASSISTANT_MODEL` с доступными вашему
аккаунту моделями, поддерживающими инструменты. `OPENROUTER_MODEL` — запасное значение
для обоих ролей. Ключ вводится только в `.env`, а токен Delta — в Settings браузера.
Полный справочник: [CONFIGURATION.md](CONFIGURATION.md).

## 2. Запуск и установка моделей

Все команды выполняются из корня репозитория:

```sh
docker compose up --build -d
docker compose ps
docker compose exec -T delta-core python -m delta_core.voice.provision
docker compose exec -T delta-core python -m delta_core.voice.provision_tts
docker compose restart delta-core
```

Первый запуск скачивает Docker/Python-зависимости, provision — голосовые модели.
Whisper и Piper используют постоянные тома. До provision текстовый режим доступен,
но голос может быть не готов. После загрузки модели Core может стартовать дольше
обычного: смотрите логи, а не запускайте несколько копий inference.

```sh
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8080/tasks-api/health
docker compose logs --tail=100 delta-core delta-tasks
```

Откройте `http://localhost:8080` на сервере либо используйте туннель ниже. В Settings
введите `DELTA_TOKEN`; в «Настройки ассистента» выберите голос. Проверьте команды
из [приёмочного сценария](RELEASE_ACCEPTANCE.md). Health проверяет сервис/БД,
но не доказывает готовность моделей или доступность OpenRouter.

## 3. Доступ с компьютера пользователя

По умолчанию порты привязаны к loopback сервера. С клиентского компьютера:

```sh
ssh -N -L 8080:127.0.0.1:8080 -L 8000:127.0.0.1:8000 USER@SERVER
```

Откройте `http://localhost:8080`. Если `DELTA_UI_PORT=8081`, замените серверный порт
в первом перенаправлении на 8081; локальный порт можно оставить 8080. Микрофон
в браузере требует secure context: localhost или HTTPS. Обычный HTTP по IP сервера
для голосового интерфейса не подходит.

Для постоянного HTTPS-доступа поставьте reverse proxy на сервере перед
`127.0.0.1:8080`, с TLS-сертификатом для вашего домена. Проксируйте все пути без
переписывания, разрешите WebSocket Upgrade, тело до 25 MB, ожидание ответа не менее
180 секунд. Встроенный gateway сам направляет `/core/` и `/tasks-api/` к сервисам.
Agent через этот gateway использует `wss://YOUR_DOMAIN/core/ws/agents`.
PostgreSQL и Tasks наружу не публикуются. Ограничьте доступ доверенной сетью/VPN:
общий development token не заменяет индивидуальные аккаунты и права доступа.

## 4. Реалистичные серверные голоса

Для Qwen выполните [NEURAL_VOICE.md](NEURAL_VOICE.md): там точные команды CPU/CUDA,
provision, версия весов, тайм-ауты и измерения. Piper установите в любом случае:
он нужен как быстрый резерв. На проверенном CPU Qwen генерирует короткую фразу
десятки секунд; не обещаем мгновенную речь до замера на целевом сервере.
При использовании CUDA ко всем Compose-командам добавляйте
`-f docker-compose.yml -f docker/compose.neural-gpu.yml`, включая обновление.

## 5. Host Agent

Для подключения пользовательских Mac/Windows/Linux теперь доступен отдельный
[настольный Delta Agent](DESKTOP_AGENT.md) с окном настройки и треем. Его ставят
на каждый управляемый компьютер; Agent на Linux-сервере не регистрирует Mac.
Готовый клиент подключается к адресу gateway и не требует установки Docker/Python.
CLI ниже остаётся доступен для разработки и ручного запуска.

Agent запускается на компьютере, которым нужно управлять, в пользовательской
графической сессии. Headless-сервер не заменяет Agent на рабочем Mac/Windows/Linux.
На машине Agent установите Python 3.12+, uv и зависимости репозитория (`uv sync`).
Передайте общий `DELTA_TOKEN` через окружение, затем:

```sh
uv run python -m delta_agent.main --name "Linux workstation" \
  --url ws://127.0.0.1:8000/ws/agents --allow-root /home/USER/projects
```

Этот URL подходит для SSH-туннеля; для TLS используйте адрес из раздела 3.
Каталог должен существовать на машине Agent. Возможности и allowlist:
[DEVICE_PROTOCOL.md](DEVICE_PROTOCOL.md), [SECURITY.md](SECURITY.md).

## 6. Остановка, перезагрузка сервера и обслуживание

`docker compose stop` останавливает процессы, `docker compose up -d` запускает их.
`docker compose down` сохраняет данные; **не добавляйте `-v`**, если данные нужны.
В текущем Compose нет restart policy: для автоматического запуска после reboot
можно создать локальный override `docker/compose.local.yml`:

```yaml
services:
  postgres:
    restart: unless-stopped
  delta-core:
    restart: unless-stopped
  delta-tasks:
    restart: unless-stopped
  delta-control-center:
    restart: unless-stopped
```

Используйте его явно: `docker compose -f docker-compose.yml -f docker/compose.local.yml up -d`.
Включите автозапуск Docker средствами вашей ОС. После reboot проверьте health и
готовность голосов. Пример override не является уже установленным systemd-сервисом.
Обновление, восстановление и диагностика: [OPERATIONS.md](OPERATIONS.md).

### Desktop Assistant UI

The desktop client uses the existing gateway `/core` for the scoped routes
`GET /api/v1/desktop/devices` and `POST /api/v1/desktop/message`. No additional
port, database or proxy is required. Update Core before installing the new client;
with accounts enabled these routes require a valid admin Agent session.
The local macOS client remains separate from the Linux server Agent.

Desktop approval clients require updated Core and shared contracts before client
installation (Registration.approval_timeout / CommandMessage.expires_at). No schema
migration or extra port is needed. Core grants up to 60 seconds of approval time
in addition to the usual action timeout. Keep client/server clocks synchronized.
The server's noninteractive CLI Agent retains its existing explicit permissions;
the desktop client's selected confirmation mode applies to that desktop only.
