"""Configured generative-AI provider adapter used by the governed agent."""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass
from typing import Any

import httpx
import truststore
from google import genai
from google.genai import types

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderStatus:
    """Configuration and reachability information safe for the health API."""

    configured: bool
    available: bool
    detail: str | None = None


class GenerativeAIClient:
    """Call the configured AI provider without exposing secrets."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_model: str | None = None
        self.last_error: str | None = None
        self.client: genai.Client | None = None
        self.http_client: httpx.Client | None = None

        if settings.llm_provider == "google-ai-studio" and settings.gemini_configured:
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
        elif settings.llm_provider == "ollama" and settings.ollama_configured:
            self.http_client = httpx.Client(
                base_url=f"{settings.ollama_base_url.rstrip('/')}/",
                timeout=settings.ollama_timeout_seconds,
            )
        elif settings.llm_provider == "deepseek" and settings.deepseek_configured:
            ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.http_client = httpx.Client(
                base_url=f"{settings.deepseek_base_url.rstrip('/')}/",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=settings.deepseek_timeout_seconds,
                verify=ssl_context,
            )

    @property
    def enabled(self) -> bool:
        if self.settings.llm_provider in {"deepseek", "ollama"}:
            return self.http_client is not None
        return self.client is not None

    @property
    def source(self) -> str:
        return f"{self.settings.llm_provider}:{self.last_model or self.settings.llm_model}"

    @property
    def unavailable_message(self) -> str:
        if self.last_error:
            return self.last_error
        if self.settings.llm_provider == "ollama":
            return (
                f"The Ollama model '{self.settings.ollama_model}' is unavailable at "
                f"{self.settings.ollama_base_url}. Start Ollama and install the model, "
                "then try again. I did not substitute a fabricated answer."
            )
        if self.settings.llm_provider == "deepseek":
            return (
                f"The DeepSeek model '{self.settings.deepseek_model}' is unavailable. "
                "Check the API key, account balance, and provider status, then try "
                "again. I did not substitute a fabricated answer."
            )
        return (
            "The Google AI Studio model is unavailable right now or its free request "
            "quota has been exhausted. I did not substitute a template answer. Please "
            "try again when the free-model service is available."
        )

    def close(self) -> None:
        """Release the provider HTTP client when used for a short-lived check."""

        if self.http_client is not None:
            self.http_client.close()

    def check_availability(self) -> ProviderStatus:
        """Check provider configuration and lightweight reachability."""

        if not self.settings.llm_configured:
            if self.settings.llm_provider == "ollama":
                detail = "Configure OLLAMA_BASE_URL and OLLAMA_MODEL."
            elif self.settings.llm_provider == "deepseek":
                detail = (
                    "Configure DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, and "
                    "DEEPSEEK_MODEL."
                )
            else:
                detail = "GEMINI_API_KEY is required for generative responses."
            return ProviderStatus(configured=False, available=False, detail=detail)

        if self.settings.llm_provider == "google-ai-studio":
            return ProviderStatus(configured=True, available=True)

        if self.settings.llm_provider == "deepseek":
            return self._check_deepseek_availability()

        if self.http_client is None:
            return ProviderStatus(
                configured=False,
                available=False,
                detail="Configure OLLAMA_BASE_URL and OLLAMA_MODEL.",
            )
        try:
            response = self.http_client.get(
                "api/tags",
                timeout=min(5.0, self.settings.ollama_timeout_seconds),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Ollama tags response must be an object")
            models = {
                str(model.get(key, ""))
                for model in payload.get("models", [])
                if isinstance(model, dict)
                for key in ("name", "model")
                if model.get(key)
            }
            if self.settings.ollama_model not in models:
                return ProviderStatus(
                    configured=True,
                    available=False,
                    detail=(
                        f"Ollama is running, but model '{self.settings.ollama_model}' "
                        "is not installed."
                    ),
                )
            return ProviderStatus(configured=True, available=True)
        except httpx.TimeoutException:
            return ProviderStatus(
                configured=True,
                available=False,
                detail=f"Ollama timed out at {self.settings.ollama_base_url}.",
            )
        except (httpx.HTTPError, ValueError):
            return ProviderStatus(
                configured=True,
                available=False,
                detail=f"Ollama is not reachable at {self.settings.ollama_base_url}.",
            )

    def _check_deepseek_availability(self) -> ProviderStatus:
        if self.http_client is None:
            return ProviderStatus(
                configured=False,
                available=False,
                detail="Configure the DeepSeek API settings.",
            )
        try:
            response = self.http_client.get(
                "models",
                timeout=min(10.0, self.settings.deepseek_timeout_seconds),
            )
            if response.status_code in {401, 403}:
                return ProviderStatus(
                    configured=True,
                    available=False,
                    detail="DeepSeek rejected the configured API key.",
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("DeepSeek models response must be an object")
            models = {
                str(item.get("id", ""))
                for item in payload.get("data", [])
                if isinstance(item, dict)
            }
            if self.settings.deepseek_model not in models:
                return ProviderStatus(
                    configured=True,
                    available=False,
                    detail=(
                        f"DeepSeek model '{self.settings.deepseek_model}' is not "
                        "available to this account."
                    ),
                )
            return ProviderStatus(configured=True, available=True)
        except httpx.TimeoutException:
            return ProviderStatus(
                configured=True,
                available=False,
                detail="DeepSeek timed out during the availability check.",
            )
        except (httpx.HTTPError, ValueError, TypeError):
            return ProviderStatus(
                configured=True,
                available=False,
                detail="DeepSeek is not reachable right now.",
            )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str | None:
        """Return provider text or ``None`` with a safe, user-facing error."""

        self.last_error = None
        if not self.enabled:
            self.last_error = self.unavailable_message
            return None
        if self.settings.llm_provider == "ollama":
            return self._complete_ollama(
                system_prompt,
                user_prompt,
                json_mode=json_mode,
                temperature=temperature,
            )
        if self.settings.llm_provider == "deepseek":
            return self._complete_deepseek(
                system_prompt,
                user_prompt,
                json_mode=json_mode,
                temperature=temperature,
            )
        return self._complete_google(
            system_prompt,
            user_prompt,
            json_mode=json_mode,
            temperature=temperature,
        )

    def _complete_google(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool,
        temperature: float | None,
    ) -> str | None:
        if self.client is None:
            return None
        try:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=(
                    self.settings.llm_planner_temperature
                    if temperature is None and json_mode
                    else (
                        self.settings.llm_response_temperature
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
            self.last_error = self.unavailable_message
            return None

    def _complete_deepseek(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool,
        temperature: float | None,
    ) -> str | None:
        if self.http_client is None:
            return None
        request: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": (
                self.settings.llm_planner_temperature
                if temperature is None and json_mode
                else (
                    self.settings.llm_response_temperature
                    if temperature is None
                    else temperature
                )
            ),
            "max_tokens": (
                self.settings.deepseek_planner_max_tokens
                if json_mode
                else self.settings.deepseek_response_max_tokens
            ),
            "thinking": {
                "type": (
                    "enabled"
                    if self.settings.deepseek_thinking_enabled
                    else "disabled"
                )
            },
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        try:
            response = self.http_client.post("chat/completions", json=request)
            if response.status_code in {401, 403}:
                self.last_error = (
                    "DeepSeek rejected the configured API key. Update "
                    "DEEPSEEK_API_KEY and try again."
                )
                return None
            if response.status_code == 402:
                self.last_error = (
                    "The DeepSeek account has insufficient balance. Add credit and "
                    "try again."
                )
                return None
            if response.status_code == 429:
                self.last_error = (
                    "DeepSeek is rate-limiting requests right now. Please try again "
                    "shortly."
                )
                return None
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("DeepSeek chat response must be an object")
            choices = payload.get("choices", [])
            if not isinstance(choices, list) or not choices:
                raise ValueError("DeepSeek chat response has no choices")
            message = choices[0].get("message", {})
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                self.last_error = (
                    "DeepSeek returned an empty response. I did not substitute a "
                    "fabricated answer."
                )
                return None
            self.last_model = self.settings.deepseek_model
            return content.strip()
        except httpx.TimeoutException:
            self.last_error = (
                f"DeepSeek timed out while using model "
                f"'{self.settings.deepseek_model}'. Please try again."
            )
        except httpx.ConnectError:
            self.last_error = (
                f"DeepSeek is not reachable at {self.settings.deepseek_base_url}. "
                "Please try again."
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning(
                "DeepSeek model %s unavailable: %s",
                self.settings.deepseek_model,
                exc,
            )
            self.last_error = (
                "DeepSeek could not complete the request. Check the provider status "
                "and model configuration, then try again."
            )
        return None

    def _complete_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool,
        temperature: float | None,
    ) -> str | None:
        if self.http_client is None:
            return None
        request: dict[str, Any] = {
            "model": self.settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": (
                    self.settings.llm_planner_temperature
                    if temperature is None and json_mode
                    else (
                        self.settings.llm_response_temperature
                        if temperature is None
                        else temperature
                    )
                )
            },
        }
        if json_mode:
            request["format"] = "json"
        try:
            response = self.http_client.post("api/chat", json=request)
            if response.status_code == 404:
                self.last_error = (
                    f"The Ollama model '{self.settings.ollama_model}' is not installed. "
                    f"Run 'ollama pull {self.settings.ollama_model}' and try again. "
                    "I did not substitute a fabricated answer."
                )
                return None
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Ollama chat response must be an object")
            message = payload.get("message", {})
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                self.last_error = (
                    "Ollama returned an empty response. I did not substitute a "
                    "fabricated answer."
                )
                return None
            self.last_model = self.settings.ollama_model
            return content.strip()
        except httpx.TimeoutException:
            self.last_error = (
                f"Ollama timed out while using model '{self.settings.ollama_model}'. "
                "Please try again. I did not substitute a fabricated answer."
            )
        except httpx.ConnectError:
            self.last_error = (
                f"Ollama is not reachable at {self.settings.ollama_base_url}. Start "
                "Ollama and try again. I did not substitute a fabricated answer."
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Ollama model %s unavailable: %s",
                self.settings.ollama_model,
                exc,
            )
            self.last_error = (
                "Ollama could not complete the request. Check the local server and "
                "model, then try again. I did not substitute a fabricated answer."
            )
        return None
