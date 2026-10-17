import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from delta_contracts.config import Settings
from delta_contracts.tasks import task_manifest
from delta_contracts.tools import ToolCall
from delta_core.assistant.context import load_conversation, MAX_HISTORY_CHARS
from delta_core.assistant.models import Interaction
from delta_core.assistant.service import AssistantService
from delta_core.assistant.context_intents import ConversationIntentRouter
from delta_core.assistant.intents import LocalIntentRouter, RegistryTaskLookup
from delta_core.db import Base
from delta_core.llm.base import LLMTurn
from delta_core.llm.openrouter import OpenRouterLLMProvider
from delta_core.main import create_app
from delta_core.services.registry import ServiceRegistry
from delta_core.tools.registry import ToolRegistry

TOKEN = 'context-test-token-123456'

@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(delta_token=TOKEN, database_url=f'sqlite:///{tmp_path}/core.db', service_configs=[]))
    Base.metadata.create_all(app.state.engine)
    yield app
    app.state.engine.dispose()


def add_history(app, message='Создай задание номер 6', answer='Задача добавлена: Задание номер 6', results=None):
    with Session(app.state.engine) as session:
        row = Interaction(user_message=message, assistant_text=answer, tool_calls=[], tool_results=results or [])
        session.add(row); session.commit()


def task_result(rows, tool='tasks.list', success=True):
    return {'tool':tool,'success':success,'data':rows,'message':'ok'}


async def test_history_sent_to_actual_openrouter_wire_with_ids_and_no_replayed_calls(app):
    task_id = str(uuid4())
    add_history(app, results=[task_result({'id':task_id,'title':'Задание номер 6'}, 'tasks.create')])
    def handler(request):
        messages = json.loads(request.content)['messages']
        assert messages[-1]['content'] == 'Удали задание номер 6'
        assert messages[1]['content'] == 'Создай задание номер 6'
        assert task_id in messages[3]['content'] and 'Задание номер 6' in messages[3]['content']
        assert messages[2]['tool_calls'][0]['id'] == messages[3]['tool_call_id']
        assert messages[3]['role'] == 'tool'
        return httpx.Response(200,json={'choices':[{'message':{'content':'Контекст прочитан'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service=AssistantService(app.state.engine,app.state.tools,OpenRouterLLMProvider('test','test',client))
        assert 'Действие пока не выполнено' in (await service.message('Удали задание номер 6'))['assistant_text']
    await app.state.http.aclose()


async def test_clarification_and_correction_survive_service_restart(app):
    add_history(app,'Создай задачу','Как назвать задачу?')
    provider=SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(text='Уточнение получено')))
    service=AssistantService(app.state.engine,app.state.tools,provider)
    await service.message('Подготовить презентацию')
    assert provider.respond.call_args.args[0][1:3] == [
        {'role':'user','content':'Создай задачу'},
        {'role':'assistant','content':'Как назвать задачу?'}]
    restarted=AssistantService(app.state.engine,app.state.tools,provider)
    await restarted.message('Нет, подготовить отчёт')
    assert any(m['content']=='Подготовить презентацию' for m in provider.respond.call_args.args[0])
    await app.state.http.aclose()


@pytest.mark.parametrize('phrase,name,updates',[
    ('Заверши её','tasks.complete',{}),('Удали это задание','tasks.delete',{}),
    ('Переименуй её в Новый отчёт','tasks.update',{'title':'Новый отчёт'}),
    ('Поставь ей высокий приоритет','tasks.update',{'priority':'high'}),
])
async def test_contextual_action_executes_once_without_llm(app,phrase,name,updates):
    task={'id':str(uuid4()),'title':'Отчёт','status':'todo','priority':'medium'}
    add_history(app,results=[task_result(task,'tasks.create')])
    mutations=[]
    def handle(request):
        if request.url.path.endswith('manifest'):return httpx.Response(200,json=task_manifest())
        if request.url.path=='/health':return httpx.Response(200,json={'status':'ok'})
        if request.method=='GET':return httpx.Response(200,json=[task])
        mutations.append(request)
        return httpx.Response(200,json={**task,**updates,'success':True,'status':'done' if name=='tasks.complete' else task['status']})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        services=ServiceRegistry([{'service_id':'delta-tasks','base_url':'http://tasks'}],client)
        await services.refresh();registry=ToolRegistry(services)
        lookup=RegistryTaskLookup(registry)
        provider=SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(text='Удалено')))
        service=AssistantService(app.state.engine,registry,provider,local_router=ConversationIntentRouter(LocalIntentRouter(lookup),lookup))
        result=await service.message(phrase)
        assert result['tool_calls'][0]['name']==name
        assert result['tool_calls'][0]['arguments']=={'id':task['id'],**updates}
        assert len(mutations)==1
        provider.respond.assert_not_called()
    await app.state.http.aclose()


async def test_ordinal_refers_to_displayed_order_and_ambiguous_pronoun_asks():
    rows=[{'id':str(uuid4()),'title':'Первый'},{'id':str(uuid4()),'title':'Второй'}]
    lookup=AsyncMock(return_value=list(reversed(rows)))
    router=ConversationIntentRouter(LocalIntentRouter(),lookup)
    context={'recent_interactions':[{'tool_results':[task_result(rows)],'assistant_text':'• Первый\n• Второй'}]}
    specs=task_manifest()['tools']
    decision=await router.route('Заверши вторую',specs,context)
    assert decision.call.arguments=={'id':rows[1]['id']}
    ambiguous=await router.route('Удали её',specs,context)
    assert ambiguous.call is None and ambiguous.clarification
    lookup.return_value=[]
    assert (await router.route('Заверши вторую',specs,context)).call is None


async def test_unrelated_action_and_failed_result_do_not_reuse_old_task():
    rows=[{'id':str(uuid4()),'title':'Отчёт'}]
    router=ConversationIntentRouter(LocalIntentRouter(),AsyncMock(return_value=rows))
    context={'recent_interactions':[{'tool_results':[task_result(rows)]},{'tool_results':[{'tool':'iot.set_light','success':True,'data':{'enabled':True}}]}]}
    decision=await router.route('Удали её',task_manifest()['tools'],context)
    assert decision.call is None and decision.clarification


def test_history_budget_and_chronological_order(app):
    for n in range(20):add_history(app,str(n),'x'*10000,[task_result([{'id':str(uuid4()),'title':'y'*5000}]*30)])
    with Session(app.state.engine) as session:messages,recent=load_conversation(session)
    assert len(recent)<=12
    assert len(json.dumps(messages,ensure_ascii=False))<=MAX_HISTORY_CHARS
    assert [m['content'] for m in messages if m['role']=='user'][-1]=='19'
    assert [int(m['content']) for m in messages if m['role']=='user']==sorted(int(m['content']) for m in messages if m['role']=='user')


def test_voice_followup_uses_same_history_as_text(app):
    add_history(app,'Запомни: проект называется Север','Название проекта — Север')
    provider=SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(text='Север')))
    app.state.assistant.provider=app.state.assistant.router=provider
    app.state.stt.transcribe=AsyncMock(return_value='Как называется проект?')
    with TestClient(app,headers={'Authorization':f'Bearer {TOKEN}'}) as client:
        result=client.post('/api/v1/assistant/voice',files={'audio':('a.wav',b'test','audio/wav')})
        assert result.status_code==200 and result.json()['assistant_text']=='Север'
    assert 'Запомни: проект называется Север' in [m['content'] for m in provider.respond.call_args.args[0]]


