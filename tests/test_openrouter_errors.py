import httpx
import pytest
from delta_contracts.errors import DeltaError
from delta_core.llm.openrouter import OpenRouterLLMProvider


@pytest.mark.parametrize('http_status',[200,503])
async def test_overload_retries_inference_once_and_recovers(http_status):
    requests=[]
    def handler(request):
        requests.append(request)
        if len(requests)==1:
            return httpx.Response(http_status,json={'error':{'code':503,'message':'private upstream details'}})
        return httpx.Response(200,json={'choices':[{'message':{'content':'Готово'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await OpenRouterLLMProvider('key','model',client).respond([],[],{})
    assert result.text=='Готово' and len(requests)==2 and result.calls==[]


@pytest.mark.parametrize('code,fragment',[(401,'API-ключ'),(402,'средств'),(403,'запретил'),(404,'недоступны'),(429,'лимит'),(503,'перегружена')])
async def test_embedded_errors_are_sanitized_and_retries_bounded(code,fragment):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'error':{'code':code,'message':'SECRET-UPSTREAM'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DeltaError) as error:
            await OpenRouterLLMProvider('key','model',client).respond([],[],{})
    assert fragment in error.value.message and 'SECRET' not in error.value.message
    assert len(calls)==(2 if code==503 else 1)


async def test_truncated_tool_call_is_never_returned_or_retried():
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'tool_calls':[{'id':'1','function':{'name':'tasks__create','arguments':'{}'}}]}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DeltaError,match='лимит ответа'):
            await OpenRouterLLMProvider('key','model',client).respond([],[],{})
    assert len(requests)==1


async def test_wall_clock_deadline_covers_retry_and_cancels_upstream():
    import asyncio
    from time import perf_counter
    requests=[]
    cancelled=asyncio.Event()
    async def handler(request):
        requests.append(request)
        if len(requests)==1:
            return httpx.Response(503,json={'error':{'code':503}})
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        start=perf_counter()
        with pytest.raises(DeltaError,match='время ожидания'):
            await OpenRouterLLMProvider('key','model',client,timeout_seconds=.45).respond([],[],{})
        assert perf_counter()-start < 1
    assert len(requests)==2 and cancelled.is_set()
