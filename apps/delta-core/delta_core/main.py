import asyncio
import httpx
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI

from delta_contracts.config import Settings
from delta_contracts.http import configure_app
from delta_core.devices.manager import DeviceManager
from delta_core.devices.router import router as devices_router
from delta_core.services.registry import ServiceRegistry
from delta_core.services.router import router as services_router
from delta_core.workspaces.router import router as workspaces_router
from delta_core.workspaces.service import WorkspaceService
from delta_core.tools.registry import ToolRegistry
from delta_core.tools.builtins import register_builtins
from delta_core.llm.mock import MockLLMProvider
from delta_core.llm.openrouter import OpenRouterLLMProvider
from delta_core.assistant.service import AssistantService
from delta_core.assistant.router import router as assistant_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.devices.reset_online()
    monitor = asyncio.create_task(app.state.devices.monitor())
    service_monitor = asyncio.create_task(app.state.services.monitor())
    try:
        yield
    finally:
        monitor.cancel()
        service_monitor.cancel()
        with suppress(asyncio.CancelledError):
            await monitor
        with suppress(asyncio.CancelledError):
            await service_monitor
        await app.state.http.aclose()
        app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Delta Core", version="0.1.0", lifespan=lifespan)
    configure_app(app, settings or Settings())
    app.state.devices = DeviceManager(app.state.engine, app.state.settings)
    app.include_router(devices_router)
    app.state.http = httpx.AsyncClient(timeout=5, headers={'Authorization':f'Bearer {app.state.settings.delta_token}'})
    configs = app.state.settings.service_configs
    app.state.services = ServiceRegistry(configs if configs is not None else [
        {'service_id':'delta-tasks', 'base_url':app.state.settings.tasks_url}
    ], app.state.http, app.state.engine)
    app.include_router(services_router)
    app.state.workspaces=WorkspaceService(app.state.engine,app.state.devices)
    app.include_router(workspaces_router)
    app.state.tools=ToolRegistry(app.state.services)
    register_builtins(app)
    settings=app.state.settings
    if settings.llm_provider not in {'mock','openrouter'}:
        raise ValueError('LLM_PROVIDER must be mock or openrouter')
    provider=MockLLMProvider() if settings.llm_provider=='mock' else OpenRouterLLMProvider(settings.openrouter_api_key,settings.openrouter_model)
    app.state.assistant=AssistantService(app.state.engine,app.state.tools,provider)
    app.include_router(assistant_router)
    return app
