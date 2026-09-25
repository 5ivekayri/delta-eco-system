from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from delta_contracts.config import Settings
from delta_tasks.main import create_app
from delta_tasks.db import Base


@pytest.fixture
def client(tmp_path):
    app=create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/tasks.db'))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app, headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        yield client


def test_task_lifecycle_and_filters(client):
    workspace=str(uuid4())
    response=client.post('/api/v1/tasks', json={'title':'API tests','workspace_id':workspace,'priority':'high','due_date':'2026-10-01'})
    assert response.status_code==201
    task=response.json()
    path=f"/api/v1/tasks/{task['id']}"
    assert client.get(path).json()['title']=='API tests'
    assert len(client.get('/api/v1/tasks',params={'workspace_id':workspace,'priority':'high','status':'todo'}).json())==1
    assert client.get('/api/v1/tasks',params={'priority':'low'}).json()==[]
    updated=client.patch(path,json={'status':'in_progress','description':'Check auth','due_date':None}).json()
    assert updated['due_date'] is None
    assert updated['status']=='in_progress'
    done=client.post(path+'/complete').json()
    assert done['completed_at'] is not None and done['status']=='done'
    assert client.patch(path,json={'status':'todo'}).json()['completed_at'] is None
    assert client.patch(path,json={'title':None}).status_code==422
    assert client.post('/api/v1/tasks',json={'title':'','status':'invalid'}).status_code==422
    assert len(client.get('/api/v1/manifest').json()['tools'])==6
    assert client.delete(path).json()['success']
    assert client.get(path).status_code==404
    assert client.get('/api/v1/tasks').json()==[]
