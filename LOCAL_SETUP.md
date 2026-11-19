# Локальная установка на Nobara Linux

Дата проверки: 2026-10-23. Репозиторий развёрнут без Docker, с Python 3.12,
отдельным PostgreSQL и собранным интерфейсом через Vite preview.

- Интерфейс: http://192.168.0.28:8081 (локально http://localhost:8081) (8080 занят другим приложением).
- Core: http://127.0.0.1:8000, Tasks: http://127.0.0.1:8001.
- PostgreSQL: 127.0.0.1:55432, отдельные базы и роли delta_core / delta_tasks.
- Секреты: `.env` (права 600). В Settings интерфейса вставьте значение DELTA_TOKEN.
- Данные PostgreSQL: `.runtime/postgres`. Не удаляйте `.runtime`: там также модели,
  настройки Agent и локальный управляющий скрипт.

Из каталога проекта:

```sh
./start-local.sh
./stop-local.sh
journalctl --user -u delta-local -n 50
```

Запуск создаёт временную пользовательскую службу systemd `delta-local`.
Она работает независимо от окна Codex. Автозапуск после перезагрузки не включён:
после входа в систему выполните `./start-local.sh`.
Остановка сохраняет базы и модели. Перед резервным копированием `.runtime/postgres`
остановите приложение. Журналы сервисов: `.runtime/{core,tasks,ui,agent}.log`.

Agent отображается как Nobara workstation. Разрешённый корень для открытия
каталогов — родительская папка проекта (`/home/kayri/Документы/ChatGPT/delta`).

Whisper small и Piper Irina установлены локально. Qwen3-TTS не установлен.
LLM_PROVIDER=openrouter: ключ и токен Delta перенесены с Mac; модель nvidia/nemotron-3.5-lightning:free.
Сохранены Linux-настройки PostgreSQL и локальных Whisper/Piper. Реальные ответы OpenRouter проверены 2026-10-23 (см. ниже). После изменения `.env`
выполните остановку и повторный запуск.

Проверено: сборка Python-пакета и интерфейса, 6 frontend-тестов, 203 backend-теста, health обоих
API через gateway, регистрация Agent и текстовая команда списка устройств.
Голос проверен синтетической записью Piper → Whisper → Assistant → Piper;
Whisper распознал «Покажи устройства» как «Покажи его устройство», но команда
списка устройств выполнилась и ответ озвучился; микрофон пользователя отдельно не проверялся.

При npm ci отмечены 4 advisory (2 moderate, 2 high); автоматическое обновление
зависимостей не выполнялось. Это локальная установка для личного использования;
Vite preview не является production-сервером для публичного размещения.

## Доступ по локальной сети — 2026-10-23

Vite preview слушает 0.0.0.0:8081. Firewalld разрешает TCP 8081 для
192.168.0.0/24 (runtime и permanent). Core, Tasks и PostgreSQL остаются на loopback.
Проверено с другого компьютера: UI HTTP 200, /core/health и /tasks-api/health — ok.
Проверены авторизованные запросы списка устройств и задач через gateway.
После смены DELTA_TOKEN обновите токен в Settings браузера.
Для микрофона браузера нужен HTTPS или SSH-туннель на localhost; HTTP по IP
позволяет пользоваться текстовым интерфейсом, но не даёт secure context для микрофона.
Автозапуск после reboot не настроен; используйте ./start-local.sh после входа.

## Исправление качества ответов — 2026-10-23

Смешанный многоязычный ответ был непостоянным: повторный запрос до изменений
ответил нормально. Потеря RAG не подтверждается: RAG в этой версии не реализован.
Системный промпт присутствовал. Был настроен общий маршрут openrouter/free.
На сервере закреплена nvidia/nemotron-3.5-lightning:free для router и assistant,
уточнены роль Delta, язык текущего запроса и запрет копировать ошибки прошлых
ответов; temperature основного ответа 0.2, router остаётся 0.
История, задачи и базы не удалялись. Mac не изменялся.

Проверено на Linux: 203 backend-теста; TypeScript/Vite production build;
реальные ответы «Кто ты?» (7.89 с), «Чем ты можешь помочь в этой системе?»
(4.03 с), devices.list через приложение (0.03 с, Agent online).
Отдельный реальный вызов закреплённой LLM правильно выбрал devices.list.
Core health доступен с Mac по LAN. Старые ошибочные ответы остаются в истории.
Доступность/качество бесплатной внешней модели не гарантированы;
проверка других моделей дала 429/404, они не установлены.
Изменения исходников сделаны в этой Linux-копии, не закоммичены;
при обновлении репозитория их необходимо сохранить/перенести.

## Аккаунты — 2026-10-23

DELTA_ACCOUNTS_ENABLED=true. Вход в сайт и Desktop Agent — по логину и паролю.
Admin создан, пароль хранится у владельца на Mac вне Git. Новые аккаунты pending
не имеют административного доступа. Старые инструкции о токене в Settings больше
не применяются. CLI Agent сервера использует .runtime/server-agent-session (30 дней).
Подробнее: docs/ACCOUNTS.md.

## Проверка 2026-11-07

