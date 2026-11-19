from pathlib import Path
import time
from subprocess import TimeoutExpired

from pydantic import ValidationError
from delta_contracts.devices import CommandMessage, CommandResult, PAYLOAD_SCHEMAS
from .platforms.base import BasePlatformAdapter


class CommandExecutor:
    def __init__(self, platform: BasePlatformAdapter, allowed_roots: list[str], capabilities=None, allowed_apps=None, permission=None, confirm=None):
        self.permission = permission or (lambda action: "allow")
        self.confirm = confirm
        self.platform = platform
        self.allowed_roots = [Path(root).expanduser().resolve() for root in allowed_roots]
        self.capabilities = set(platform.capabilities if capabilities is None else capabilities)
        self.allowed_apps = set(['browser', 'vscode', '*'] if allowed_apps is None else allowed_apps)

    def applications(self):
        if '*' not in self.allowed_apps and not any(key.startswith('installed-') for key in self.allowed_apps):
            return {}
        items = self.platform.installed_applications()
        return {key:app for key,app in items.items() if '*' in self.allowed_apps or key in self.allowed_apps}

    def execute(self, message: dict, cancelled=None) -> dict:
        command_id = str(message.get("command_id", ""))
        try:
            command = CommandMessage.model_validate(message)
            if command.action not in self.capabilities:
                raise ValueError('Capability is disabled locally')
            payload = PAYLOAD_SCHEMAS[command.action].model_validate(command.payload)
            # Validate the target before displaying any approval or invoking the OS.
            application = None
            if command.action == 'open_app':
                application = self.applications().get(payload.app_id)
                if application is None and payload.app_id not in self.allowed_apps.intersection({'browser','vscode'}):
                    return CommandResult(command_id=command_id, success=False, message='Приложение не установлено или запрещено на этом компьютере.', error_code='APP_NOT_AVAILABLE').model_dump()
            if command.action == 'open_path':
                path = Path(payload.path).expanduser().resolve(strict=True)
                if not path.is_dir() or not any(path.is_relative_to(root) for root in self.allowed_roots):
                    raise ValueError('Path must be a directory inside an allowed root')
                payload.path = str(path)
            policy = self.permission(command.action)
            if policy == 'deny':
                return CommandResult(command_id=command_id, success=False,
                    message='Команда запрещена в настройках этого компьютера.', error_code='COMMAND_DENIED').model_dump()
            def expired():
                return (cancelled is not None and cancelled.is_set()) or (command.expires_at is not None and time.time() >= command.expires_at)
            if expired():
                return CommandResult(command_id=command_id, success=False,
                    message='Запрос больше не действителен.', error_code='COMMAND_EXPIRED').model_dump()
            if policy == 'ask':
                details = payload.model_dump()
                if application is not None:
                    details['app_name'] = application.name
                if not self.confirm or not self.confirm(command.action, details, command.expires_at, cancelled):
                    return CommandResult(command_id=command_id, success=False,
                        message='Команда не подтверждена на компьютере.', error_code='APPROVAL_DECLINED').model_dump()
            elif policy != 'allow':
                raise ValueError('Unknown local command policy')
            if expired():
                return CommandResult(command_id=command_id, success=False,
                    message='Запрос больше не действителен.', error_code='COMMAND_EXPIRED').model_dump()
            data = {}
            if command.action == 'system_info':
                data = self.platform.get_system_info()
            elif command.action == 'open_url':
                self.platform.open_url(payload.url)
            elif command.action == 'open_app':
                if application is not None:
                    self.platform.open_installed_app(payload.app_id)
                else:
                    self.platform.open_app(payload.app_id)
            elif command.action == 'open_path':
                # Recheck symlinks after the user has spent time on the dialog.
                resolved = Path(payload.path).resolve(strict=True)
                if not resolved.is_dir() or not any(resolved.is_relative_to(root) for root in self.allowed_roots):
                    raise ValueError('Path changed while awaiting approval')
                self.platform.open_path(str(resolved))
            return CommandResult(command_id=command_id, success=True, message=f"{command.action} completed", data=data).model_dump()
        except (ValidationError, ValueError):
            return CommandResult(command_id=command_id, success=False, message="Command rejected by Agent policy",
                                 error_code="INVALID_COMMAND").model_dump()
        except PermissionError:
            return CommandResult(command_id=command_id, success=False,
                                 message="Allow Delta Agent access to this folder in operating system privacy settings",
                                 error_code="LOCAL_PERMISSION_REQUIRED").model_dump()
        except TimeoutExpired:
            return CommandResult(command_id=command_id, success=False,
                                 message="Operating system did not confirm opening in time; check desktop dialogs. The action was not retried.",
                                 error_code="ACTION_TIMEOUT").model_dump()
        except Exception as error:
            return CommandResult(command_id=command_id, success=False, message="Desktop action failed; check local app/path configuration",
                                 error_code="ACTION_FAILED", data={"error_type": type(error).__name__}).model_dump()
