"""DeepSeek API adapter used by the governed DoraDB agent."""

from __future__ import annotations

import logging
import ssl
from typing import Any

import httpx
import truststore

from .config import Settings

logger = logging.getLogger(__name__)


class GenerativeAIClient:
    """Call DeepSeek's OpenAI-compatible chat-completions endpoint safely."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_model: str | None = None
        self.http_client: httpx.Client | None = None
        if settings.deepseek_configured:
            ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.http_client = httpx.Client(
                base_url=settings.deepseek_base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                verify=ssl_context,
                timeout=settings.deepseek_timeout_seconds,
            )

    @property
    def enabled(self) -> bool:
        return self.http_client is not None

    @property
    def source(self) -> str:
        return f"deepseek:{self.last_model or self.settings.deepseek_model}"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str | None:
        """Return model text and fail closed when the provider is unavailable."""

        if self.http_client is None:
            return None

        selected_temperature = (
            self.settings.deepseek_planner_temperature
            if temperature is None and json_mode
            else (
                self.settings.deepseek_response_temperature
                if temperature is None
                else temperature
            )
        )
        payload: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": selected_temperature,
            "max_tokens": (
                self.settings.deepseek_planner_max_tokens
                if json_mode
                else self.settings.deepseek_response_max_tokens
            ),
            "stream": False,
            "thinking": {
                "type": (
                    "enabled"
                    if self.settings.deepseek_thinking_enabled
                    else "disabled"
                )
            },
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = self.http_client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            message = choices[0].get("message") or {}
            content = message.get("content")
            self.last_model = str(data.get("model") or self.settings.deepseek_model)
            return str(content).strip() if content else None
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "DeepSeek model %s unavailable: %s",
                self.settings.deepseek_model,
                exc,
            )
            return None
