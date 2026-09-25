from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .devices import StrictModel

Status = Literal['todo', 'in_progress', 'done']
Priority = Literal['low', 'medium', 'high']


class TaskCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default='', max_length=10000)
    workspace_id: UUID | None = None
    status: Status = 'todo'
    priority: Priority = 'medium'
    due_date: date | None = None


class TaskUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    workspace_id: UUID | None = None
    status: Status | None = None
    priority: Priority | None = None
    due_date: date | None = None

    @model_validator(mode='after')
    def reject_null_required(self):
        for key in self.model_fields_set - {'workspace_id', 'due_date'}:
            if getattr(self, key) is None:
                raise ValueError(f'{key} cannot be null')
        return self


class TaskFilter(StrictModel):
    workspace_id: UUID | None = None
    status: Status | None = None
    priority: Priority | None = None


class TaskID(StrictModel):
    id: UUID


class TaskToolUpdate(TaskUpdate):
    id: UUID


def task_manifest():
    specs = [
        ('create', TaskCreate, 'POST', '/api/v1/tasks', 'body', ['tasks:write']),
        ('list', TaskFilter, 'GET', '/api/v1/tasks', 'query', ['tasks:read']),
        ('get', TaskID, 'GET', '/api/v1/tasks/{id}', 'query', ['tasks:read']),
        ('update', TaskToolUpdate, 'PATCH', '/api/v1/tasks/{id}', 'body', ['tasks:write']),
        ('complete', TaskID, 'POST', '/api/v1/tasks/{id}/complete', 'body', ['tasks:write']),
        ('delete', TaskID, 'DELETE', '/api/v1/tasks/{id}', 'query', ['tasks:delete']),
    ]
    return {'service_id':'delta-tasks', 'name':'Delta Tasks', 'version':'0.1.0',
            'description':'Independent task management service', 'health_url':'/health', 'enabled':True,
            'tools':[{'name':f'tasks.{name}', 'description':f'{name.capitalize()} tasks',
                      'input_schema':schema.model_json_schema(), 'permissions':permissions, 'enabled':True,
                      'method':method, 'path':path, 'arguments_in':location}
                     for name,schema,method,path,location,permissions in specs]}
