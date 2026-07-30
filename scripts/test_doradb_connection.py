"""Validate the configured DoraDB login without printing credentials."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import Settings


def main() -> int:
    settings = Settings()
    if not settings.doradb_configured:
        return 2
    engine = create_engine(
        settings.doradb_url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c default_transaction_read_only=on -c statement_timeout=5000",
        },
    )
    try:
        with engine.connect() as connection:
            read_only = connection.scalar(text("SHOW transaction_read_only"))
            connection.execute(text("SELECT 1"))
        return 0 if str(read_only).lower() == "on" else 3
    except SQLAlchemyError:
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
