from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.errors import (
    AppError,
    UpstreamError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from app.core.logging import logger

CONNECT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class Interaction:
    id: str
    model: str
    reply: str


def reply_text(payload: dict) -> str:
    parts: list[str] = []
    for step in payload.get("steps") or []:
        if step.get("type") != "model_output":
            continue
        for block in step.get("content") or []:
            text = block.get("text")
            if block.get("type") == "text" and text:
                parts.append(text)
    return "\n".join(parts).strip()


def error_details(response: httpx.Response) -> tuple[str, str]:
    message = response.text
    code = ""
    try:
        error = response.json().get("error", {})
        code = str(error.get("code") or "")
        message = str(error.get("message") or message)
    except (json.JSONDecodeError, AttributeError):
        pass
    return code, message


def is_retryable(status: int, code: str, message: str) -> bool:
    if status in {429, 500, 503}:
        return True
    text = f"{code} {message}".lower()
    return "unavailable" in text or "high demand" in text


class GeminiClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    def model_candidates(self, preferred: str | None) -> list[str]:
        names = [preferred or self._settings.gemini_api_model, *self._settings.fallback_models]
        return list(dict.fromkeys(name for name in names if name))

    async def create_interaction(
        self,
        text: str,
        system_prompt: str,
        previous_interaction_id: str | None = None,
        model: str | None = None,
    ) -> Interaction:
        # Gemini keeps conversation state per model, so a later turn cannot switch models.
        opening = previous_interaction_id is None
        models = [model] if model and not opening else self.model_candidates(model)
        headers = {
            "x-goog-api-key": self._settings.gemini_api_key,
            "Content-Type": "application/json",
            "Api-Revision": self._settings.gemini_api_revision,
        }
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._settings.gemini_total_timeout_seconds
        last_error: AppError = UpstreamUnavailableError("Gemini did not respond")

        for name in models:
            body: dict = {"model": name, "input": text, "system_instruction": system_prompt}
            if previous_interaction_id:
                body["previous_interaction_id"] = previous_interaction_id

            for attempt in range(1, self._settings.gemini_attempts + 1):
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise self._deadline_error()
                request_timeout = min(self._settings.gemini_request_timeout_seconds, remaining)
                try:
                    # httpx timeouts apply per read, so a slow trickle needs a wall-clock cap too.
                    async with asyncio.timeout(request_timeout):
                        response = await self._http.post(
                            self._settings.interactions_url,
                            headers=headers,
                            json=body,
                            timeout=httpx.Timeout(
                                request_timeout,
                                connect=min(CONNECT_TIMEOUT_SECONDS, request_timeout),
                            ),
                        )
                except (TimeoutError, httpx.TimeoutException):
                    logger.warning(
                        "gemini model=%s attempt=%s timed out after %.1fs",
                        name,
                        attempt,
                        request_timeout,
                    )
                    last_error = UpstreamUnavailableError(f"{name} did not answer in time")
                except httpx.TransportError:
                    logger.warning("gemini model=%s attempt=%s transport error", name, attempt)
                    last_error = UpstreamUnavailableError("Gemini could not be reached")
                else:
                    if response.status_code < 400:
                        return self._interaction(response, name)
                    code, message = error_details(response)
                    logger.warning(
                        "gemini model=%s attempt=%s status=%s code=%s",
                        name,
                        attempt,
                        response.status_code,
                        code or "none",
                    )
                    if not is_retryable(response.status_code, code, message):
                        last_error = UpstreamError(message)
                        break
                    last_error = UpstreamUnavailableError(message)

                if attempt < self._settings.gemini_attempts:
                    delay = self._settings.gemini_retry_delay_seconds
                    if deadline - loop.time() <= delay:
                        raise self._deadline_error()
                    await asyncio.sleep(delay)

            if not opening:
                break
            logger.warning("gemini moving on from model=%s", name)

        if deadline - loop.time() <= 0:
            raise self._deadline_error()
        raise last_error

    def _deadline_error(self) -> UpstreamTimeoutError:
        logger.warning(
            "gemini gave up after %.0fs total", self._settings.gemini_total_timeout_seconds
        )
        return UpstreamTimeoutError(
            "Gemini is overloaded and did not answer within "
            f"{self._settings.gemini_total_timeout_seconds:g}s. Try again later."
        )

    @staticmethod
    def _interaction(response: httpx.Response, model: str) -> Interaction:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise UpstreamError("Gemini returned a body that is not JSON") from exc
        if not isinstance(payload, dict):
            raise UpstreamError("Gemini returned an unexpected body")
        interaction_id = payload.get("id")
        if not interaction_id:
            raise UpstreamError("Gemini did not return an interaction id")
        logger.info("gemini model=%s status=%s", model, response.status_code)
        return Interaction(id=interaction_id, model=model, reply=reply_text(payload))
