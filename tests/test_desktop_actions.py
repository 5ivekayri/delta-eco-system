from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from delta_core.activity.models import ActivityEvent
from delta_core.assistant.models import Interaction
from delta_core.llm.base import LLMTurn
from test_devices import app, HEADERS, REGISTER

APPS=[{'id':'installed-code','name':'Visual Studio Code','aliases':['vscode']}]


@pytest.mark.parametrize('message,action',[('закрой vscode','close_app'),('сверни vscode','minimize_app')])
def test_window_actions_dispatch_exact_id_without_llm(app,message,action):
    forbidden=AsyncMock(side_effect=AssertionError('No LLM on exact command'))
    app.state.assistant.provider.respond=forbidden;app.state.assistant.router.respond=forbidden
    with TestClient(app) as client:
        with client.websocket_connect('/ws/agents',headers=HEADERS) as agent:
            agent.send_json({**REGISTER,'capabilities':['open_app','close_app','minimize_app'],'applications':APPS})
            device=agent.receive_json()['device_id']
            with ThreadPoolExecutor() as pool:
                future=pool.submit(client.post,'/api/v1/assistant/message',headers=HEADERS,json={'message':message,'device_id':device})
                command=agent.receive_json()
                assert command['action']==action and command['payload']=={'app_id':'installed-code'}
                agent.send_json({'type':'command_result','command_id':command['command_id'],'success':True,'message':'request sent'})
                response=future.result(timeout=5)
            assert response.status_code==200
            assert response.json()['tool_calls'][0]['name']=='devices.'+action
    forbidden.assert_not_called()


def test_lists_entire_catalogue_without_llm(app):
    app.state.assistant.provider.respond=AsyncMock(side_effect=AssertionError('No LLM'))
    with TestClient(app) as client:
        with client.websocket_connect('/ws/agents',headers=HEADERS) as agent:
            apps=[{'id':f'app-{i}','name':f'Application {i}'} for i in range(114)]
            agent.send_json({**REGISTER,'applications':apps})
            device=agent.receive_json()['device_id']
            response=client.post('/api/v1/assistant/message',headers=HEADERS,json={'message':'выведи список всех программ','device_id':device})
            assert response.status_code==200
            assert 'Application 113' in response.json()['assistant_text']
            assert response.json()['assistant_text'].count('• ')==114


def test_screen_image_is_not_persisted_in_activity_or_history(app,monkeypatch):
    monkeypatch.setenv('DELTA_LLM_BRIDGE_URL','http://127.0.0.1:8092/v1')
    app.state.llm_http=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'vision_available':True})))
    app.state.assistant.provider.respond=AsyncMock(return_value=LLMTurn(text='На экране тестовое окно.'))
    with TestClient(app) as client:
        with client.websocket_connect('/ws/agents',headers=HEADERS) as agent:
            agent.send_json({**REGISTER,'capabilities':['capture_screen']})
            device=agent.receive_json()['device_id']
            with ThreadPoolExecutor() as pool:
                future=pool.submit(client.post,'/api/v1/assistant/message',headers=HEADERS,json={'message':'что происходит на экране','device_id':device})
                command=agent.receive_json();assert command['action']=='capture_screen'
                agent.send_json({'type':'command_result','command_id':command['command_id'],'success':True,'message':'captured',
                                 'data':{'image_url':'data:image/jpeg;base64,AAAA','width':1,'height':1}})
                response=future.result(timeout=5)
            assert response.json()['assistant_text']=='На экране тестовое окно.'
    with Session(app.state.engine) as db:
        for row in db.scalars(select(ActivityEvent)):
            assert 'base64' not in json.dumps(row.details)
        for row in db.scalars(select(Interaction)):
            assert 'base64' not in json.dumps(row.tool_results)


@pytest.mark.parametrize('code,available',[(200,False),(503,False)])
def test_unavailable_vision_never_requests_capture(app,monkeypatch,code,available):
    monkeypatch.setenv('DELTA_LLM_BRIDGE_URL','http://127.0.0.1:8092/v1')
    app.state.llm_http=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(code,json={'vision_available':available})))
    app.state.devices.dispatch=AsyncMock(side_effect=AssertionError('No capture when vision unavailable'))
    with TestClient(app) as client:
        with client.websocket_connect('/ws/agents',headers=HEADERS) as agent:
            agent.send_json({**REGISTER,'capabilities':['capture_screen']})
            device=agent.receive_json()['device_id']
            response=client.post('/api/v1/assistant/message',headers=HEADERS,json={'message':'что происходит на экране','device_id':device})
            assert 'VISION_UNAVAILABLE' in response.text or 'Локальная Qwen' in response.text or 'Bridge недоступен' in response.text
    app.state.devices.dispatch.assert_not_called()
