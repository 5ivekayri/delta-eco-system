import json
import httpx
from fastapi.testclient import TestClient
from delta_contracts.config import Settings
from delta_contracts.tools import ToolCall
from delta_core.main import create_app
from delta_core.db import Base
from delta_core.services.registry import ServiceRegistry
from delta_core.tools.registry import ToolRegistry
from delta_core.llm.openrouter import OpenRouterLLMProvider
from delta_core.llm.mock import MockLLMProvider


async def test_unknown_service_plugs_in_without_assistant_changes():
    calls=[]
    manifest={'service_id':'example-service','name':'Example','version':'1','tools':[
        {'name':'example.echo','description':'Echo input','input_schema':{'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False},'method':'POST','path':'/echo','arguments_in':'body'}]}
    def handler(request):
        if request.url.path.endswith('manifest'):return httpx.Response(200,json=manifest)
        if request.url.path=='/health':return httpx.Response(200,json={'status':'ok'})
        calls.append(request)
        return httpx.Response(200,json={'echo':json.loads(request.content)['text']})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        services=ServiceRegistry([{'service_id':'example-service','base_url':'http://example'}],client)
        await services.refresh();registry=ToolRegistry(services)
        assert registry.specifications()[0]['name']=='example.echo'
        result=await registry.execute(ToolCall(name='example.echo',arguments={'text':'hello'}))
        assert result.success and result.data=={'echo':'hello'}
        invalid=await registry.execute(ToolCall(name='example.echo',arguments={'text':123}))
        assert not invalid.success and invalid.error_code=='TOOL_VALIDATION_ERROR'
        assert len(calls)==1
        assert not (await registry.execute(ToolCall(name='shell.execute'))).success


def test_assistant_mock_devices_history_and_validation(tmp_path):
    app=create_app(Settings(delta_token='test-token-only-123456',database_url=f'sqlite:///{tmp_path}/core.db',service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app,headers={'Authorization':'Bearer test-token-only-123456'}) as client:
        response=client.post('/api/v1/assistant/message',json={'message':'покажи устройства'})
        assert response.status_code==200
        result=response.json()
        assert result['tool_calls'][0]['name']=='devices.list'
        assert result['tool_results'][0]['success']
        assert 'нет подключённых' in result['assistant_text']
        assert len(client.get('/api/v1/assistant/history').json())==1
        assert client.post('/api/v1/assistant/message',json={'message':''}).status_code==422


async def test_mock_task_selection():
    turn=await MockLLMProvider().respond([{'role':'user','content':'добавь задачу протестировать API'}],[{'name':'tasks.create'}],{})
    assert turn.calls[0].name=='tasks.create'
    assert turn.calls[0].arguments['title']=='протестировать API'


async def test_assistant_calls_tasks_over_http(tmp_path):
    from delta_contracts.tasks import task_manifest
    from delta_core.assistant.service import AssistantService
    app=create_app(Settings(delta_token='test-token-only-123456',database_url=f'sqlite:///{tmp_path}/core.db',service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    def handler(request):
        if request.url.path.endswith('manifest'):return httpx.Response(200,json=task_manifest())
        if request.url.path=='/health':return httpx.Response(200,json={'status':'ok'})
        assert request.method=='POST' and request.url.path=='/api/v1/tasks'
        return httpx.Response(201,json={'id':'test-task','title':json.loads(request.content)['title']})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        services=ServiceRegistry([{'service_id':'delta-tasks','base_url':'http://tasks'}],client)
        await services.refresh()
        assistant=AssistantService(app.state.engine,ToolRegistry(services),MockLLMProvider())
        response=await assistant.message('добавь задачу протестировать API')
        assert response['tool_results'][0]['service_id']=='delta-tasks'
        assert response['assistant_text']=='Задача добавлена: протестировать API'
    await app.state.http.aclose()


async def test_openrouter_aliases_and_tool_messages():
    def handler(request):
        body=json.loads(request.content)
        assert body['tools'][0]['function']['name']=='tasks__list'
        assert request.headers['Authorization']=='Bearer fake-test-key'
        return httpx.Response(200,json={'choices':[{'message':{'content':None,'tool_calls':[{'id':'test-call','function':{'name':'tasks__list','arguments':'{}'}}]}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider=OpenRouterLLMProvider('fake-test-key','test/model',client)
        turn=await provider.respond([{'role':'user','content':'tasks'}],[{'name':'tasks.list','description':'List tasks','input_schema':{'type':'object'}}],{})
        assert turn.calls[0].name=='tasks.list'
