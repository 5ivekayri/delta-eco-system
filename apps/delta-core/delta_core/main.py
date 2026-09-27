import asyncio
import httpx
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI

from delta_contracts.config import Settings
from delta_contracts.http import configure_app
from delta_core.activity.router import router as activity_router
from delta_core.devices.manager import DeviceManager
from delta_core.devices.router import router as devices_router
from delta_core.services.registry import ServiceRegistry
from delta_core.services.router import router as services_router
from delta_core.workspaces.router import router as workspaces_router
from delta_core.workspaces.service import WorkspaceService
from delta_core.tools.registry import ToolRegistry
from delta_core.tools.builtins import register_builtins
from delta_core.iot.adapter import VirtualIoTAdapter
from delta_core.iot.router import router as iot_router
from delta_core.iot.tools import register_iot_tools
from delta_core.llm.mock import MockLLMProvider
from delta_core.llm.openrouter import OpenRouterLLMProvider
from delta_core.assistant.service import AssistantService
from delta_core.assistant.intents import LocalIntentRouter, RegistryTaskLookup
from delta_core.assistant.router import router as assistant_router
from delta_core.voice.router import router as voice_router
from delta_core.voice.stt import MockSTTProvider, WhisperSTTProvider
from delta_core.voice.tts import MockTTSProvider, PiperTTSProvider
from delta_core.voice.limits import VoiceUploadLimit


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app.state.stt.startup()
    if app.state.tts is not None and hasattr(app.state.tts, 'startup'):
        await app.state.tts.startup()
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
        await app.state.llm_http.aclose()
        app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Delta Core", version="0.1.0", lifespan=lifespan)
    configure_app(app, settings or Settings())
    app.state.devices = DeviceManager(app.state.engine, app.state.settings)
    app.include_router(devices_router)
    app.include_router(activity_router)
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
    app.state.iot = VirtualIoTAdapter(app.state.engine)
    register_iot_tools(app)
    app.include_router(iot_router)
    settings=app.state.settings
    if settings.llm_provider not in {'mock','openrouter'}:
        raise ValueError('LLM_PROVIDER must be mock or openrouter')
    # Dedicated pooled client: never forward Delta's internal bearer token to an LLM.
    app.state.llm_http = httpx.AsyncClient(timeout=60)
    if settings.llm_provider == 'mock':
        provider = router_provider = MockLLMProvider()
    else:
        provider = OpenRouterLLMProvider(settings.openrouter_api_key,
            settings.delta_assistant_model or settings.openrouter_model, app.state.llm_http)
        router_provider = OpenRouterLLMProvider(settings.openrouter_api_key,
            settings.delta_router_model or settings.openrouter_model, app.state.llm_http,
            router=True, max_tokens=settings.delta_router_max_tokens)
    app.state.assistant = AssistantService(app.state.engine, app.state.tools, provider, router_provider,
        local_router=LocalIntentRouter(RegistryTaskLookup(app.state.tools)),
        local_threshold=settings.delta_local_intent_threshold)
    if settings.tts_provider not in {'piper', 'mock', 'disabled'}:
        raise ValueError('TTS_PROVIDER must be piper, mock or disabled')
    app.state.tts = (PiperTTSProvider(settings.piper_model, settings.tts_max_chars, settings.tts_max_seconds)
                     if settings.tts_provider == 'piper' else MockTTSProvider() if settings.tts_provider == 'mock' else None)
    app.include_router(assistant_router)
    if settings.stt_provider not in {'mock', 'whisper'}:
        raise ValueError('STT_PROVIDER must be mock or whisper')
    app.state.stt = (MockSTTProvider(settings.mock_stt_transcript) if settings.stt_provider == 'mock'
                     else WhisperSTTProvider(settings.whisper_model, settings.whisper_cache_dir,
                                             settings.voice_max_seconds, settings.whisper_language))
    app.include_router(voice_router)
    app.add_middleware(VoiceUploadLimit, max_bytes=settings.voice_max_bytes + 64 * 1024)
    return app
