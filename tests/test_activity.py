from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from delta_contracts.config import Settings
from delta_core.main import create_app
from delta_core.db import Base
from delta_core.activity.models import record_event


def test_activity_auth_filters_and_stable_pagination(tmp_path):
    token='test-token-only-123456'
    app=create_app(Settings(delta_token=token,database_url=f'sqlite:///{tmp_path}/activity.db',service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as session:
        for i in range(5):
            record_event(session,'IOT_ACTION',str(i),id=str(i),created_at=datetime(2026,1,1,tzinfo=timezone.utc))
        record_event(session,'HEARTBEAT','hidden')
        session.commit()
    with TestClient(app) as client:
        assert client.get('/api/v1/activity').status_code==401
        client.headers['Authorization']=f'Bearer {token}'
        first=client.get('/api/v1/activity',params={'limit':2}).json()
        assert [r['id'] for r in first['items']]==['4','3']
        second=client.get('/api/v1/activity',params={'limit':2,**first['next_cursor']}).json()
        assert [r['id'] for r in second['items']]==['2','1']
        third=client.get('/api/v1/activity',params={'limit':2,**second['next_cursor']}).json()
        assert [r['id'] for r in third['items']]==['0'] and third['next_cursor'] is None
        assert len(client.get('/api/v1/activity',params={'event_type':'HEARTBEAT'}).json()['items'])==1
        assert len(client.get('/api/v1/activity',params={'include_heartbeats':True}).json()['items'])==6
        assert client.get('/api/v1/activity?limit=101').status_code==422
        assert client.get('/api/v1/activity?before_time=bad').status_code==422
