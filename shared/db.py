from typing import Any, Iterable, Optional

import psycopg
from psycopg.rows import dict_row

from .config import DATABASE_URL


def db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def fetch_one(query: str, params: Iterable[Any] = ()) -> Optional[dict[str, Any]]:
    with db_connection() as connection:
        return connection.execute(query, tuple(params)).fetchone()


def fetch_all(query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with db_connection() as connection:
        return list(connection.execute(query, tuple(params)).fetchall())


def execute(query: str, params: Iterable[Any] = ()) -> None:
    with db_connection() as connection:
        connection.execute(query, tuple(params))
        connection.commit()
