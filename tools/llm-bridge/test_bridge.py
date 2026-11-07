import asyncio
from unittest.mock import AsyncMock
import httpx
import pytest
import bridge


CONFIG = dict(mode='auto',cloud_timeout=.01,cooldown=30,local_timeout=1,idle_seconds=0,core_health='http://core/health')
PAYLOAD = {'messages':[{'role':'user','content':'Hello'}]}
REPLY = {'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'OK'}}]}


def make():
    runtime = type('Runtime', (), {'stop':AsyncMock(), 'start':AsyncMock(), 'process':None})()
    obj = bridge.Bridge(dict(CONFIG), 'not-a-real-key', client=AsyncMock(), runtime=runtime)
    obj.cloud = AsyncMock(return_value=REPLY)
    obj.local = AsyncMock(return_value=REPLY)
    return obj


@pytest.mark.asyncio
async def test_cloud_success_does_not_load_local():
    obj = make()
    assert await obj.respond(PAYLOAD) == REPLY
    obj.local.assert_not_called()
    assert obj.active == 0


@pytest.mark.asyncio
async def test_failure_falls_back_once_and_opens_cooldown():
    obj = make(); obj.cloud.side_effect = TimeoutError()
    await obj.respond(PAYLOAD); await obj.respond(PAYLOAD)
    assert obj.cloud.call_count == 1
    assert obj.local.call_count == 2
    assert obj.last_backend == 'local'


@pytest.mark.asyncio
async def test_explicit_cloud_never_falls_back():
    obj=make(); obj.mode='openrouter'; obj.cloud.side_effect=TimeoutError()
    with pytest.raises(bridge.BackendFailure): await obj.respond(PAYLOAD)
    obj.local.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_does_not_trigger_fallback():
    obj=make(); obj.cloud.side_effect=asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError): await obj.respond(PAYLOAD)
    obj.local.assert_not_called()
    assert obj.active == 0


@pytest.mark.asyncio
async def test_switch_mode_unloads_model_and_close_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge,'ROOT',tmp_path)
    obj=make(); await obj.set_mode('openrouter')
    obj.runtime.stop.assert_awaited_once()
    await obj.close()
    assert obj.runtime.stop.call_count == 2
    obj.client.aclose.assert_awaited_once()
    with pytest.raises(bridge.BackendFailure): await obj.respond(PAYLOAD)


@pytest.mark.asyncio
async def test_wall_clock_deadline_on_cloud():
    obj=make()
    async def slow(*args, **kwargs):
        await asyncio.sleep(1)
    obj.client.post=slow
    with pytest.raises(TimeoutError): await bridge.Bridge.cloud(obj,PAYLOAD)


def test_tool_name_and_arguments_validated():
    payload={'tools':[{'function':{'name':'devices__open_app','parameters':{'type':'object','required':['app_name'],
             'properties':{'app_name':{'type':'string'}},'additionalProperties':False}}}]}
    call={'id':'1','type':'function','function':{'name':'devices__open_app','arguments':'{"app_name":"vscode"}'}}
    reply={'choices':[{'finish_reason':'tool_calls','message':{'content':None,'tool_calls':[call]}}]}
    assert bridge.validate_reply(reply,payload) == reply
    call['function']['arguments']='{"command":"rm -rf /"}'
    with pytest.raises(bridge.BackendFailure):bridge.validate_reply(reply,payload)
    call['function']['name']='shell'
    with pytest.raises(bridge.BackendFailure):bridge.validate_reply(reply,payload)


@pytest.mark.asyncio
async def test_unhealthy_core_releases_model(monkeypatch):
    obj=make(); obj.client.get.return_value=httpx.Response(503)
    original=asyncio.sleep
    async def fast(seconds): await original(.001)
    monkeypatch.setattr(bridge.asyncio,'sleep',fast)
    task=asyncio.create_task(obj.monitor())
    await original(.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert not obj.core_ready
    assert obj.runtime.stop.call_count >= 1


@pytest.mark.asyncio
async def test_images_use_vision_only_and_strip_tools():
    obj=make();obj.config['vision_model']='test-vision'
    obj.client.post.return_value=httpx.Response(200,json=REPLY,request=httpx.Request('POST','https://example.test'))
    payload={'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,AAAA'}}]}],
             'tools':[{'function':{'name':'shell'}}],'tool_choice':'auto'}
    assert await obj.respond(payload)==REPLY
    posted=obj.client.post.call_args.kwargs['json']
    assert posted['model']=='test-vision' and 'tools' not in posted and 'tool_choice' not in posted
    obj.cloud.assert_not_called();obj.local.assert_not_called()
    obj.mode='local'
    with pytest.raises(bridge.BackendFailure):await obj.respond(payload)
    assert obj.client.post.call_count==1
    obj.mode='auto';obj.client.post.side_effect=TimeoutError()
    with pytest.raises(TimeoutError):await obj.respond(payload)
    obj.local.assert_not_called()
    assert obj.active==0
