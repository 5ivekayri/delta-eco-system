from typing import Literal
from pydantic import Field, field_validator
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from .devices import StrictModel


class ToolDefinition(StrictModel):
    name: str = Field(pattern=r'^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$')
    description: str
    input_schema: dict
    permissions: list[str] = Field(default_factory=list)
    enabled: bool = True
    method: Literal['GET','POST','PATCH','DELETE'] = 'POST'
    path: str
    arguments_in: Literal['body','query'] = 'body'

    @field_validator('input_schema')
    @classmethod
    def check_schema(cls, value):
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as error:
            raise ValueError('Invalid tool JSON schema') from error
        return value

    @field_validator('path')
    @classmethod
    def relative_path(cls, value):
        if not value.startswith('/') or value.startswith('//') or '..' in value or '?' in value or '#' in value:
            raise ValueError('A relative API path is required')
        return value


class ServiceManifest(StrictModel):
    service_id: str = Field(pattern=r'^[a-z][a-z0-9-]*$')
    name: str
    version: str
    description: str = ''
    health_url: str = '/health'
    enabled: bool = True
    tools: list[ToolDefinition]

    @field_validator('health_url')
    @classmethod
    def health_path(cls, value):
        return ToolDefinition.relative_path(value)
