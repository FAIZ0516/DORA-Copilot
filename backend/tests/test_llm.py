import json

import httpx

from backend.config import Settings
from backend.llm import GenerativeAIClient


def ollama_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "llm_provider": "ollama",
        "ollama_base_url": "http://127.0.0.1:11434",
        "ollama_model": "qwen3:4b",
        "ollama_timeout_seconds": 10,
    }
    values.update(overrides)
    return Settings(**values)


def deepseek_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "llm_provider": "deepseek",
        "deepseek_api_key": "test-key",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-v4-flash",
        "deepseek_timeout_seconds": 10,
        "deepseek_thinking_enabled": True,
        "deepseek_planner_max_tokens": 1600,
        "deepseek_response_max_tokens": 3000,
    }
    values.update(overrides)
    return Settings(**values)


def replace_http_client(
    client: GenerativeAIClient,
    handler: httpx.MockTransport,
    *,
    base_url: str = "http://127.0.0.1:11434/",
    headers: dict[str, str] | None = None,
) -> None:
    if client.http_client is not None:
        client.http_client.close()
    client.http_client = httpx.Client(
        base_url=base_url,
        headers=headers,
        transport=handler,
        timeout=10,
    )


def test_google_ai_studio_remains_the_default_provider() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "google-ai-studio"
    assert settings.llm_model == settings.gemini_model
    assert settings.llm_source == f"google-ai-studio:{settings.gemini_model}"


def test_deepseek_configuration_drives_common_provider_properties() -> None:
    settings = deepseek_settings()

    assert settings.llm_configured is True
    assert settings.llm_model == "deepseek-v4-flash"
    assert settings.llm_source == "deepseek:deepseek-v4-flash"
    assert settings.llm_planner_temperature == 0
    assert settings.llm_response_temperature == 0.3


def test_deepseek_chat_sends_thinking_json_and_token_controls() -> None:
    captured: dict[str, object] = {}
    authorization = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authorization
        authorization = request.headers.get("Authorization", "")
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "reasoning_content": "private reasoning",
                            "content": '{"mode":"conversation"}',
                        }
                    }
                ],
            },
        )

    client = GenerativeAIClient(deepseek_settings())
    replace_http_client(
        client,
        httpx.MockTransport(handler),
        base_url="https://api.deepseek.com/",
        headers={"Authorization": "Bearer test-key"},
    )

    result = client.complete(
        "Return JSON only.",
        "Plan this safe request.",
        json_mode=True,
        temperature=0,
    )

    assert result == '{"mode":"conversation"}'
    assert authorization == "Bearer test-key"
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["stream"] is False
    assert captured["messages"] == [
        {"role": "system", "content": "Return JSON only."},
        {"role": "user", "content": "Plan this safe request."},
    ]
    assert captured["temperature"] == 0
    assert captured["max_tokens"] == 1600
    assert captured["thinking"] == {"type": "enabled"}
    assert captured["response_format"] == {"type": "json_object"}
    assert client.source == "deepseek:deepseek-v4-flash"


def test_deepseek_authentication_error_is_safe_and_actionable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    client = GenerativeAIClient(deepseek_settings())
    replace_http_client(
        client,
        httpx.MockTransport(handler),
        base_url="https://api.deepseek.com/",
    )

    assert client.complete("system", "question") is None
    assert "rejected the configured API key" in client.unavailable_message
    assert "test-key" not in client.unavailable_message


def test_deepseek_health_confirms_selected_model() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "deepseek-v4-flash"}]},
        )

    client = GenerativeAIClient(deepseek_settings())
    replace_http_client(
        client,
        httpx.MockTransport(handler),
        base_url="https://api.deepseek.com/",
    )

    status = client.check_availability()

    assert status.configured is True
    assert status.available is True
    assert status.detail is None


def test_ollama_chat_sends_system_user_and_json_mode() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": '{"mode":"data"}'}},
        )

    client = GenerativeAIClient(ollama_settings())
    replace_http_client(client, httpx.MockTransport(handler))

    result = client.complete(
        "Existing governed system instructions",
        "Question and validated evidence",
        json_mode=True,
        temperature=0,
    )

    assert result == '{"mode":"data"}'
    assert captured["model"] == "qwen3:4b"
    assert captured["stream"] is False
    assert captured["format"] == "json"
    assert captured["messages"] == [
        {"role": "system", "content": "Existing governed system instructions"},
        {"role": "user", "content": "Question and validated evidence"},
    ]
    assert captured["options"] == {"temperature": 0}
    assert client.source == "ollama:qwen3:4b"


def test_ollama_connection_error_is_clear_and_does_not_create_an_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = GenerativeAIClient(ollama_settings())
    replace_http_client(client, httpx.MockTransport(handler))

    assert client.complete("system", "validated evidence") is None
    assert "not reachable" in client.unavailable_message
    assert "did not substitute a fabricated answer" in client.unavailable_message


def test_ollama_missing_model_is_reported_without_fallback_content() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    client = GenerativeAIClient(ollama_settings())
    replace_http_client(client, httpx.MockTransport(handler))

    assert client.complete("system", "validated evidence") is None
    assert "qwen3:4b" in client.unavailable_message
    assert "ollama pull qwen3:4b" in client.unavailable_message
    assert "did not substitute a fabricated answer" in client.unavailable_message


def test_ollama_health_checks_that_the_selected_model_is_installed() -> None:
    def available_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})

    client = GenerativeAIClient(ollama_settings())
    replace_http_client(client, httpx.MockTransport(available_handler))
    available = client.check_availability()

    assert available.configured is True
    assert available.available is True
    assert available.detail is None

    def missing_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})

    replace_http_client(client, httpx.MockTransport(missing_handler))
    missing = client.check_availability()

    assert missing.configured is True
    assert missing.available is False
    assert "not installed" in str(missing.detail)
