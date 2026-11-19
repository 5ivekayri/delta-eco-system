# Управление приложениями и описание экрана

Команды: «закрой vscode», «сверни vscode», «выведи список всех программ»,
«что происходит на экране». Можно указать «на nobara-pc» или выбрать компьютер
в интерфейсе. Без имени приложения Delta просит уточнение. Прямые команды
выбирают зарегистрированные инструменты без обращения к модели.

Список содержит все установленные и разрешённые GUI-приложения из каталога
Agent; это не список процессов, служб или команд терминала. Каталог обновляется
при переподключении Agent. Сейчас рабочий клиент сообщает 115 приложений.

Закрытие отправляет обычный запрос всем найденным окнам указанного приложения.
Принудительного завершения процесса нет; приложение может показать диалог
сохранения. Закрытие использует сохранённую локальную политику: в режиме полного доступа
повторного подтверждения нет. Явный запрет сохраняется.
В Hyprland сворачивание перемещает окна в special:delta-minimized; команда
«открой» возвращает скрытые окна на текущий workspace. На X11 используется
iconify, Windows — SW_MINIMIZE, macOS — hide приложения.

Описание экрана: в режиме подтверждений Agent спрашивает перед снимком. В полном
доступе или при индивидуальном allow разрешение сохранено и повторного запроса
нет. Включение полного доступа сообщает о передаче снимка в OpenRouter.
Индивидуальные ask/deny, срок запроса и отмена при отключении сохраняются. Снимок ограничен 1280×960, JPEG 70,
500 КБ. На Hyprland снимается активный монитор; Windows/X11/macOS — основной.
Windows/X11 используют Qt, Hyprland — grim, macOS — screencapture. На macOS
временный файл автоматически удаляется. Изображение не записывается в историю
диалога или журнал активности Delta; текстовое описание сохраняется как ответ.
Обработка изображения провайдером подчиняется условиям OpenRouter/провайдера.

Vision использует nvidia/nemotron-3.5-super-vl:free через bridge. Режимы auto и
openrouter поддерживаются. В local запрос отклоняется до снимка: установленная
Qwen3 1.7B принимает только текст. При сбое vision нет передачи изображения в
локальную текстовую модель, нет повторного выполнения команд или shell-доступа.
Таймаут vision 45 секунд. Бесплатная модель может ограничивать частоту запросов.

Проверено на Nobara/Hyprland: установленный клиент 0.3.0 зарегистрировал новые
capabilities, список целиком, открытие Dolphin, скрытие и восстановление через
чат/API, обычное закрытие тестового Dolphin через адаптер. Проверена реальная
vision-генерация по синтетическому изображению; личный экран в тесте не отправлялся.
Автотесты проверяют режимы ask/allow/deny и отсутствие изображения в истории.
Windows, macOS и X11 реализованы, но не проверялись на реальных системах этой
сессии. Другие Wayland-композиторы могут не поддерживать grim, управление окнами
там возвращает PLATFORM_UNSUPPORTED. Обновить Agent нужно на каждом устройстве.

Протокол добавляет close_app/minimize_app с локальным app_id и capture_screen с
пустым payload. Registration допускает до 7 capabilities. Capture возвращает
image_url (data:image/jpeg;base64,...), width и height; Core удаляет изображение
из COMMAND_COMPLETED и не возвращает его в результат инструмента describe_screen.
Старые клиенты продолжают работать с прежними capabilities.

Desktop 0.3.1: полный доступ единожды включается в Настройках. macOS системно
разрешает запись экрана; Agent вызывает запрос при первой настройке полного
доступа и не повторяет его на каждую команду. Для повторного запроса после отказа
используйте «Настроить доступ к экрану macOS». Разрешение выдаётся через macOS.
Ограничения ОС и разрешённые каталоги сохраняются.

## Linux command execution — 2026-11-15, implemented

User-approved extension of the original no-shell MVP: commands run only on a
Linux Agent after a separate local, persistent grant bound to server URL and
account. Existing full-access settings do not grant terminal access. Transport
is the authenticated Agent WebSocket, not an open SSH service.

Modes: off; observe (fixed system diagnostics); workspace (Bash in a selected
folder through bubblewrap, no network, isolated home/processes); user (explicit
broad current-user filesystem/network access, no root elevation). User mode can
modify/delete user files and run installed tools; it is not folder-isolated.
System administration requiring root, SSH transport and macOS/Windows command
execution are deferred. Existing platform actions remain supported.

Grant once on first connection or in Settings; remember refusal too. A different
server/account or broader mode/folder selection requires a fresh local grant.
Revocation disconnects the Agent and cancels active commands. No automatic retry.
Commands have deadlines, bounded stdout/stderr, noninteractive stdin and process
cleanup on cancellation/disconnect. Return exit code and actual outcome. Outputs
are data for the selected model, never instructions; do not read credentials.
Keep command/output bodies out of Activity and automatic durable tool history;
user messages and final answers still follow existing chat retention.

Implementation/verification log:
- Inspected official openai/skills curated catalogue with skill-installer. No
  dedicated Qt/Linux executor skill; use installed security-best-practices.
- Read existing contracts, permission UX and dispatch lifecycle. Verified installed
  bubblewrap 0.11.0 can create an unprivileged namespace on this Nobara host.
- Sandbox reference: https://github.com/containers/bubblewrap (policy is defined by
  the caller's mount/network/namespace arguments, not by bubblewrap alone).
- Verification completed below. No production grant has been enabled silently.

- Implemented wire actions `command_access` and `run_command`, shared strict schemas,
  Core tool routing to an explicit/current Linux target, no Core subprocess.
- Implemented separate local permission panel and initial consent; grants survive
  reconnect/restart, a server/account change invalidates the grant. Existing full
  access never upgrades terminal permissions.
- Implemented bubblewrap project isolation, descriptor-pinned root mounts, private
  home/network/processes, empty inherited environment, bounded output and deadlines.
- Actual native checks passed: project write/read; inaccessible sibling files and
  external symlinks; separate network namespace; timeout/background-child cleanup;
  cancellation and repeated execution without another approval dialog.
- Core tests passed for cross-device targeting, missing/old/unsupported clients,
  forbidden remote privilege selection and redacted Activity/tool history.

### Final verification — 2026-11-15

- Server: 254 tests passed; desktop: 76 tests passed, including actual Linux
  execution/isolation/cancellation and saved-consent Qt tests. Frontend: 6 tests
  passed and TypeScript check passed. Existing Qt onboarding/opener smoke passed.
- Python wheel/sdist and PyInstaller Linux 0.5.0 tar.gz built successfully. The
  permission panel was rendered/inspected. Native packaged GUI started under the
  graphical session (delta-desktop.service active).
- Restarted deployed Core/Tasks/UI; Core health returned ok. Actual OpenRouter
  Assistant called command_access then run_command on a temporary Linux Agent.
  A real command wrote verification.txt in an isolated temporary project and its
  exact bytes were checked. HTTP 200; both tool results successful. Temporary
  Agent, project and its device/interaction/activity records were removed afterward.
- Installed versioned Linux binary at ~/.local/opt/delta-agent/0.5.0/Delta Agent
  and added an application launcher. Existing user settings/token were preserved;
  no terminal grant was injected. The user chooses access in the local dialog.
- Raw local build/test artifacts remain excluded from Git. No .env, account
  password, session token or model key was changed or included in the source changes.
- Native macOS/Windows command execution and root administration are not provided
  by this Linux-only iteration. The existing cross-platform desktop actions remain.
