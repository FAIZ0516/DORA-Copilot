import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import Base
from backend.tts import TTSQuotaExceededError, adjust_characters, reserve_characters


def test_tts_usage_is_persisted_and_adjustable() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = reserve_characters(session, 120)
        second = reserve_characters(session, 80)
        corrected = adjust_characters(session, -10)

    assert first.used == 120
    assert second.used == 200
    assert corrected.used == 190


def test_tts_usage_rejects_over_limit() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    original_limit = settings.elevenlabs_monthly_char_limit
    settings.elevenlabs_monthly_char_limit = 100
    try:
        with Session(engine) as session:
            reserve_characters(session, 80)
            with pytest.raises(TTSQuotaExceededError):
                reserve_characters(session, 21)
    finally:
        settings.elevenlabs_monthly_char_limit = original_limit
