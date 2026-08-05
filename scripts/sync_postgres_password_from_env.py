"""Synchronize the local postgres role with the password already saved in .env.

This recovery helper opens a localhost-only trust window for the postgres role,
reloads PostgreSQL, changes the role password, restores the original HBA file,
and validates the secure DoraDB connection. It never prints the password.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2 import sql


WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from backend.config import Settings  # noqa: E402


DATA_DIR = Path(r"D:\DevTools\PostgreSQLData")
PG_CTL = Path(r"D:\DevTools\PostgreSQL\bin\pg_ctl.exe")
HBA_PATH = DATA_DIR / "pg_hba.conf"
MARKER_PATH = WORKSPACE / ".runtime" / "postgres-password-reset.flag"
ERROR_PATH = WORKSPACE / ".runtime" / "postgres-password-sync-error.log"


def reload_postgres() -> None:
    subprocess.run(
        [str(PG_CTL), "reload", "-D", str(DATA_DIR)],
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> int:
    settings = Settings()
    if not settings.doradb_password:
        return 2

    original_hba = HBA_PATH.read_text(encoding="utf-8")
    backup_path = HBA_PATH.with_name(
        f"pg_hba.conf.codex-sync-backup-{datetime.now():%Y%m%d-%H%M%S}"
    )
    shutil.copy2(HBA_PATH, backup_path)
    trust_rules = (
        "# Temporary local postgres recovery rules - restored automatically\n"
        "host    all    postgres    127.0.0.1/32    trust\n"
        "host    all    postgres    ::1/128         trust\n\n"
    )

    try:
        HBA_PATH.write_text(trust_rules + original_hba, encoding="utf-8")
        reload_postgres()
        time.sleep(0.5)

        connection = psycopg2.connect(
            host=settings.doradb_host,
            port=settings.doradb_port,
            dbname="postgres",
            user="postgres",
            connect_timeout=5,
        )
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                    sql.Identifier("postgres")
                ),
                (settings.doradb_password,),
            )
        connection.close()
    finally:
        HBA_PATH.write_text(original_hba, encoding="utf-8")
        reload_postgres()

    time.sleep(0.5)
    secure_connection = psycopg2.connect(
        host=settings.doradb_host,
        port=settings.doradb_port,
        dbname=settings.doradb_name,
        user="postgres",
        password=settings.doradb_password,
        connect_timeout=5,
        options="-c default_transaction_read_only=on -c statement_timeout=5000",
    )
    with secure_connection.cursor() as cursor:
        cursor.execute("SHOW transaction_read_only")
        read_only = cursor.fetchone()
        cursor.execute("SELECT 1")
    secure_connection.close()
    if not read_only or str(read_only[0]).lower() != "on":
        return 3

    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKER_PATH.write_text(datetime.now().astimezone().isoformat(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        if ERROR_PATH.exists():
            ERROR_PATH.unlink()
        raise SystemExit(exit_code)
    except SystemExit:
        raise
    except Exception:
        ERROR_PATH.parent.mkdir(parents=True, exist_ok=True)
        ERROR_PATH.write_text(traceback.format_exc(), encoding="utf-8")
        raise
