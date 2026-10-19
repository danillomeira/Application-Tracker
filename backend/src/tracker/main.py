"""Aplicação FastAPI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tracker.api.router import api_router
from tracker.api.ws import router as ws_router
from tracker.core.config import get_settings
from tracker.core.db import dispose_engine
from tracker.core.logging import configure_logging, request_id_var

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    stop = asyncio.Event()
    poller: asyncio.Task[None] | None = None
    if get_settings().telegram_polling():
        from tracker.modules.notifications.telegram_bot import poll_updates

        poller = asyncio.create_task(poll_updates(stop))
    yield
    stop.set()
    if poller is not None:
        poller.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poller
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Application Tracker API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if s.app_env != "prod" else None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_origin_regex=r"^(chrome|moz)-extension://.*$",  # extensão do assistente
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "same-origin"
        response.headers["x-frame-options"] = "SAMEORIGIN"  # o dashboard mostra o PDF do CV num iframe (via proxy, mesma origem)
        if s.app_env == "prod":
            response.headers["strict-transport-security"] = "max-age=31536000"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": str(exc.status_code), "message": exc.detail}},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "dados inválidos",
                    "details": {
                        "errors": [
                            {"loc": list(e.get("loc", [])), "msg": str(e.get("msg")), "type": e.get("type")} for e in exc.errors()
                        ]
                    },
                }
            },
            status_code=422,
        )

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router)
    return app


app = create_app()
