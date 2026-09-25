from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class DeltaError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def register_errors(app: FastAPI) -> None:
    @app.exception_handler(DeltaError)
    async def domain_error(request: Request, exc: DeltaError):
        return JSONResponse(status_code=exc.status, content={
            "success": False, "error_code": exc.code, "message": exc.message,
        })

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic errors may contain raw input; return locations/messages only.
        return JSONResponse(status_code=422, content={
            "success": False, "error_code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "errors": [{"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors()],
        })

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={
            "success": False, "error_code": f"HTTP_{exc.status_code}",
            "message": str(exc.detail),
        }, headers=exc.headers)
