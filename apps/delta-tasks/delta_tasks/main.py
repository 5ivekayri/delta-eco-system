from fastapi import FastAPI

from delta_contracts.config import Settings
from delta_contracts.http import configure_app, lifespan
from .router import router


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Delta Tasks", version="0.1.0", lifespan=lifespan)
    configure_app(app, settings or Settings(service_name="delta-tasks"))
    app.include_router(router)
    return app
