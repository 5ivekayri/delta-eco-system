from typing import Literal
from uuid import UUID
from pydantic import Field, field_validator, model_validator
from .devices import StrictModel, URLPayload


class WorkspaceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=10000)

    @field_validator('name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Name cannot be blank')
        return value.strip()


class WorkspaceUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)

    @model_validator(mode='after')
    def nonnull(self):
        for key in self.model_fields_set:
            if getattr(self,key) is None:
                raise ValueError(f'{key} cannot be null')
        if self.name is not None:
            self.name=WorkspaceCreate.nonblank(self.name)
        return self


class BindingInput(StrictModel):
    device_id: UUID
    local_path: str = Field(default='', max_length=4096)
    apps: list[Literal['vscode','browser']] = Field(default_factory=list, max_length=2)
    urls: list[str] = Field(default_factory=list, max_length=20)

    @field_validator('urls')
    @classmethod
    def valid_urls(cls, value):
        return [URLPayload(url=url).url for url in value]

    @model_validator(mode='after')
    def has_actions(self):
        if not self.local_path and not self.apps and not self.urls:
            raise ValueError('Configure at least one path, app or URL')
        return self


class LaunchInput(StrictModel):
    workspace_id: UUID | None = None
    workspace_name: str | None = None
    device_id: UUID | None = None
    device_name: str | None = None
