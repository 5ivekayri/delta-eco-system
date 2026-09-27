import httpx
from delta_core.services.registry import ServiceRegistry
from delta_contracts.tasks import task_manifest


async def test_manifest_discovery_health_transitions_and_disabled():
    healthy=True
    def handler(request):
        if request.url.path.endswith('manifest'):
            return httpx.Response(200,json=task_manifest())
        return httpx.Response(200 if healthy else 503,json={'status':'ok' if healthy else 'offline'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        registry=ServiceRegistry([{'service_id':'delta-tasks','base_url':'http://tasks'}],client)
        await registry.refresh()
        assert registry.get('delta-tasks').status=='online'
        assert len(registry.available_tools())==6
        healthy=False
        await registry.refresh()
        assert registry.get('delta-tasks').status=='offline'
        assert not registry.available_tools()
        registry.get('delta-tasks').enabled=False
        await registry.refresh()
        assert registry.get('delta-tasks').status=='disabled'


async def test_invalid_health_and_recovery_hide_unavailable_tools():
    health=[]
    def handler(request):
        return httpx.Response(200,json=task_manifest() if request.url.path.endswith('manifest') else health)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        registry=ServiceRegistry([{'service_id':'delta-tasks','base_url':'http://tasks'}],client)
        await registry.refresh()
        assert registry.get('delta-tasks').status=='degraded'
        assert registry.get('delta-tasks').public()['available_tools']==[]
        health={'status':'ok'}
        await registry.refresh()
        assert len(registry.get('delta-tasks').public()['available_tools'])==6


async def test_activity_failure_does_not_break_health_checks(monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    def broken_session(*args,**kwargs):
        raise SQLAlchemyError('unavailable')
    monkeypatch.setattr('delta_core.services.registry.Session',broken_session)
    def handler(request):
        return httpx.Response(200,json=task_manifest() if request.url.path.endswith('manifest') else {'status':'ok'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        registry=ServiceRegistry([{'service_id':'delta-tasks','base_url':'http://tasks'}],client,engine=object())
        await registry.refresh()
        assert registry.get('delta-tasks').status=='online'
        await registry.refresh()
        assert registry.available_tools()
