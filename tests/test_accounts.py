from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select
from delta_contracts.config import Settings
from delta_core.main import create_app
from delta_core.db import Base
from delta_core.accounts.models import User,LoginSession
from delta_core.accounts.service import hash_password


def test_account_roles_sessions_and_agent_scope(tmp_path,monkeypatch):
    monkeypatch.setenv('DELTA_ACCOUNTS_ENABLED','true')
    app=create_app(Settings(delta_token='internal-test-token-only',database_url=f'sqlite:///{tmp_path}/core.db',service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        db.add(User(username='admin',password_hash=hash_password('test-password-123'),role='admin'));db.commit()
    with TestClient(app) as c:
        assert c.get('/api/v1/devices',headers={'Authorization':'Bearer internal-test-token-only'}).status_code==401
        assert c.post('/api/v1/auth/register',json={'username':'newuser','password':'test-password-123','role':'admin'}).status_code==422
        assert c.post('/api/v1/auth/register',json={'username':'newuser','password':'test-password-123'}).status_code==200
        assert c.post('/api/v1/auth/login',json={'username':'newuser','password':'test-password-123'}).json()['role']=='pending'
        assert c.get('/api/v1/devices').status_code==403
        assert c.get('/api/v1/task-proxy/tasks').status_code==403
        assert c.post('/api/v1/auth/agent-login',json={'username':'newuser','password':'test-password-123'}).status_code==403
        assert c.post('/api/v1/auth/login',json={'username':'admin','password':'wrong-password'}).status_code==401
        r=c.post('/api/v1/auth/login',json={'username':'ADMIN','password':'test-password-123'})
        assert r.status_code==200 and r.json()['role']=='admin'
        assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
        assert c.get('/api/v1/devices').status_code==200
        assert c.post('/api/v1/workspaces',json={'name':'blocked'}).status_code==403
        agent=c.post('/api/v1/auth/agent-login',json={'username':'admin','password':'test-password-123'}).json()['token']
        c.post('/api/v1/auth/logout',json={},headers={'X-Delta-Request':'1'})
        assert c.get('/api/v1/devices').status_code==401
        assert c.get('/api/v1/devices',headers={'Authorization':'Bearer '+agent}).status_code==401
        with Session(app.state.engine) as db:
            assert all(row.digest!=agent for row in db.scalars(select(LoginSession)))
            assert db.scalar(select(User).where(User.username=='admin')).password_hash!='test-password-123'
        c.post('/api/v1/auth/logout',json={},headers={'Authorization':'Bearer '+agent})
        from delta_core.accounts.service import resolve
        assert resolve(app.state.engine,agent,'agent') is None
