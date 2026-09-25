from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from delta_contracts.config import Settings
from delta_contracts.storage import utcnow
from delta_core.main import create_app
from delta_core.db import Base
from delta_core.devices.models import Device


@pytest.fixture
def setup(tmp_path):
    app=create_app(Settings(delta_token='test-token-only-123456',database_url=f'sqlite:///{tmp_path}/core.db',service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app,headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        with Session(app.state.engine) as session:
            device=Device(device_uid='test',display_name='Test',hostname='test',os='macos',architecture='x64',username='test',agent_version='0.1',capabilities=['open_app','open_path','open_url'],status='online',last_seen=utcnow())
            session.add(device);session.commit();device_id=device.id
        yield app,client,device_id


def test_workspace_crud_binding_and_launch(setup):
    app,client,device_id=setup
    response=client.post('/api/v1/workspaces',json={'name':'Thesis','description':'Research'})
    assert response.status_code==201
    workspace=response.json();path='/api/v1/workspaces/'+workspace['id']
    assert client.get(path).json()['name']=='Thesis'
    assert client.post('/api/v1/workspaces',json={'name':'thesis'}).status_code==409
    assert client.patch(path,json={'description':'Updated'}).json()['description']=='Updated'
    assert client.post(path+'/launch',json={'device_id':device_id}).json()['error_code']=='WORKSPACE_BINDING_NOT_FOUND'
    binding={'device_id':device_id,'local_path':'/projects/thesis','apps':['vscode'],'urls':['https://example.com']}
    assert client.post(path+'/bindings',json=binding).status_code==200
    assert len(client.get(path+'/bindings').json())==1
    app.state.devices.dispatch=AsyncMock(return_value={'success':True,'message':'opened'})
    launched=client.post(path+'/launch',json={'device_id':device_id}).json()
    assert launched['success']
    assert [r['action'] for r in launched['results']]==['open_app','open_path','open_url']
    assert app.state.devices.dispatch.await_count==3
    app.state.devices.dispatch=AsyncMock(side_effect=[{'success':False,'message':'app missing'},{'success':True,'message':'opened'},{'success':True,'message':'opened'}])
    assert not client.post(path+'/launch',json={'device_id':device_id}).json()['success']
    assert client.post(path+'/bindings',json={**binding,'urls':['file:///etc/passwd']}).status_code==422
    assert client.post(path+'/launch',json={}).json()['error_code']=='DEVICE_CONTEXT_REQUIRED'
    assert client.delete(path).json()['success']
    assert client.get(path).status_code==404
    assert client.get('/api/v1/workspaces').json()==[]
