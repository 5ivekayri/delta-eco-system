"""Cross-platform Qt desktop client for the existing Agent protocol."""
import asyncio
import html
from concurrent.futures import Future, TimeoutError as FutureTimeout, InvalidStateError
from datetime import datetime
import socket
import time
import sys

from PySide6.QtCore import QObject, QLockFile, QThread, QTimer, Qt, Signal, Slot, QUrl, QPointF
from PySide6.QtGui import QAction, QPalette, QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap, QPen, QPolygonF
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
    QDialog, QStackedWidget, QTabWidget, QComboBox)

from .autostart import set_autostart
from .main import run_agent
from .account import login as account_login, logout as account_logout, desktop_request
from pydantic import SecretStr
from .platforms import get_platform
from .settings import DesktopSettings, config_directory, load_settings, save_settings


class DesktopOpener(QObject):
    """Dispatch native GUI opening on the UI thread, after Agent policy checks."""
    requested = Signal(object)

    def __init__(self):
        super().__init__()
        self.requested.connect(self.open_native)

    @Slot(object)
    def open_native(self, request):
        url, future = request
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(QDesktopServices.openUrl(url))
        except Exception:
            future.set_exception(RuntimeError('Native desktop opener failed'))

    def open_path(self, path):
        future = Future()
        self.requested.emit((QUrl.fromLocalFile(path), future))
        try:
            if not future.result(timeout=10):
                raise RuntimeError('Operating system rejected folder opening')
        except FutureTimeout:
            from subprocess import TimeoutExpired
            future.cancel()
            raise TimeoutExpired('native folder opener', 10) from None


COMMAND_LABELS = {
    'system_info': 'Сведения о компьютере',
    'open_url': 'Открытие ссылок',
    'open_path': 'Открытие папок',
    'open_app': 'Запуск приложений',
}


class ApprovalBroker(QObject):
    requested = Signal(object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.requested.connect(self.show_request)

    def confirm(self, action, payload, expires_at, cancelled):
        future = Future()
        seconds = min(60, max(0, expires_at - time.time() - 1)) if expires_at else 10
        deadline = time.monotonic() + seconds
        self.requested.emit((action, payload, future, deadline))
        while time.monotonic() < deadline and not (cancelled and cancelled.is_set()):
            try:
                return bool(future.result(timeout=min(.1, max(.001, deadline-time.monotonic()))))
            except FutureTimeout:
                pass
        future.cancel()
        return False

    @Slot(object)
    def show_request(self, request):
        action, payload, future, deadline = request
        if future.done() or time.monotonic() >= deadline:
            future.cancel()
            return
        dialog = QDialog(self.window)
        dialog.setWindowTitle('Delta — разрешить команду?')
        dialog.setModal(True)
        dialog.resize(500, 300)
        layout = QVBoxLayout(dialog)
        title = QLabel(COMMAND_LABELS[action])
        title.setStyleSheet('font-size:20px;font-weight:600')
        layout.addWidget(title)
        layout.addWidget(QLabel('Запрос от подключённого сервера Delta на этот компьютер.'))
        detail = payload.get('app_name') or payload.get('url') or payload.get('path') or {'browser':'Браузер','vscode':'Visual Studio Code'}.get(payload.get('app_id'), 'Имя компьютера, система и версия агента')
        target = QTextEdit()
        target.setReadOnly(True)
        target.setPlainText(detail)
        target.setMaximumHeight(110)
        layout.addWidget(target)
        countdown = QLabel()
        layout.addWidget(countdown)
        buttons = QHBoxLayout()
        deny = QPushButton('Отклонить')
        allow = QPushButton('Разрешить один раз')
        allow.setAutoDefault(False)
        deny.setDefault(True)
        buttons.addWidget(deny)
        buttons.addWidget(allow)
        layout.addLayout(buttons)
        def finish(approved):
            try:
                future.set_result(bool(approved) and time.monotonic() < deadline)
            except InvalidStateError:
                pass
        deny.clicked.connect(dialog.reject)
        allow.clicked.connect(dialog.accept)
        dialog.finished.connect(lambda result: finish(result == QDialog.DialogCode.Accepted))
        timer = QTimer(dialog)
        def tick():
            remaining = max(0, int(deadline-time.monotonic()))
            countdown.setText(f'Без подтверждения запрос будет отклонён через {remaining} с.')
            if future.done() or time.monotonic() >= deadline:
                dialog.reject()
        timer.timeout.connect(tick)
        timer.start(100)
        tick()
        dialog.finished.connect(timer.stop)
        dialog.finished.connect(dialog.deleteLater)
        self.window.show_window()
        dialog.open()
        deny.setFocus()


class LogoutWorker(QThread):
    completed = Signal(bool)
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
    def run(self):
        try:
            account_logout(self.settings.server, self.settings.token.get_secret_value())
            self.completed.emit(True)
        except Exception:
            self.completed.emit(False)


class ApiWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, settings, path, body=None):
        super().__init__()
        self.settings, self.path, self.body = settings, path, body

    def run(self):
        try:
            self.completed.emit(desktop_request(self.settings, self.path, self.body))
        except Exception as error:
            self.failed.emit(str(error) if isinstance(error, ValueError) else 'Не удалось получить ответ. Попробуйте позже.')


