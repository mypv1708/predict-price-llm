"""FastAPI sessions that keep Gemini state with previous_interaction_id."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, sessions
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.limits import BodySizeLimitMiddleware
from app.core.logging import configure_logging
from app.core.security import require_api_token
from app.db.session import create_engine, create_session_factory
from app.services.gemini import GeminiClient

MULTIPART_OVERHEAD_BYTES = 64 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings)
    async with engine.connect():
        pass
    http = httpx.AsyncClient()
    app.state.session_factory = create_session_factory(engine)
    app.state.gemini = GeminiClient(http, settings)
    try:
        yield
    finally:
        await http.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title="Price Predict", lifespan=lifespan)
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES,
    )
    # Added last so it wraps the size limit and early 413s still carry CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["null"],
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.include_router(health.router)
    app.include_router(sessions.router, dependencies=[Depends(require_api_token)])
    return app


app = create_app()
