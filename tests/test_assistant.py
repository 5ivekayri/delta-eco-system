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


async def test_openrouter_invalid_responses_and_network_failures():
    import pytest
    from delta_contracts.errors import DeltaError
    malformed = [
        {'choices': []},
        {'choices': [{'message': None}]},
        {'choices': [{'message': {'content': ['unexpected']}}]},
        {'choices': [{'message': {'tool_calls': [{'id': '1', 'function': {'name': 'shell', 'arguments': '{}'}}]}}]},
        {'choices': [{'message': {'tool_calls': [{'id': '1', 'function': {'name': 'tasks__list', 'arguments': 'not JSON'}}]}}]},
    ]
    for body in malformed:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as client:
            provider = OpenRouterLLMProvider('fake', 'test/model', client)
            with pytest.raises(DeltaError) as error:
                await provider.respond([], [{'name': 'tasks.list', 'description': '', 'input_schema': {}}], {})
            assert error.value.code == 'LLM_UNAVAILABLE'
    def unavailable(request):
        raise httpx.ConnectError('offline', request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        with pytest.raises(DeltaError) as error:
            await OpenRouterLLMProvider('fake', 'test/model', client).respond([], [], {})
        assert error.value.code == 'LLM_UNAVAILABLE'


async def test_disabled_local_tool_cannot_fall_through_to_external_tool():
    from delta_contracts.devices import EmptyPayload
    from delta_contracts.services import ServiceManifest
    from delta_core.tools.registry import LocalTool
    async def handler(_):
        raise AssertionError('Disabled handler must not run')
    async with httpx.AsyncClient() as client:
        services = ServiceRegistry([{'service_id': 'example', 'base_url': 'http://example'}], client)
        registry = ToolRegistry(services)
        registry.register(LocalTool('example.echo', 'Echo', EmptyPayload, handler, ['read'], enabled=False))
        service = services.get('example')
        service.status = 'online'
        service.manifest = ServiceManifest.model_validate({'service_id': 'example', 'name': 'Example', 'version': '1', 'tools': [
            {'name': 'example.echo', 'description': 'Echo', 'input_schema': {'type': 'object'}, 'method': 'GET', 'path': '/echo'}]})
        assert registry.specifications() == []
        result = await registry.execute(ToolCall(name='example.echo'))
        assert not result.success and result.error_code == 'TOOL_NOT_FOUND'


async def test_mock_asks_for_ambiguous_device():
    context = {'workspaces': [{'id': 'workspace', 'name': 'Dark Weather'}], 'devices': [
        {'id': 'first', 'display_name': 'Mac'}, {'id': 'second', 'display_name': 'Mac'}]}
    turn = await MockLLMProvider().respond([{'role': 'user', 'content': 'открой Dark Weather на Mac'}],
                                           [{'name': 'workspaces.launch'}], context)
    assert not turn.calls
    assert 'несколько' in turn.text


async def test_assistant_rejects_duplicate_calls_before_execution(tmp_path):
    from delta_core.assistant.service import AssistantService
    from delta_core.llm.base import LLMTurn
    class Provider:
        async def respond(self, *args):
            return LLMTurn(calls=[ToolCall(id='same', name='devices.list'), ToolCall(id='same', name='devices.list')])
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/core.db', service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    try:
        assistant = AssistantService(app.state.engine, app.state.tools, Provider())
        result = await assistant.message('покажи устройства')
        assert result['tool_calls'] == [] and result['tool_results'] == []
        assert 'лимит' in result['assistant_text']
    finally:
        await app.state.http.aclose()
        app.state.engine.dispose()


async def test_assistant_preserves_results_when_model_fails_after_action(tmp_path):
    from delta_contracts.errors import DeltaError
    from delta_core.assistant.service import AssistantService
    from delta_core.llm.base import LLMTurn
    class Provider:
        async def respond(self, messages, *args):
            if messages[-1]['role'] == 'tool':
                raise DeltaError('LLM_UNAVAILABLE', 'offline', 503)
            return LLMTurn(calls=[ToolCall(name='devices.list')])
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/core.db', service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    try:
        result = await AssistantService(app.state.engine, app.state.tools, Provider()).message('покажи устройства и объясни их состояние')
        assert result['tool_results'][0]['success']
        assert 'фактические результаты' in result['assistant_text']
        from sqlalchemy.orm import Session
        from delta_core.assistant.models import Interaction
        with Session(app.state.engine) as session:
            record = session.get(Interaction, result['id'])
            assert record.tool_results == result['tool_results']
    finally:
        await app.state.http.aclose()
        app.state.engine.dispose()


def test_assistant_rejects_blank_and_unauthenticated_requests(tmp_path):
    app = create_app(Settings(delta_token='test-token-only-123456', database_url=f'sqlite:///{tmp_path}/core.db', service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        assert client.post('/api/v1/assistant/message', json={'message': 'hello'}).status_code == 401
        for path in ['history', 'tools']:
            assert client.get('/api/v1/assistant/' + path).status_code == 401
        assert client.post('/api/v1/assistant/message', json={'message': '  \n '},
                           headers={'Authorization': 'Bearer test-token-only-123456'}).status_code == 422


async def test_openrouter_round_trip_returns_actual_tool_result():
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, json={'choices': [{'message': {'tool_calls': [
                {'id': 'call-1', 'function': {'name': 'tasks__list', 'arguments': '{}'}}]}}]})
        assert body['messages'][-2]['tool_calls'][0]['function']['name'] == 'tasks__list'
        assert body['messages'][-1]['tool_call_id'] == 'call-1'
        assert json.loads(body['messages'][-1]['content'])['data'][0]['title'] == 'Test task'
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Test task'}}]})
    tools = [{'name': 'tasks.list', 'description': 'List tasks', 'input_schema': {'type': 'object'}}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenRouterLLMProvider('fake', 'test/model', client)
        messages = [{'role': 'user', 'content': 'tasks'}]
        turn = await provider.respond(messages, tools, {})
        call = turn.calls[0]
        messages += [{'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': call.id, 'type': 'function', 'function': {'name': call.name, 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': call.id, 'content': json.dumps({'success': True, 'data': [{'title': 'Test task'}]})}]
        final = await provider.respond(messages, tools, {})
        assert final.text == 'Test task' and not final.calls
        assert messages[-2]['tool_calls'][0]['function']['name'] == 'tasks.list'