После перезагрузки обнаружен оставшийся `postmaster.pid`. Локальный управляющий
скрипт теперь проверяет PostgreSQL через `pg_ctl status`, а не по наличию файла.
Delta вновь запущена. `WHISPER_CPU_THREADS=4` выбран по замерам на этом CPU.
Лимиты ожидания LLM и результаты до/после: [VOICE_LATENCY.md](docs/VOICE_LATENCY.md).
Подробные времена текстовых и голосовых запросов видны в Developer mode и в
`.runtime/core.log` (события assistant_timing, voice_timing, llm_timing).

## Обновление macOS-клиента: запуск приложений

Core обновлён 2026-11-07: devices.open_app/list_apps, каталог Agent 0.2.0.
Готовый DMG из GitHub Actions run 42394731109 (macOS job successful):
http://192.168.0.28:8081/downloads/Delta-Agent-macOS.dmg
SHA-256: 54c7fd53669d88b8ae0325d92e95298df211867a3e734549976fafd260750009.
Копия лежит в соседнем delta-desktop/dist/macOS. Раздача из dist/downloads
локальная и исчезнет при пересборке frontend; повторно скопируйте DMG при необходимости.
На Mac завершите старый Agent и замените Delta Agent.app в Applications.
Сохранённые UID/настройки остаются в ~/.delta-agent-desktop. Реальное открытие Finder
пока не проверено: старый клиент честно возвращает требование обновления.

Локальный управляющий скрипт сохранён в Git: `scripts/manage_local.py`; start-local.sh
и stop-local.sh используют его. `.runtime` содержит только локальные данные и секреты.

## Linux command tools — 2026-11-15

Core updated/restarted with devices.command_access/run_command. Desktop 0.5.0
built, installed at ~/.local/opt/delta-agent/0.5.0/Delta Agent and opened via the
transient delta-desktop.service. Choose the terminal level locally once; it is
saved for the current server/account. Existing CLI Agent remains without terminal.
No SSH port/service or root grant was added. Live model/Agent file-write check
passed in a temporary isolated project; test records were cleaned up.

## Постоянный запуск — 2026-11-18

По запросу пользователя остановлен и отключён автозапуск
`pshenichflix-frontend.service` (порт 5173); порт проверен и свободен.
Остальные службы Пшеничфликса не изменялись.
Создана постоянная пользовательская служба
`~/.config/systemd/user/delta-local.service`, запускающая
`scripts/manage_local.py start` с Restart=on-failure и RestartSec=10.
Включены `systemctl --user enable --now delta-local.service` и
`loginctl enable-linger kayri`: служба работает независимо от открытого
терминала/приложения и настроена на запуск после перезагрузки без входа пользователя.
Фактическая перезагрузка в рамках проверки не выполнялась.
Проверено: unit enabled/active, Linger=yes; Core :8000/health и Tasks
:8001/health вернули HTTP 200/status ok, frontend :8081 вернул HTTP 200.
Адреса UI: http://localhost:8081/ и http://192.168.0.28:8081/.
Управление: `systemctl --user start|stop|restart delta-local.service`;
журнал: `journalctl --user -u delta-local.service`.

## Обновление ассистента и журнала — 2026-11-18

Добавлен фиксированный ответ на типовые вопросы о базовой модели/создателе Delta
и системная инструкция для остальных формулировок. В Assistant и Settings добавлен
переключатель «Журнал запросов LLM»: провайдер, модель, время, результат и переход
с OpenRouter на локальную LLM. Подробности и ограничения: docs/VOICE_LATENCY.md.
Frontend пересобран; dist/downloads сохранён и восстановлен. Постоянная служба
`delta-local.service` перезапущена, Core/Tasks/UI работают, порт 5173 свободен.
Проверка рабочего API выполнена через существующий разрешённый desktop endpoint
с текущей сессией Agent; учётные данные не менялись. Browser UI проверен отдельно
на временных фикстурах, поскольку браузер открывает экран входа. Тестовый HTTP-сервер
после проверки остановлен. Проверки: 273 + 9 Python tests, 7 UI tests, tsc/build.

## Word-читалка и мини-редактор — 2026-11-19

Раздел «Документы» заменён на интерфейс текстового процессора: светлый лист,
режимы чтения/редактирования, библиотека с поиском, создание DOCX, панель
форматирования, поиск по тексту, масштаб, Ctrl+S, история версий и боковой ИИ.
Ручные правки сохраняются отдельным rich API с проверкой ревизии и владельца;
неизменённые ZIP-части DOCX сохраняются. Спецификация: docs/DOCUMENTS.md.

Проверки: 278 backend tests и 14 frontend tests passed, tsc и production build
успешны, npm audit --omit=dev — 0 vulnerabilities. Новая функциональность проверена
в браузере на изолированном localhost-сервере с отдельной SQLite: чтение, частичное
форматирование 16 pt/bold, Enter, Ctrl+S, таблица/отмена, новый файл, повторное
открытие и поиск через границу форматирования. Скачанный DOCX отрендерен и просмотрен;
изображения, колонтитулы, стили и другие ZIP-части совпали с исходником.

Production frontend установлен атомарной заменой dist; downloads сохранены.
Предыдущая сборка: .runtime/ui-before-word-1795036696. delta-local.service
перезапущена и active; Core :8000, Tasks :8001, UI :8081 вернули HTTP 200.
Новые маршруты /documents/blank и /documents/{doc_id}/content есть в live OpenAPI.
Порт 5173 остаётся свободным. Тестовый сервер :8817 остановлен после проверки;
учётные записи и пользовательские документы рабочего сервиса не изменялись.
