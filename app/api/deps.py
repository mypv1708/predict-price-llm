from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.services.gemini import GeminiClient
from app.services.session_service import SessionService


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as db:
        yield db


def get_gemini(request: Request) -> GeminiClient:
    return request.app.state.gemini


DbSession = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
GeminiDep = Annotated[GeminiClient, Depends(get_gemini)]


def get_session_service(db: DbSession, gemini: GeminiDep, settings: SettingsDep) -> SessionService:
    return SessionService(db, gemini, settings)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
