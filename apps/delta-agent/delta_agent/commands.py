from pathlib import Path

from pydantic import ValidationError
from delta_contracts.devices import CommandMessage, CommandResult, PAYLOAD_SCHEMAS
from .platforms.base import BasePlatformAdapter


class CommandExecutor:
    def __init__(self, platform: BasePlatformAdapter, allowed_roots: list[str]):
        self.platform = platform
        self.allowed_roots = [Path(root).expanduser().resolve() for root in allowed_roots]

    def execute(self, message: dict) -> dict:
        command_id = str(message.get("command_id", ""))
        try:
            command = CommandMessage.model_validate(message)
            payload = PAYLOAD_SCHEMAS[command.action].model_validate(command.payload)
            data = {}
            if command.action == "system_info":
                data = self.platform.get_system_info()
            elif command.action == "open_url":
                self.platform.open_url(payload.url)
            elif command.action == "open_app":
                self.platform.open_app(payload.app_id)
            elif command.action == "open_path":
                path = Path(payload.path).expanduser().resolve(strict=True)
                if not path.is_dir() or not any(path.is_relative_to(root) for root in self.allowed_roots):
                    raise ValueError("Path must be a directory inside an allowed root")
                self.platform.open_path(str(path))
            return CommandResult(command_id=command_id, success=True, message=f"{command.action} completed", data=data).model_dump()
        except (ValidationError, ValueError):
            return CommandResult(command_id=command_id, success=False, message="Command rejected by Agent policy",
                                 error_code="INVALID_COMMAND").model_dump()
        except Exception:
            return CommandResult(command_id=command_id, success=False, message="Desktop action failed; check local app/path configuration",
                                 error_code="ACTION_FAILED").model_dump()
