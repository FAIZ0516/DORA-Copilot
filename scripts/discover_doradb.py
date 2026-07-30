"""Find the local PostgreSQL database containing the expected DoraDB objects."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import Settings


EXPECTED_OBJECTS = {
    "vw_gdt_dte_release_frequency",
    "vw_gdt_dte_release_success",
    "tbl_gdt_dte_release_info",
    "mvw_gdt_dte_jira_fuslist",
    "tbl_gdt_dte_jira_issues",
}


def main() -> None:
    settings = Settings()
    admin = psycopg2.connect(
        host=settings.doradb_host,
        port=settings.doradb_port,
        dbname="postgres",
        user=settings.doradb_user,
        password=settings.doradb_password,
        connect_timeout=5,
    )
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT datname
            FROM pg_database
            WHERE datistemplate IS FALSE AND datallowconn IS TRUE
            ORDER BY datname
            """
        )
        databases = [row[0] for row in cursor.fetchall()]
    admin.close()

    results: list[dict[str, object]] = []
    for database in databases:
        try:
            connection = psycopg2.connect(
                host=settings.doradb_host,
                port=settings.doradb_port,
                dbname=database,
                user=settings.doradb_user,
                password=settings.doradb_password,
                connect_timeout=5,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    UNION
                    SELECT table_name
                    FROM information_schema.views
                    WHERE table_schema = 'public'
                    UNION
                    SELECT matviewname
                    FROM pg_matviews
                    WHERE schemaname = 'public'
                    """
                )
                objects = {row[0] for row in cursor.fetchall()}
            connection.close()
            matches = sorted(EXPECTED_OBJECTS & objects)
            results.append(
                {
                    "database": database,
                    "expected_matches": matches,
                    "match_count": len(matches),
                }
            )
        except psycopg2.Error:
            results.append(
                {"database": database, "expected_matches": [], "match_count": 0}
            )

    print(json.dumps(results))


if __name__ == "__main__":
    main()
