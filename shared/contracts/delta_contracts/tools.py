from typing import Any
from uuid import uuid4
from pydantic import Field
from .devices import StrictModel


class ToolCall(StrictModel):
    id: str = Field(default_factory=lambda:str(uuid4()))
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResult(StrictModel):
    tool: str
    success: bool
    data: Any = None
    message: str = ''
    error_code: str | None = None
    service_id: str | None = None
    duration_ms: int = 0
