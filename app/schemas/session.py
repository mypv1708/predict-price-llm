from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PricePosition(BaseModel):
    price: str
    start: int | None = Field(
        default=None,
        description="Code point offset of the signal in the message. Null when it was not found.",
    )
    end: int | None = Field(
        default=None,
        description="Exclusive end offset, so message[start:end] is the signal.",
    )


class PriceHit(PricePosition):
    signal: str | None = None


class MessageIn(BaseModel):
    message: str = Field(
        min_length=1,
        examples=[
            "𝘿𝙄𝙉𝙂 𝘿𝙄𝙉𝙂 𝘿𝙀𝙎𝙄𝙂𝙉 • 𝙎𝙎𝟮𝟲\n\nSet áo trễ vai chân váy xếp ly xinh xĩu 💗\n\n• B310 SM"
        ],
    )


class SessionStartOut(BaseModel):
    session_id: str
    previous_interaction_id: str
    system_prompt: str
    reply: str


class MessageOut(BaseModel):
    session_id: str
    results: list[PricePosition]


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    previous_interaction_id: str
    system_prompt: str
    model: str
    created_at: datetime


class StoredTurn(BaseModel):
    id: int
    request_text: str
    response_text: str
    created_at: datetime
    results: list[PriceHit]


class SessionDetail(SessionOut):
    messages: list[StoredTurn]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    created_at: datetime
    results: list[PriceHit] | None = None


class ChatHistory(BaseModel):
    session_id: str
    messages: list[ChatMessage]