async def test_title_reference_resolves_task_id_and_duplicate_title_does_not_guess():
    task={'id':str(uuid4()),'title':'Задание номер 6'}
    lookup=AsyncMock(return_value=[task])
    router=ConversationIntentRouter(LocalIntentRouter(),lookup)
    result=await router.route('Удали задание номер 6',task_manifest()['tools'],{})
    assert result.call.name=='tasks.delete' and result.call.arguments=={'id':task['id']}
    lookup.return_value=[task,{**task,'id':str(uuid4())}]
    result=await router.route('Удали задание номер 6',task_manifest()['tools'],{})
    assert result.call is None and result.clarification


async def test_read_lookup_is_not_mistaken_for_completion(app):
    from delta_contracts.tasks import TaskFilter,TaskID
    from delta_core.tools.registry import LocalTool
    task={'id':str(uuid4()),'title':'Отчёт','status':'todo'}
    registry=ToolRegistry(app.state.services)
    listing=AsyncMock(return_value=[task]);complete=AsyncMock(return_value={**task,'status':'done'})
    registry.register(LocalTool('tasks.list','List',TaskFilter,listing,[]))
    registry.register(LocalTool('tasks.complete','Complete',TaskID,complete,[]))
    provider=SimpleNamespace(respond=AsyncMock(side_effect=[LLMTurn(calls=[ToolCall(name='tasks.list')]),LLMTurn(calls=[ToolCall(name='tasks.complete',arguments={'id':task['id']})])]))
    service=AssistantService(app.state.engine,registry,provider)
    result=await service.message('Заверши задачу Отчёт')
    assert complete.await_count==1 and listing.await_count==1
    assert provider.respond.await_count==2  # route + necessary lookup resolution; no extra final completion
    assert result['tool_results'][-1]['data']['status']=='done'
    await app.state.http.aclose()


async def test_model_cannot_claim_success_without_executing_tool(app):
    provider=SimpleNamespace(respond=AsyncMock(return_value=LLMTurn(text='Задача успешно удалена.')))
    service=AssistantService(app.state.engine,app.state.tools,provider)
    result=await service.message('Удали задачу Отчёт')
    assert not result['tool_results']
    assert 'успешно удалена' not in result['assistant_text']
    assert 'Действие пока не выполнено' in result['assistant_text']
    provider.respond.return_value=LLMTurn(text='Как назвать задачу?')
    result=await service.message('Создай задачу')
    assert 'Как назвать задачу?' in result['assistant_text']
    await app.state.http.aclose()


async def test_ambiguous_followup_persists_clarification_without_llm_or_mutation(app):
    rows=[{'id':str(uuid4()),'title':'Первый'},{'id':str(uuid4()),'title':'Второй'}]
    add_history(app,'Покажи задачи','• Первый\n• Второй',[task_result(rows)])
    registry=SimpleNamespace(specifications=lambda:task_manifest()['tools'], execute=AsyncMock())
    provider=SimpleNamespace(respond=AsyncMock(side_effect=AssertionError('Must clarify locally')))
    router=ConversationIntentRouter(LocalIntentRouter(),AsyncMock(return_value=rows))
    response=await AssistantService(app.state.engine,registry,provider,local_router=router).message('Удали её')
    assert not response['tool_calls'] and 'Уточните' in response['assistant_text']
    registry.execute.assert_not_called();provider.respond.assert_not_called()
    with Session(app.state.engine) as session:
        assert session.get(Interaction,response['id']).assistant_text==response['assistant_text']
    await app.state.http.aclose()


async def test_task_word_synonym_can_create_locally():
    decision=await LocalIntentRouter().route('Создай задание номер 6',task_manifest()['tools'],{})
    assert decision.call.name=='tasks.create' and decision.call.arguments=={'title':'номер 6'}
