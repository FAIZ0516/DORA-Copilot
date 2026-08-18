from unittest.mock import patch

from backend.api.system import readiness


def test_readiness_does_not_probe_the_llm_provider() -> None:
    with (
        patch(
            "backend.api.system._database_readiness",
            return_value=("ok", "postgresql:neondb", True, None),
        ),
        patch("backend.api.system.GenerativeAIClient") as llm_client,
    ):
        payload = readiness()

    llm_client.assert_not_called()
    assert payload == {
        "status": "ok",
        "database": "postgresql:neondb",
        "data_source": "doradb",
        "database_connected": True,
        "detail": None,
    }
