from __future__ import annotations

import json
import re

from app.schemas.session import PriceHit


def locate_signal(message: str, signal: str, start: int = 0) -> tuple[int, int] | None:
    index = message.find(signal, start)
    if index >= 0:
        return index, index + len(signal)

    # The model often collapses line breaks or changes case when it quotes the signal back.
    tokens = signal.split()
    if not tokens:
        return None
    pattern = re.compile(r"\s+".join(re.escape(token) for token in tokens), re.IGNORECASE)
    match = pattern.search(message, start)
    return match.span() if match else None


def parse_llm_json(reply: str) -> dict:
    text = reply.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def price_hits(message: str, reply: str) -> list[PriceHit]:
    data = parse_llm_json(reply)
    prices = data.get("prices") or []
    signals = data.get("signals") or []
    if not isinstance(prices, list):
        return []
    if not isinstance(signals, list):
        signals = []

    hits: list[PriceHit] = []
    # A signal repeated for several prices maps to its next occurrence, not the first one again.
    resume_at: dict[str, int] = {}
    for index, price in enumerate(prices):
        signal = signals[index] if index < len(signals) else None
        signal_text = signal if isinstance(signal, str) and signal.strip() else None
        span = None
        if signal_text:
            span = locate_signal(message, signal_text, resume_at.get(signal_text, 0))
            if span is None and signal_text in resume_at:
                span = locate_signal(message, signal_text)
            if span:
                resume_at[signal_text] = span[1]
        hits.append(
            PriceHit(
                price=str(price),
                signal=signal_text,
                start=span[0] if span else None,
                end=span[1] if span else None,
            )
        )
    return hits
