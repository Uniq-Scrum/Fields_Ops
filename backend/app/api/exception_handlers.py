"""
Centralized FastAPI exception handling.

Ensures no route can accidentally leak a raw SQLAlchemy/psycopg2 exception,
stack trace, or other internal detail to an API consumer: `AppException`
subclasses are translated to their declared status code and message, and
anything unexpected is logged with its full traceback server-side but
returned to the client as a generic 500.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
