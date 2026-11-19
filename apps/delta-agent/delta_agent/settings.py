"""Desktop-only settings. Never import a Core .env or database credentials."""
import json
import os
from pathlib import Path
import tempfile
from typing import Literal
from delta_contracts.devices import Action
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


def config_directory():
    return Path.home() / '.delta-agent-desktop'


def websocket_url(value: str) -> str:
    value = value.strip()
    if any(ord(c) < 33 for c in value):
        raise ValueError('Адрес не должен содержать пробелы')
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https', 'ws', 'wss'} or not parsed.hostname:
        raise ValueError('Укажите адрес http(s):// сервера или ws(s):// агента')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Адрес не должен содержать пароль, параметры или фрагмент')
    try:
        parsed.port
    except ValueError:
        raise ValueError('Неверный порт') from None
    path = parsed.path.rstrip('/')
    if parsed.scheme in {'http', 'https'}:
        # UI gateway and direct Core both supported, explicitly by their URL.
        if not path:
            path = '/core/ws/agents'
        elif path == '/core':
            path += '/ws/agents'
        elif not path.endswith('/ws/agents'):
            raise ValueError('Укажите корень веб-интерфейса или полный URL /ws/agents')
    elif not path.endswith('/ws/agents'):
        raise ValueError('WebSocket URL должен заканчиваться на /ws/agents')
    return urlunsplit(({'http': 'ws', 'https': 'wss'}.get(parsed.scheme, parsed.scheme), parsed.netloc, path, '', ''))


class DesktopSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    server: str
    token: SecretStr
    username: str = ""
    name: str = Field(min_length=1, max_length=255)
    allowed_roots: list[str] = Field(default_factory=list)
    allow_urls: bool = False
    allowed_apps: list[str] = Field(default_factory=list)
    allow_installed_apps: bool = True
    autostart: bool = False
    auto_connect: bool = True
    access_mode: Literal['confirm', 'full'] = 'confirm'
    command_permissions: dict[Action, Literal['allow', 'ask', 'deny']] = Field(default_factory=dict)

    def permission(self, action):
        return self.command_permissions.get(action, 'ask' if self.access_mode == 'confirm' else 'allow')

    @field_validator('server')
    @classmethod
    def valid_server(cls, value):
        return websocket_url(value)

    @field_validator('token')
    @classmethod
    def valid_token(cls, value):
        if len(value.get_secret_value()) < 16:
            raise ValueError('Токен должен содержать не менее 16 символов')
        return value

    @field_validator('allowed_apps')
    @classmethod
    def valid_apps(cls, values):
        if not all(value in {'vscode', 'browser'} or (value.startswith('installed-') and len(value)==34 and all(c in '0123456789abcdef' for c in value[10:])) for value in values):
            raise ValueError('Неизвестное приложение')
        return sorted(set(values))

    @field_validator('allowed_roots')
    @classmethod
    def valid_roots(cls, values):
        roots = [Path(value).expanduser().resolve(strict=True) for value in values]
        if any(not root.is_dir() for root in roots):
            raise ValueError('Разрешать можно только существующие каталоги')
        return sorted(set(map(str, roots)))

    @property
    def capabilities(self):
        result = ['system_info']
        if self.allow_urls:
            result.append('open_url')
        if self.allowed_roots:
            result.append('open_path')
        if self.allowed_apps or self.allow_installed_apps:
            result.append('open_app')
        return [action for action in result if self.permission(action) != "deny"]


def save_settings(settings: DesktopSettings, directory: Path):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = settings.model_dump()
    data['token'] = settings.token.get_secret_value()
    fd, temporary = tempfile.mkstemp(dir=directory, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
        os.replace(temporary, directory / 'settings.json')
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_settings(directory: Path):
    file = directory / 'settings.json'
    return DesktopSettings.model_validate_json(file.read_text(encoding='utf-8')) if file.exists() else None