class AgentWorker(QThread):
    event = Signal(dict)

    def __init__(self, settings, directory, opener, password="", approvals=None):
        super().__init__()
        self.settings, self.directory = settings, directory
        self.opener = opener
        self.approvals = approvals
        self.password = password
        self.loop = self.task = None

    def run(self):
        async def work():
            self.loop = asyncio.get_running_loop()
            self.task = asyncio.current_task()
            if self.isInterruptionRequested():
                return
            s = self.settings
            if self.password:
                try:
                    result = await asyncio.to_thread(account_login, s.server, s.username, self.password)
                except ValueError as error:
                    self.event.emit({'event':'login_error', 'message':str(error)})
                    return
                finally:
                    self.password = ''
                s.token = SecretStr(result['token'])
                save_settings(s, self.directory)
                self.event.emit({'event':'authenticated'})
            adapter = get_platform()
            if sys.platform == 'darwin':
                adapter.open_path = self.opener.open_path
            await run_agent(s.server, s.token.get_secret_value(), s.name, self.directory,
                            s.allowed_roots, capabilities=s.capabilities,
                            allowed_apps=s.allowed_apps + (['*'] if s.allow_installed_apps else []), on_event=self.event.emit, adapter=adapter,
                            permission=s.permission, confirm=self.approvals.confirm if self.approvals else None)
        try:
            asyncio.run(work())
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self.event.emit({'event': 'failed', 'error_type': type(error).__name__})

    def stop(self):
        self.requestInterruption()
        if self.loop and self.task:
            try:
                self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError:
                pass


def app_icon():
    pixmap = QPixmap(512, 512)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor('#111111'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 512, 512, 108, 108)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor('#cdcdcd'), 30, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawPolygon(QPolygonF([QPointF(256,100),QPointF(100,392),QPointF(412,392)]))
    painter.end()
    return QIcon(pixmap)


