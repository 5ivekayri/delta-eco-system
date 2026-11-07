from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

Action = Literal["system_info", "open_url", "open_path", "open_app", "close_app", "minimize_app", "capture_screen"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Application(StrictModel):
    id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.-]+$')
    name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class Registration(StrictModel):
    type: Literal["register"] = "register"
    device_uid: str = Field(min_length=1, max_length=128)
    hostname: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    os: Literal["windows", "macos", "linux", "unknown"]
    architecture: str = Field(max_length=64)
    username: str = Field(max_length=255)
    agent_version: str = Field(max_length=32)
    capabilities: list[Action] = Field(max_length=7)
    approval_timeout: int = Field(default=0, ge=0, le=60)
    applications: list[Application] | None = Field(default=None, max_length=1024)


class CommandRequest(StrictModel):
    action: Action
    payload: dict = Field(default_factory=dict)


class CommandMessage(CommandRequest):
    type: Literal["command"] = "command"
    command_id: str
    expires_at: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class CommandResult(StrictModel):
    type: Literal["command_result"] = "command_result"
    command_id: str
    success: bool
    message: str = Field(max_length=2000)
    data: dict = Field(default_factory=dict)
    error_code: str | None = None


class EmptyPayload(StrictModel):
    pass


class URLPayload(StrictModel):
    url: str = Field(max_length=4096)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Only HTTP(S) URLs without credentials are allowed")
        if any(ord(c) < 32 for c in value):
            raise ValueError("Control characters are not allowed")
        return value


class PathPayload(StrictModel):
    path: str = Field(min_length=1, max_length=4096)


class AppPayload(StrictModel):
    app_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.-]+$')


class ApplicationTarget(StrictModel):
    device_id: str | None = Field(default=None, max_length=128)
    device_name: str | None = Field(default=None, max_length=255)


class OpenApplication(ApplicationTarget):
    app_name: str = Field(min_length=1, max_length=255)


PAYLOAD_SCHEMAS = {
    "system_info": EmptyPayload, "open_url": URLPayload,
    "open_path": PathPayload, "open_app": AppPayload,
    "close_app": AppPayload, "minimize_app": AppPayload, "capture_screen": EmptyPayload,
}
