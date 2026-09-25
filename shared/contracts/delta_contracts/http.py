import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text

from .config import Settings
from .errors import register_errors


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        app.state.engine.dispose()


def configure_app(app: FastAPI, settings: Settings) -> None:
    register_errors(app)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    app.state.engine = engine
    app.state.settings = settings
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(settings.service_name)

    @app.middleware("http")
    async def authenticate_and_log(request: Request, call_next):
        request_id = str(uuid4())
        start = time.monotonic()
        if request.url.path.startswith("/api/"):
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied, f"Bearer {settings.delta_token}"):
                return JSONResponse(status_code=401, content={
                    "success": False, "error_code": "UNAUTHORIZED",
                    "message": "A valid development token is required",
                })
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(json.dumps({
            "request_id": request_id, "service_id": settings.service_name,
            "method": request.method, "path": request.url.path,
            "duration_ms": round((time.monotonic() - start) * 1000),
            "success": response.status_code < 400,
        }))
        return response

    @app.get("/health")
    def health():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={
                "status": "degraded", "service": settings.service_name,
                "error_code": "DATABASE_UNAVAILABLE",
            })
        return {"status": "ok", "service": settings.service_name, "version": "0.1.0"}