class AgentWindow(QMainWindow):
    def __init__(self, directory=None):
        super().__init__()
        self.directory = directory or config_directory()
        self.worker = None
        self.logout_worker = None
        self.opener = DesktopOpener()
        self.approvals = ApprovalBroker(self)
        self.quitting = False
        self.setWindowTitle('Delta Agent — этот компьютер')
        self.setWindowIcon(app_icon())
        self.resize(660, 720)
        self.api_workers = []
        self.session_generation = 0
        self.pending_settings = None
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 24, 28, 24)
        header = QHBoxLayout()
        title = QLabel('Δ  DELTA')
        title.setStyleSheet('font-size:24px; font-weight:600; color:#cccccc')
        header.addWidget(title)
        header.addStretch()
        settings_button = QPushButton('Настройки')
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(settings_button)
        layout.addLayout(header)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        login_page = QWidget()
        login_layout = QVBoxLayout(login_page)
        login_layout.addStretch()
        welcome = QLabel('Добро пожаловать')
        welcome.setStyleSheet('font-size:28px; font-weight:600')
        login_layout.addWidget(welcome)
        login_layout.addWidget(QLabel('Войдите в Delta, чтобы подключить этот компьютер.'))
        login_layout.addSpacing(24)
        self.username = QLineEdit()
        self.username.setPlaceholderText('Логин')
        self.username.setAccessibleName('Логин')
        self.password = QLineEdit()
        self.password.setPlaceholderText('Пароль')
        self.password.setAccessibleName('Пароль')
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self.connect_agent)
        login_layout.addWidget(self.username)
        login_layout.addWidget(self.password)
        self.login_error = QLabel('')
        self.login_error.setWordWrap(True)
        self.login_error.setStyleSheet('color:#c4c4c4')
        login_layout.addWidget(self.login_error)
        self.connect_button = QPushButton('Войти')
        self.connect_button.clicked.connect(self.connect_agent)
        login_layout.addWidget(self.connect_button)
        login_layout.addStretch(2)
        self.pages.addWidget(login_page)
        dashboard = QWidget()
        dashboard_layout = QVBoxLayout(dashboard)
        self.status = QLabel('Подключаем компьютер…')
        dashboard_layout.addWidget(self.status)
        tabs = QTabWidget()
        dashboard_layout.addWidget(tabs)
        assistant = QWidget()
        assistant_layout = QVBoxLayout(assistant)
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText('Что сделаем сегодня?\n\nПопросите Delta открыть проект или показать ваши задачи.')
        assistant_layout.addWidget(self.chat)
        self.target = QComboBox()
        self.target.addItem('Этот компьютер', None)
        self.target.setAccessibleName('Компьютер для команды')
        assistant_layout.addWidget(self.target)
        composer = QHBoxLayout()
        self.message = QLineEdit()
        self.message.setMaxLength(10000)
        self.message.setPlaceholderText('Что нужно сделать?')
        self.message.returnPressed.connect(self.send_message)
        composer.addWidget(self.message)
        self.send_button = QPushButton('Отправить')
        self.send_button.clicked.connect(self.send_message)
        composer.addWidget(self.send_button)
        assistant_layout.addLayout(composer)
        tabs.addTab(assistant, 'Ассистент')
        device_page = QWidget()
        devices_layout = QVBoxLayout(device_page)
        devices_layout.addWidget(QLabel('Ваши компьютеры'))
        self.devices = QListWidget()
        devices_layout.addWidget(self.devices)
        self.device_hint = QLabel('')
        self.device_hint.setWordWrap(True)
        devices_layout.addWidget(self.device_hint)
        self.refresh_button = QPushButton('Обновить')
        self.refresh_button.clicked.connect(self.refresh_devices)
        devices_layout.addWidget(self.refresh_button)
        tabs.addTab(device_page, 'Устройства')
        self.pages.addWidget(dashboard)
        self.setCentralWidget(panel)
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle('Настройки Delta')
        self.settings_dialog.resize(540, 640)
        settings_layout = QVBoxLayout(self.settings_dialog)
        settings_tabs = self.settings_tabs = QTabWidget()
        settings_layout.addWidget(settings_tabs)
        self.fields = QWidget()
        form = QFormLayout(self.fields)
        connection_page = QWidget()
        connection_form = QFormLayout(connection_page)
        settings_tabs.addTab(self.fields, 'Команды и доступ')
        settings_tabs.addTab(connection_page, 'Подключение')
        self.access_mode = QComboBox()
        self.access_mode.addItem('С подтверждениями', 'confirm')
        self.access_mode.addItem('Полный доступ', 'full')
        form.addRow('Режим', self.access_mode)
        hint = QLabel('Полный доступ выполняет разрешённые команды без вопросов.\nОтдельные запреты и ограничения папок сохраняются.')
        hint.setWordWrap(True)
        form.addRow(hint)
        self.command_permissions = {}
        for action, label in COMMAND_LABELS.items():
            choice = QComboBox()
            for text, value in [('По общему режиму', 'inherit'), ('Запретить', 'deny'),
                                ('Спрашивать', 'ask'), ('Разрешить', 'allow')]:
                choice.addItem(text, value)
            self.command_permissions[action] = choice
            form.addRow(label, choice)
        def update_mode_labels():
            label = 'По режиму: спрашивать' if self.access_mode.currentData() == 'confirm' else 'По режиму: разрешить'
            for choice in self.command_permissions.values():
                choice.setItemText(0, label)
        self.access_mode.currentIndexChanged.connect(update_mode_labels)
        update_mode_labels()
        self.command_permissions['open_url'].setCurrentIndex(self.command_permissions['open_url'].findData('deny'))
        form.addRow(QLabel('Доступные приложения и папки'))
        self.server = QLineEdit('http://192.168.0.28:8081')
        self.name = QLineEdit(socket.gethostname())
        connection_form.addRow('Сервер Delta', self.server)
        connection_form.addRow('Имя компьютера', self.name)
        self.urls = QCheckBox()  # Legacy settings compatibility; policy dropdown owns URL access.
        self.urls.hide()
        self.vscode = QCheckBox('Открывать Visual Studio Code')
        self.browser = QCheckBox('Открывать браузер')
        self.installed_apps = QCheckBox('Открывать установленные приложения (Finder и другие)')
        self.installed_apps.setChecked(True)
        for check in [self.installed_apps, self.vscode, self.browser]:
            form.addRow(check)
        self.roots = QListWidget()
        self.roots.setMaximumHeight(90)
        form.addRow('Разрешённые папки', self.roots)
        buttons = QHBoxLayout()
        add = QPushButton('Добавить папку…')
        add.clicked.connect(self.add_root)
        remove = QPushButton('Убрать')
        remove.clicked.connect(lambda: self.roots.takeItem(self.roots.currentRow()))
        buttons.addWidget(add)
        buttons.addWidget(remove)
        form.addRow(buttons)
        self.autostart = QCheckBox('Запускать при входе в систему')
        self.auto_connect = QCheckBox('Подключаться автоматически')
        self.auto_connect.setChecked(True)
        connection_form.addRow(self.autostart)
        connection_form.addRow(self.auto_connect)

        save = QPushButton('Сохранить настройки')
        save.clicked.connect(self.save_preferences)
        settings_layout.addWidget(save)
        self.disconnect_button = QPushButton('Отключить компьютер')
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.clicked.connect(self.disconnect_agent)
        settings_layout.addWidget(self.disconnect_button)
        self.logout_button = QPushButton('Выйти из аккаунта')
        self.logout_button.clicked.connect(self.logout_account)
        settings_layout.addWidget(self.logout_button)
        diagnostics = QPushButton('Показать диагностику')
        settings_layout.addWidget(diagnostics)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.document().setMaximumBlockCount(100)
        self.log.hide()
        diagnostics.clicked.connect(lambda: self.log.setVisible(not self.log.isVisible()))
        settings_layout.addWidget(self.log)
        self.device_timer = QTimer(self)
        self.device_timer.setInterval(15000)
        self.device_timer.timeout.connect(self.refresh_devices)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip('Delta Agent — не подключён')
        menu = QMenu(self)
        show = QAction('Открыть Delta Agent', self)
        show.triggered.connect(self.show_window)
        disconnect = QAction('Отключить', self)
        disconnect.triggered.connect(self.disconnect_agent)
        quit_action = QAction('Завершить Delta Agent', self)
        quit_action.triggered.connect(self.quit_agent)
        for action in [show, disconnect, quit_action]:
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window()
                                   if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        try:
            settings = load_settings(self.directory)
        except Exception:
            settings = None
            self.log.append('Не удалось загрузить настройки. Проверьте папки и введите настройки заново.')
        self.saved = settings
        if settings:
            self.server.setText(settings.server)
            self.name.setText(settings.name)
            self.username.setText(settings.username)
            self.urls.setChecked(settings.allow_urls)
            self.installed_apps.setChecked(settings.allow_installed_apps)
            self.vscode.setChecked('vscode' in settings.allowed_apps)
            self.browser.setChecked('browser' in settings.allowed_apps)
            self.roots.addItems(settings.allowed_roots)
            self.autostart.setChecked(settings.autostart)
            self.auto_connect.setChecked(settings.auto_connect)
            self.access_mode.setCurrentIndex(self.access_mode.findData(settings.access_mode))
            for action, choice in self.command_permissions.items():
                choice.setCurrentIndex(choice.findData(settings.command_permissions.get(action, 'deny' if action == 'open_url' and not settings.allow_urls else 'inherit')))
            if settings.auto_connect and settings.username:
                QTimer.singleShot(0, lambda: self.start_worker(settings))

    def open_settings(self):
        self.settings_dialog.show()
        self.settings_dialog.raise_()

    def reset_dashboard(self):
        self.session_generation += 1
        self.device_timer.stop()
        self.chat.clear()
        self.devices.clear()
        self.message.clear()
        self.target.clear()
        self.target.addItem('Этот компьютер', None)
        self.pages.setCurrentIndex(0)

    def save_preferences(self):
        try:
            old = self.saved
            settings = DesktopSettings(server=self.server.text(), name=self.name.text().strip(),
                username=self.username.text().strip(), token=old.token if old else 'pending-login-token',
                allowed_roots=[self.roots.item(i).text() for i in range(self.roots.count())],
                allow_installed_apps=self.installed_apps.isChecked(),
                allow_urls=self.command_permissions['open_url'].currentData() != 'deny', allowed_apps=[name for name, check in
                    [('vscode', self.vscode), ('browser', self.browser)] if check.isChecked()],
                autostart=self.autostart.isChecked(), auto_connect=self.auto_connect.isChecked(),
                access_mode=self.access_mode.currentData(), command_permissions={
                    action: choice.currentData() for action, choice in self.command_permissions.items()
                    if choice.currentData() != 'inherit'})
            if not old or old.server != settings.server:
                settings.token = SecretStr('pending-login-token')
                settings.auto_connect = False
            set_autostart(settings.autostart)
            save_settings(settings, self.directory)
            self.saved = settings
            if settings.token.get_secret_value() in {'pending-login-token', 'logged-out-session'}:
                self.reset_dashboard()
                self.disconnect_agent()
            elif self.worker:
                self.pending_settings = settings
                self.disconnect_agent()
            else:
                self.start_worker(settings)
            self.settings_dialog.hide()
        except Exception:
            QMessageBox.warning(self, 'Не удалось сохранить', 'Проверьте адрес сервера, имя компьютера и доступность выбранных папок.')

    def api_call(self, path, body, success, failure, finished):
        if not self.saved:
            return
        generation = self.session_generation
        worker = ApiWorker(self.saved, path, body)
        self.api_workers.append(worker)
        worker.completed.connect(lambda result: success(result) if generation == self.session_generation else None)
        worker.failed.connect(lambda error: failure(error) if generation == self.session_generation else None)
        def cleanup():
            self.api_workers.remove(worker)
            worker.deleteLater()
            finished()
        worker.finished.connect(cleanup)
        worker.start()

    def refresh_devices(self):
        if not self.refresh_button.isEnabled() or self.pages.currentIndex() != 1:
            return
        self.refresh_button.setEnabled(False)
        def display(devices):
            selected = self.target.currentData() or getattr(self, 'local_device_id', None)
            self.devices.clear()
            self.target.clear()
            for device in devices:
                name = device.get('display_name', 'Компьютер')
                online = device.get('status') == 'online'
                self.devices.addItem(('●  ' if online else '○  ') + name + (' — подключён' if online else ' — не в сети'))
                if online:
                    self.target.addItem(name, device['id'])
            index = self.target.findData(selected)
            if index >= 0:
                self.target.setCurrentIndex(index)
            elif self.target.count():
                self.target.insertItem(0, 'Выберите компьютер для команды', None)
                self.target.setCurrentIndex(0)
            self.device_hint.setText('' if devices else 'Пока нет устройств. Войдите в Delta на другом компьютере, чтобы подключить его.')
        self.api_call('devices', None, display, self.device_hint.setText,
                      lambda: self.refresh_button.setEnabled(True))

    def send_message(self):
        text = self.message.text().strip()
        if not text or not self.send_button.isEnabled() or self.pages.currentIndex() != 1:
            return
        self.chat.append('<p style="color:#cccccc">Вы</p><p>' + html.escape(text) + '</p>')
        self.message.clear()
        self.send_button.setEnabled(False)
        self.send_button.setText('Думаю…')
        def answer(result):
            self.chat.append('<p style="color:#cccccc">Δ Delta</p><p>' + html.escape(result.get('assistant_text') or result.get('message') or 'Ответ не получен.').replace('\n', '<br>') + '</p>')
        def failed(error):
            self.chat.append('<p style="color:#c4c4c4">' + html.escape(error) + '</p>')
        def done():
            self.send_button.setEnabled(True)
            self.send_button.setText('Отправить')
        self.api_call('message', {'message': text, 'device_id': self.target.currentData()}, answer, failed, done)

    def add_root(self):
        path = QFileDialog.getExistingDirectory(self, 'Разрешить открытие папки и вложенных каталогов')
        if path and path not in [self.roots.item(i).text() for i in range(self.roots.count())]:
            self.roots.addItem(path)

    def connect_agent(self):
        if self.worker:
            return
        try:
            settings = DesktopSettings(server=self.server.text(), token="pending-login-token", username=self.username.text().strip(),
                name=self.name.text().strip(), allowed_roots=[self.roots.item(i).text() for i in range(self.roots.count())],
                allow_installed_apps=self.installed_apps.isChecked(),
                allow_urls=self.command_permissions['open_url'].currentData() != 'deny', allowed_apps=[name for name, check in
                    [('vscode', self.vscode), ('browser', self.browser)] if check.isChecked()],
                autostart=self.autostart.isChecked(), auto_connect=self.auto_connect.isChecked(),
                access_mode=self.access_mode.currentData(), command_permissions={
                    action: choice.currentData() for action, choice in self.command_permissions.items()
                    if choice.currentData() != 'inherit'})
            if len(self.password.text()) < 10 or not settings.username:
                raise ValueError("Enter login credentials")
            set_autostart(settings.autostart)
        except Exception:
            # Pydantic exceptions include input values: never display/log them.
            QMessageBox.warning(self, 'Проверьте настройки',
                'Введите логин и пароль (не менее 10 символов). Адрес подключения можно проверить в настройках.')
            return
        self.start_worker(settings, self.password.text())
        self.password.clear()

    def start_worker(self, settings, password=""):
        if self.worker:
            return
        self.login_error.clear()
        self.connect_button.setText('Входим…')
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.worker = AgentWorker(settings, self.directory, self.opener, password, self.approvals)
        self.worker.event.connect(self.on_event)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def on_event(self, event):
        kind = event['event']
        if kind == 'authenticated':
            self.password.clear()
            self.saved = self.worker.settings
            self.pages.setCurrentIndex(1)
            return
        if kind == 'login_error':
            self.log.append(event['message'])
            self.login_error.setText(event['message'])
            self.pages.setCurrentIndex(0)
            return
        if kind == 'auth_required':
            self.reset_dashboard()
            self.login_error.setText('Сессия завершилась. Войдите снова.')
            self.log.append('Сессия завершилась. Введите логин и пароль для повторного входа.')
            return
        if kind == 'connected':
            self.saved = self.worker.settings
            self.local_device_id = event.get('device_id')
            self.pages.setCurrentIndex(1)
            self.refresh_devices()
            self.device_timer.start()
            text = '●  Подключён — этот компьютер доступен в Delta'
        elif kind == 'connecting':
            text = '●  Подключение к серверу…'
        elif kind == 'reconnecting':
            detail = 'Проверьте токен и адрес' if event.get('error_type') == 'InvalidStatus' else 'Проверьте сеть и сервер'
            text = f'●  Нет соединения. {detail}. Повтор через {event["delay"]} с'
        elif kind == 'command':
            text = f'{event.get("action")}: ' + ('выполнено' if event['success'] else 'отклонено / ошибка')
            if event.get('error_code') in {'ACTION_TIMEOUT', 'LOCAL_PERMISSION_REQUIRED'}:
                text += '. Проверьте системные диалоги и разрешения доступа к папке.'
        else:
            text = '●  Ошибка агента. Переподключитесь.'
        if kind != 'command':
            self.status.setText(text)
            self.tray.setToolTip('Delta Agent — ' + text)
        self.log.append(datetime.now().strftime('%H:%M:%S') + '  ' + text)

    def logout_account(self):
        if self.logout_worker:
            return
        settings = load_settings(self.directory)
        if not settings:
            return
        self.session_generation += 1
        self.device_timer.stop()
        self.disconnect_agent()
        self.logout_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        worker = LogoutWorker(settings)
        self.logout_worker = worker
        def complete(success):
            if success:
                settings.auto_connect = False
                settings.token = SecretStr('logged-out-session')
                save_settings(settings, self.directory)
                self.password.clear()
                self.log.append('Вы вышли из аккаунта.')
                self.saved = settings
                self.reset_dashboard()
                self.settings_dialog.hide()
            else:
                QMessageBox.warning(self, 'Нет связи', 'Не удалось завершить сессию на сервере. Повторите выход после восстановления связи.')
        def finished():
            worker.deleteLater()
            self.logout_worker = None
            self.logout_button.setEnabled(True)
            self.connect_button.setEnabled(self.worker is None)
        worker.completed.connect(complete)
        worker.finished.connect(finished)
        worker.start()

    def disconnect_agent(self):
        if self.worker:
            self.status.setText('●  Отключение…')
            self.disconnect_button.setEnabled(False)
            self.worker.stop()

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.connect_button.setText('Войти')
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.status.setText('●  Не подключён')
        self.tray.setToolTip('Delta Agent — не подключён')
        if self.quitting:
            QApplication.instance().quit()
        elif self.pending_settings:
            settings, self.pending_settings = self.pending_settings, None
            self.start_worker(settings)

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.tray.isVisible():
            event.ignore()
            self.hide()
        else:
            event.ignore()
            self.quit_agent()

    def quit_agent(self):
        if any(w.isRunning() for w in self.api_workers):
            self.hide()
            QTimer.singleShot(200, self.quit_agent)
            return
        if self.logout_worker and self.logout_worker.isRunning():
            self.logout_worker.finished.connect(self.quit_agent)
            return
        self.quitting = True
        self.hide()
        self.tray.hide()
        if self.worker:
            self.disconnect_agent()
        else:
            QApplication.instance().quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Delta Agent')
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    # Override native platform accents too (focus, selections, links, tooltips).
    palette = QPalette()
    for role, value in {
        'Window': '#0f0f0f', 'WindowText': '#eeeeee', 'Base': '#191919',
        'AlternateBase': '#242424', 'Text': '#eeeeee', 'Button': '#303030',
        'ButtonText': '#eeeeee', 'BrightText': '#ffffff', 'Highlight': '#dddddd',
        'HighlightedText': '#111111', 'Link': '#ffffff', 'LinkVisited': '#bbbbbb',
        'ToolTipBase': '#242424', 'ToolTipText': '#eeeeee', 'PlaceholderText': '#999999',
        'Light': '#666666', 'Midlight': '#444444', 'Dark': '#111111',
        'Mid': '#333333', 'Shadow': '#000000', 'Accent': '#ffffff',
    }.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(value))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor('#777777'))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor('#777777'))
    app.setPalette(palette)
    app.setStyleSheet('''QWidget { background:#0f0f0f; color:#f0f0f0; font-size:13px; }
        QLineEdit,QListWidget,QTextEdit { background:#1b1b1b; border:1px solid #3a3a3a;
        border-radius:5px; padding:6px; selection-background-color:#dddddd; selection-color:#111111; }
        QPushButton { background:#343434; border:1px solid #5e5e5e; border-radius:6px; padding:9px; }
        QPushButton:hover { background:#464646; } QPushButton:disabled { color:#777777; background:#1c1c1c; }
        QCheckBox { padding:4px; } QCheckBox::indicator { width:14px; height:14px;
        border:1px solid #868686; border-radius:3px; background:#1b1b1b; }
        QCheckBox::indicator:checked { background:#b0b0b0; border:1px solid #cccccc; }
        QMenu { background:#1b1b1b; }''')
    directory = config_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = QLockFile(str(directory / 'desktop.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, 'Delta Agent', 'Агент уже запущен. Откройте его через значок Δ в трее.')
        return
    window = AgentWindow(directory)
    if '--background' not in sys.argv or not window.saved or not window.tray.isVisible():
        window.show()
    app.exec()
    lock.unlock()


if __name__ == '__main__':
    main()
