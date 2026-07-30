"""Google AI Studio Gemini adapter used by the governed agent."""

from __future__ import annotations

import logging
import ssl

import httpx
import truststore
from google import genai
from google.genai import types

from .config import Settings

logger = logging.getLogger(__name__)


class GenerativeAIClient:
    """Call the configured Gemini model without exposing credentials."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_model: str | None = None
        self.client: genai.Client | None = None
        self.http_client: httpx.Client | None = None
        if settings.gemini_configured:
            ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.http_client = httpx.Client(
                verify=ssl_context,
                timeout=settings.gemini_timeout_seconds,
            )
            self.client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=int(settings.gemini_timeout_seconds * 1000),
                    httpx_client=self.http_client,
                ),
            )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @property
    def source(self) -> str:
        return f"google-ai-studio:{self.last_model or self.settings.gemini_model}"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str | None:
        """Return model text, falling back safely on provider errors."""

        if self.client is None:
            return None
        try:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=(
                    self.settings.gemini_planner_temperature
                    if temperature is None and json_mode
                    else (
                        self.settings.gemini_response_temperature
                        if temperature is None
                        else temperature
                    )
                ),
                response_mime_type="application/json" if json_mode else "text/plain",
            )
            response = self.client.models.generate_content(
                model=self.settings.gemini_model,
                contents=user_prompt,
                config=config,
            )
            self.last_model = self.settings.gemini_model
            return (response.text or "").strip() or None
        except Exception as exc:
            logger.warning(
                "Google AI Studio model %s unavailable: %s",
                self.settings.gemini_model,
                exc,
            )
            return None
