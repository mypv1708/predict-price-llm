from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.api.deps import SessionServiceDep, SettingsDep
from app.schemas.session import (
    ChatHistory,
    MessageIn,
    MessageOut,
    SessionDetail,
    SessionStartOut,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionStartOut)
async def start_session(
    service: SessionServiceDep,
    settings: SettingsDep,
    file: Annotated[UploadFile | None, File()] = None,
) -> SessionStartOut:
    upload = await file.read(settings.max_upload_bytes + 1) if file else None
    return await service.start(upload)


@router.post("/{session_id}/messages", response_model=MessageOut)
async def send_message(session_id: str, body: MessageIn, service: SessionServiceDep) -> MessageOut:
    return await service.send_message(session_id, body.message)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, service: SessionServiceDep) -> SessionDetail:
    return await service.detail(session_id)


@router.get("/{session_id}/messages", response_model=ChatHistory)
async def get_session_messages(session_id: str, service: SessionServiceDep) -> ChatHistory:
    return await service.history(session_id)
