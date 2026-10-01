from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.logging import logger
from app.models import ChatSession, LlmMessage
from app.repositories.session_repository import SessionRepository
from app.schemas.session import (
    ChatHistory,
    ChatMessage,
    MessageOut,
    PricePosition,
    SessionDetail,
    SessionStartOut,
    StoredTurn,
)
from app.services.gemini import GeminiClient
from app.services.price_extraction import price_hits
from app.services.prompt import load_dataset, load_system_prompt, opening_input


class SessionService:
    def __init__(self, db: AsyncSession, gemini: GeminiClient, settings: Settings) -> None:
        self._db = db
        self._gemini = gemini
        self._settings = settings
        self._sessions = SessionRepository(db)

    async def start(self, upload: bytes | None) -> SessionStartOut:
        csv_text = load_dataset(self._settings, upload)
        system_prompt = load_system_prompt(self._settings)
        interaction = await self._gemini.create_interaction(
            opening_input(system_prompt, csv_text),
            system_prompt,
        )

        session = ChatSession(
            session_id=uuid.uuid4().hex,
            previous_interaction_id=interaction.id,
            system_prompt=system_prompt,
            model=interaction.model,
        )
        self._sessions.add(session)
        await self._db.commit()

        logger.info(
            "session created id=%s model=%s chars=%s",
            session.session_id,
            interaction.model,
            len(csv_text),
        )
        return SessionStartOut(
            session_id=session.session_id,
            previous_interaction_id=session.previous_interaction_id,
            system_prompt=session.system_prompt,
            reply=interaction.reply,
        )

    async def send_message(self, session_id: str, message: str) -> MessageOut:
        if not message.strip():
            raise BadRequestError("Message is empty")
        if len(message) > self._settings.max_message_chars:
            raise BadRequestError(f"Message exceeds {self._settings.max_message_chars} characters")

        session = await self._require(session_id)
        expected_interaction_id = session.previous_interaction_id
        # Release the connection before the slow Gemini call so the pool stays free.
        await self._db.commit()

        interaction = await self._gemini.create_interaction(
            message,
            session.system_prompt,
            expected_interaction_id,
            session.model,
        )

        advanced = await self._sessions.advance(
            session_id,
            expected_interaction_id=expected_interaction_id,
            interaction_id=interaction.id,
            model=interaction.model,
        )
        if not advanced:
            await self._db.rollback()
            raise ConflictError("Another message in this session finished first. Send it again.")
        self._sessions.add_message(
            LlmMessage(
                session_id=session_id,
                request_text=message,
                response_text=interaction.reply,
            )
        )
        await self._db.commit()

        logger.info(
            "llm exchange session=%s model=%s request_chars=%s response_chars=%s",
            session_id,
            interaction.model,
            len(message),
            len(interaction.reply),
        )
        return MessageOut(
            session_id=session_id,
            results=[
                PricePosition(price=hit.price, start=hit.start, end=hit.end)
                for hit in price_hits(message, interaction.reply)
            ],
        )

    async def detail(self, session_id: str) -> SessionDetail:
        session = await self._require(session_id)
        messages = await self._sessions.list_messages(session_id)
        return SessionDetail(
            session_id=session.session_id,
            previous_interaction_id=session.previous_interaction_id,
            system_prompt=session.system_prompt,
            model=session.model,
            created_at=session.created_at,
            messages=[
                StoredTurn(
                    id=row.id,
                    request_text=row.request_text,
                    response_text=row.response_text,
                    created_at=row.created_at,
                    results=price_hits(row.request_text, row.response_text),
                )
                for row in messages
            ],
        )

    async def history(self, session_id: str) -> ChatHistory:
        session = await self._require(session_id)
        messages = [
            ChatMessage(role="system", content=session.system_prompt, created_at=session.created_at)
        ]
        for row in await self._sessions.list_messages(session_id):
            messages.append(
                ChatMessage(role="user", content=row.request_text, created_at=row.created_at)
            )
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=row.response_text,
                    created_at=row.created_at,
                    results=price_hits(row.request_text, row.response_text),
                )
            )
        return ChatHistory(session_id=session.session_id, messages=messages)

    async def _require(self, session_id: str) -> ChatSession:
        session = await self._sessions.get(session_id)
        if session is None:
            raise NotFoundError("Session was not found")
        return session
