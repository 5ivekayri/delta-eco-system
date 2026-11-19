from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from delta_contracts.devices import Registration, OpenApplication
from delta_core.devices.applications import ApplicationService
from test_devices import app, HEADERS, REGISTER

APPS=[{'id':'installed-finder','name':'Finder','aliases':['com.apple.finder','файндер']}]


def test_assistant_opens_finder_on_explicit_remote_mac_without_llm(app):
    forbidden=AsyncMock(side_effect=AssertionError('Must not call LLM'))
    app.state.assistant.provider.respond=forbidden
    app.state.assistant.router.respond=forbidden
    with TestClient(app) as client:
        with client.websocket_connect('/ws/agents',headers=HEADERS) as mac:
            mac.send_json({**REGISTER,'device_uid':'mac','display_name':'Mac — kayri','capabilities':['open_app'],'applications':APPS})
            mac_id=mac.receive_json()['device_id']
            with client.websocket_connect('/ws/agents',headers=HEADERS) as linux:
                linux.send_json({**REGISTER,'device_uid':'linux','display_name':'Linux','os':'linux','capabilities':['open_app'],'applications':[]})
                linux_id=linux.receive_json()['device_id']
                with ThreadPoolExecutor() as pool:
                    future=pool.submit(client.post,'/api/v1/assistant/message',headers=HEADERS,
                        json={'message':'открой Finder на Mac','device_id':linux_id})
                    command=mac.receive_json()
                    assert command['action']=='open_app' and command['payload']=={'app_id':'installed-finder'}
                    mac.send_json({'type':'command_result','command_id':command['command_id'],'success':True,'message':'opened'})
                    response=future.result(timeout=5)
                body=response.json()
                assert response.status_code==200 and body['tool_results'][0]['success']
                assert 'Finder' in body['assistant_text'] and 'Mac — kayri' in body['assistant_text']
                assert body['timings']['router_calls']==0
                assert body['tool_results'][0]['data']['device_id']==mac_id
                # Explicit Linux target must never fall back to the Mac.
                failure=client.post('/api/v1/assistant/message',headers=HEADERS,json={'message':'открой Finder','device_id':linux_id}).json()
                assert not failure['tool_results'][0]['success']
                assert failure['tool_results'][0]['error_code']=='APP_NOT_AVAILABLE'
    forbidden.assert_not_called()


async def test_legacy_agent_reports_required_update_instead_of_unsupported_claim(app):
    manager=app.state.devices
    device_id,_=await manager.register(Registration(**REGISTER),AsyncMock())
    from delta_contracts.errors import DeltaError
    with pytest.raises(DeltaError) as error:
        await ApplicationService(manager).open_app(OpenApplication(app_name='Finder',device_id=device_id))
    assert error.value.code=='AGENT_UPDATE_REQUIRED'


async def test_ambiguous_target_and_denied_command_never_claim_success(app):
    manager=app.state.devices
    for uid in ['mac1','mac2']:
        await manager.register(Registration(**{**REGISTER,'device_uid':uid,'capabilities':['open_app'],'applications':APPS}),AsyncMock())
    manager.dispatch=AsyncMock(return_value={'success':False,'message':'Denied','error_code':'COMMAND_DENIED'})
    service=ApplicationService(manager)
    from delta_contracts.errors import DeltaError
    with pytest.raises(DeltaError) as error:await service.open_app(OpenApplication(app_name='Finder'))
    assert error.value.code=='APP_AMBIGUOUS'
    manager.dispatch.assert_not_called()
    device_id=next(iter(manager.connections))
    result=await service.open_app(OpenApplication(app_name='Finder',device_id=device_id))
    assert not result['success'] and result['error_code']=='COMMAND_DENIED'
    manager.dispatch.assert_awaited_once()
