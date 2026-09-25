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
