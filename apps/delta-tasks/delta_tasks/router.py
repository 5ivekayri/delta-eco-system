from uuid import UUID
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from delta_contracts.errors import DeltaError
from delta_contracts.storage import serialize, utcnow
from delta_contracts.tasks import TaskCreate, TaskUpdate, Status, Priority, task_manifest
from .models import Task

router = APIRouter(prefix='/api/v1')


def get_task(session, task_id):
    task = session.get(Task, str(task_id))
    if task is None:
        raise DeltaError('TASK_NOT_FOUND', 'Task not found', 404)
    return task


@router.get('/manifest')
def manifest():
    return task_manifest()


@router.get('/tasks')
def list_tasks(request: Request, workspace_id: UUID | None = None,
               status: Status | None = None, priority: Priority | None = None):
    query = select(Task)
    for key, value in {'workspace_id': workspace_id, 'status': status, 'priority': priority}.items():
        if value is not None:
            query = query.where(getattr(Task, key) == str(value))
    with Session(request.app.state.engine) as session:
        return [serialize(task) for task in session.scalars(query.order_by(Task.created_at.desc()).limit(1000))]


@router.post('/tasks', status_code=201)
def create_task(body: TaskCreate, request: Request):
    values = body.model_dump()
    if values['workspace_id'] is not None:
        values['workspace_id'] = str(values['workspace_id'])
    task = Task(**values, completed_at=utcnow() if body.status == 'done' else None)
    with Session(request.app.state.engine) as session:
        session.add(task)
        session.commit()
        session.refresh(task)
        return serialize(task)


@router.get('/tasks/{task_id}')
def read_task(task_id: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        return serialize(get_task(session, task_id))


@router.patch('/tasks/{task_id}')
def update_task(task_id: UUID, body: TaskUpdate, request: Request):
    with Session(request.app.state.engine) as session:
        task = get_task(session, task_id)
        values = body.model_dump(exclude_unset=True)
        for key, value in values.items():
            setattr(task, key, str(value) if key == 'workspace_id' and value is not None else value)
        if 'status' in values:
            task.completed_at = (task.completed_at or utcnow()) if task.status == 'done' else None
        session.commit()
        session.refresh(task)
        return serialize(task)


@router.post('/tasks/{task_id}/complete')
def complete_task(task_id: UUID, request: Request):
    return update_task(task_id, TaskUpdate(status='done'), request)


@router.delete('/tasks/{task_id}')
def delete_task(task_id: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        task = get_task(session, task_id)
        session.delete(task)
        session.commit()
    return {'success': True, 'id': str(task_id)}
