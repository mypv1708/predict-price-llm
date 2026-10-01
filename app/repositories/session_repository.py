from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatSession, LlmMessage


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, session_id: str) -> ChatSession | None:
        return await self._db.get(ChatSession, session_id)

    def add(self, session: ChatSession) -> None:
        self._db.add(session)

    async def advance(
        self,
        session_id: str,
        *,
        expected_interaction_id: str,
        interaction_id: str,
        model: str,
    ) -> bool:
        updated = await self._db.scalar(
            update(ChatSession)
            .where(
                ChatSession.session_id == session_id,
                ChatSession.previous_interaction_id == expected_interaction_id,
            )
            .values(previous_interaction_id=interaction_id, model=model)
            .returning(ChatSession.session_id)
            .execution_options(synchronize_session=False)
        )
        return updated is not None

    def add_message(self, message: LlmMessage) -> None:
        self._db.add(message)

    async def list_messages(self, session_id: str) -> Sequence[LlmMessage]:
        result = await self._db.scalars(
            select(LlmMessage).where(LlmMessage.session_id == session_id).order_by(LlmMessage.id)
        )
        return result.all()
