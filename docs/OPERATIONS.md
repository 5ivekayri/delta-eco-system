# Эксплуатация, резервные копии и обновление

Команды ниже выполняются из корня репозитория для обычного CPU Compose.
Для дополнительных профилей сохраняйте тот же набор `-f`, что использован при запуске.

## Что хранится

| Данные | Место | Как сохранять |
|---|---|---|
| История, устройства, пространства, IoT, Activity | БД `delta_core` | PostgreSQL dump |
| Задачи | Отдельная БД `delta_tasks` | PostgreSQL dump |
| Whisper / Piper / Qwen | Именованные тома моделей либо bind Qwen | Сохранить или повторить provision |
| Ключи, пароли, конфигурация | `.env` | Отдельная защищённая копия |
| Настройки голоса | localStorage браузера | Не входят в серверный backup |
| Токен браузера | sessionStorage | Ввести заново |
| UID Agent | `~/.delta-agent/device_uid` на устройстве | Сохранить на устройстве |

## Backup

Чтобы получить согласованный снимок двух независимых БД, остановите запись.
Не запускайте параллельно другие клиенты, пишущие напрямую в Tasks.

```sh
umask 077
mkdir -p backups
backup_dir="backups/$(date +%Y%m%d-%H%M%S)"
mkdir "$backup_dir"
docker compose stop delta-control-center delta-core delta-tasks
docker compose exec -T postgres pg_dump -U postgres -Fc delta_core > "$backup_dir/core.dump"
docker compose exec -T postgres pg_dump -U postgres -Fc delta_tasks > "$backup_dir/tasks.dump"
docker compose up -d
```

Проверьте exit code каждой команды; при ошибке dump не считайте backup успешным.
Скопируйте `.env` отдельно в защищённое хранилище. Запишите `git rev-parse HEAD`,
использованные Compose-профили и версию моделей рядом с backup. Храните копию вне
сервера. Архивы содержат личные данные. Не коммитьте их.

## Восстановление

Сначала потренируйтесь на отдельном сервере/проекте Compose. Используйте версию кода
на момент backup и соответствующую `.env`. Запустите `docker compose up -d postgres`;
дождитесь healthy. На **пустых** базах, созданных init-скриптом:

```sh
docker compose exec -T postgres pg_restore -U postgres --exit-on-error -d delta_core < /SAFE/PATH/core.dump
docker compose exec -T postgres pg_restore -U postgres --exit-on-error -d delta_tasks < /SAFE/PATH/tasks.dump
docker compose up --build -d
```

Не восстанавливайте поверх заполненной БД: остановитесь и подготовьте отдельное
пустое окружение. Дамп сохраняет Alembic revision; при запуске применятся следующие
миграции. Проверьте историю, задачи, связи, повторное подключение Agent и голоса.
Модели восстановите в тома или повторите provision из руководства установки.

## Обновление и откат

1. Запишите текущий commit и сделайте проверенный backup обеих БД и `.env`.
2. Проверьте `git status --short`: локальные изменения разберите до pull.
3. Выполните `git pull --ff-only`, сравните `.env.example` со своими настройками.
4. Выполните `docker compose up --build -d`. Alembic запускается перед backend.
5. Выполните [приёмку](RELEASE_ACCEPTANCE.md), проверьте логи и модели.

Откат кода не откатывает схему БД. При несовместимой миграции восстановите backup
в отдельное окружение с предыдущей версией кода и только после проверки переключайте
доступ. Не выполняйте автоматический destructive downgrade на рабочей базе.
Изменение DB-пароля в `.env` не меняет пользователя в существующем PostgreSQL volume:
ротация требует согласованного изменения роли и конфигурации, а не удаления volume.

## Диагностика

| Симптом | Проверка / действие |
|---|---|
| Invalid development token / 401 | Токен Settings должен совпадать с `DELTA_TOKEN`; после изменения окружения пересоздайте сервисы через `up -d` |
| Порт занят | Измените `DELTA_UI_PORT`; Core 8000 фиксирован в Compose, его конфликт решается отдельным override |
| Нет микрофона | HTTPS либо localhost, разрешение браузера, устройство ввода |
| Голос не готов | Provision моделей, restart Core, каталог голосов в настройках |
| Медленный Qwen | `docker stats`, нагрузка, тайм-аут; сравните Piper, затем измерьте GPU |
| OpenRouter error | Ключ, доступность выбранной модели и tool calling; локальные команды остаются независимы от LLM |
| Контекст потерян | Проверьте историю Core, окно 12 взаимодействий, неоднозначность; это один общий диалог |
| Agent offline | URL, токен, WebSocket proxy, запущенный пользовательский процесс Agent |
| DB unhealthy | Логи PostgreSQL, свободный диск, соответствие паролей существующему volume |

`docker compose ps`, `docker compose logs --tail=100 SERVICE`, `docker stats --no-stream`
помогают локализовать проблему. Перед передачей логов уберите ключи и личные данные.
Не публикуйте вывод `docker compose config`: в нём могут быть раскрыты значения `.env`.
