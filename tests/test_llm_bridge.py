import httpx
import pytest
from unittest.mock import Mock
from delta_core.assistant.service import AssistantService
from delta_core.llm.openrouter import OpenRouterLLMProvider
from delta_contracts.errors import DeltaError


def test_catalogue_constrains_model_without_mutating_registry():
    tools=Mock()
    original=[{'name':'devices.open_app','description':'Open app','input_schema':{'properties':{'app_name':{'type':'string'}}}}]
    tools.specifications.return_value=original
    service=AssistantService(None,tools,None,application_catalogue=lambda:{'pc':[{'name':'Visual Studio Code'}]})
    assert service.model_specifications()[0]['input_schema']['properties']['app_name']['enum']==['Visual Studio Code']
    assert 'enum' not in original[0]['input_schema']['properties']['app_name']
    service.application_catalogue=lambda:{}
    assert service.model_specifications()==[]


async def test_invented_application_is_rejected_before_execution():
    def response(request):
        return httpx.Response(200,json={'choices':[{'message':{'tool_calls':[{'id':'1','function':{'name':'devices__open_app','arguments':'{"app_name":"code"}'}}]}}]})
    specs=[{'name':'devices.open_app','description':'Open','input_schema':{'type':'object','properties':{'app_name':{'enum':['Visual Studio Code']}}}}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(DeltaError):await OpenRouterLLMProvider('key','model',client).respond([],specs,{})


async def test_bridge_endpoint_has_no_duplicate_retry(monkeypatch):
    monkeypatch.setenv('DELTA_LLM_BRIDGE_URL','http://127.0.0.1:8092/v1')
    calls=[]
    def response(request):
        calls.append(str(request.url));return httpx.Response(503,json={'error':'unavailable'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(DeltaError):await OpenRouterLLMProvider('key','model',client).respond([],[],{})
    assert calls==['http://127.0.0.1:8092/v1/chat/completions']


def test_bridge_endpoint_rejects_nonlocal_host(monkeypatch):
    monkeypatch.setenv('DELTA_LLM_BRIDGE_URL','https://untrusted.example/v1')
    with pytest.raises(ValueError):OpenRouterLLMProvider('key','model')
