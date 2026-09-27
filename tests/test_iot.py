from types import SimpleNamespace
from unittest.mock import AsyncMock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from delta_contracts.config import Settings
from delta_contracts.errors import DeltaError
from delta_contracts.iot import IoTState
from delta_contracts.storage import utcnow
from delta_core.activity.models import ActivityEvent
from delta_core.db import Base
from delta_core.iot.adapter import VirtualIoTAdapter
from delta_core.main import create_app

TOKEN = 'test-token-only-123456'


@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(delta_token=TOKEN,database_url=f'sqlite:///{tmp_path}/iot.db',service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    return app


@pytest.fixture
def client(app):
    with TestClient(app,headers={'Authorization':f'Bearer {TOKEN}'}) as client:
        yield client


def test_state_light_auth_and_persistence(client):
    assert client.get('/api/v1/iot/state',headers={'Authorization':'bad'}).status_code == 401
    assert client.post('/api/v1/iot/light',json={'enabled':True},headers={'Authorization':'bad'}).status_code == 401
    initial = client.get('/api/v1/iot/state').json()
    assert {key:initial[key] for key in ['source','desk_light','temperature','brightness','motion']} == {
        'source':'virtual','desk_light':False,'temperature':23.0,'brightness':30,'motion':True}
    first = client.post('/api/v1/iot/light',json={'enabled':True})
    assert first.status_code == 200 and first.json()['desk_light'] is True
    second = client.post('/api/v1/iot/light',json={'enabled':True})
    assert second.json()['updated_at'] == first.json()['updated_at']
    # Replacing the adapter must not reset the database state.
    client.app.state.iot = VirtualIoTAdapter(client.app.state.engine)
    assert client.get('/api/v1/iot/state').json()['desk_light'] is True
    with Session(client.app.state.engine) as session:
        events = list(session.scalars(select(ActivityEvent).where(ActivityEvent.event_type == 'IOT_ACTION')))
        assert len(events) == 1 and events[0].details['enabled'] is True
    assert client.post('/api/v1/iot/light',json={'enabled':False}).json()['desk_light'] is False


@pytest.mark.parametrize('body',[{}, {'enabled':'false'}, {'enabled':1}, {'enabled':None}, {'enabled':True,'device_name':'unknown'}])
def test_invalid_light_payload_cannot_change_state(client, body):
    assert client.post('/api/v1/iot/light',json=body).status_code == 422
    assert client.get('/api/v1/iot/state').json()['desk_light'] is False


@pytest.mark.parametrize('message,tool,key,value',[
    ('Включи рабочий свет','iot.set_light','enabled',True),
    ('Выключи свет','iot.set_light','enabled',False),
    ('Какая температура','iot.get_temperature','temperature',23.0),
    ('Покажи освещённость','iot.get_brightness','brightness',30),
    ('Есть ли движение','iot.get_motion','motion',True),
])
def test_assistant_local_tools_once_without_llm(client,message,tool,key,value):
    service = client.app.state.assistant
    service.provider.respond = AsyncMock(side_effect=AssertionError('LLM must not run'))
    service.router.respond = service.provider.respond
    registered = client.app.state.tools.local[tool]
    registered.handler = AsyncMock(wraps=registered.handler)
    response = client.post('/api/v1/assistant/message',json={'message':message})
    assert response.status_code == 200
    data = response.json()
    assert data['route_source'] == 'local' and data['execution_path'] == 'fast'
    assert len(data['tool_results']) == 1 and data['tool_results'][0]['success']
    assert data['tool_results'][0]['data'][key] == value
    registered.handler.assert_awaited_once()
    service.provider.respond.assert_not_called()


def test_adapter_can_be_replaced_without_changing_routes_or_assistant(client):
    state = IoTState(source='test-adapter',desk_light=True,temperature=19.5,brightness=42,motion=False,updated_at=utcnow())
    adapter = SimpleNamespace(get_state=AsyncMock(return_value=state),set_light=AsyncMock(return_value=state))
    client.app.state.iot = adapter
    assert client.get('/api/v1/iot/state').json()['temperature'] == 19.5
    assert client.post('/api/v1/iot/light',json={'enabled':True}).json()['source'] == 'test-adapter'
    result = client.post('/api/v1/assistant/message',json={'message':'Какая температура'}).json()
    assert '19.5' in result['assistant_text']
    assert result['tool_results'][0]['data']['source'] == 'test-adapter'
    adapter.set_light.assert_awaited_once_with(True)


def test_adapter_error_has_no_false_success(client):
    client.app.state.iot = SimpleNamespace(set_light=AsyncMock(side_effect=DeltaError('IOT_UNAVAILABLE','offline',503)))
    assert client.post('/api/v1/iot/light',json={'enabled':True}).status_code == 503
    result = client.post('/api/v1/assistant/message',json={'message':'Включи свет'}).json()
    assert not result['tool_results'][0]['success']
    assert 'offline' in result['assistant_text']


async def test_audit_and_state_commit_atomically(app,monkeypatch):
    assert not (await app.state.iot.get_state()).desk_light
    import delta_core.iot.adapter as module
    def failed(*args,**kwargs):
        raise SQLAlchemyError('audit failed')
    monkeypatch.setattr(module,'record_event',failed)
    with pytest.raises(DeltaError):
        await app.state.iot.set_light(True)
    assert not (await app.state.iot.get_state()).desk_light


def test_voice_light_and_temperature_use_same_registered_adapter(client):
    client.app.state.stt.transcript = 'Включи рабочий свет'
    first = client.post('/api/v1/assistant/voice',files={'audio':('voice.wav',b'mock','audio/wav')}).json()
    assert first['timings']['router_calls'] == 0
    assert first['tool_results'][0]['data']['enabled'] is True
    assert client.get('/api/v1/iot/state').json()['desk_light'] is True
    client.app.state.stt.transcript = 'Какая температура'
    second = client.post('/api/v1/assistant/voice',files={'audio':('voice.wav',b'mock','audio/wav')}).json()
    assert second['tool_results'][0]['data']['temperature'] == 23
    assert second['timings']['response_generation_calls'] == 0


def test_migration_seeds_once_and_preserves_changes(tmp_path,monkeypatch):
    url = f'sqlite:///{tmp_path}/migrations.db'
    monkeypatch.setenv('DATABASE_URL',url)
    monkeypatch.setenv('DELTA_TOKEN',TOKEN)
    config = Config('apps/delta-core/alembic.ini')
    command.upgrade(config,'head')
    engine = create_engine(url)
    from delta_core.iot.models import VirtualIoTState
    with Session(engine) as session:
        row = session.get(VirtualIoTState,1)
        assert row.temperature == 23 and not row.desk_light
        row.desk_light = True
        session.commit()
    command.upgrade(config,'head')
    with Session(engine) as session:
        assert session.get(VirtualIoTState,1).desk_light is True
    command.downgrade(config,'0004')
    assert 'virtual_iot_state' not in inspect(engine).get_table_names()
    assert 'assistant_history' in inspect(engine).get_table_names()
    engine.dispose()
