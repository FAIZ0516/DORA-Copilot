"""Set the local postgres role password during an authorized trust window."""

from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2 import sql


def main() -> int:
    password = os.environ.pop("DORA_NEW_POSTGRES_PASSWORD", "")
    if not password:
        return 2
    try:
        connection = psycopg2.connect(
            host="127.0.0.1",
            port=5432,
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
                (password,),
            )
        connection.close()
        return 0
    except psycopg2.Error:
        return 1


if __name__ == "__main__":
    sys.exit(main())
