"""Direct Postgres connection pool over DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS.

Replaces the old supabase-py PostgREST client. Fail-lazy: a missing or wrong
DB_HOST is only detected on the first actual query, not at import time, so the
app still boots and healthchecks pass in environments where the DB isn't needed.
"""

from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from src.shared.config.env import DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER
from src.shared.logger import logger

_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        conninfo = f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER} password={DB_PASS}"
        logger.debug("Initialising Postgres connection pool | host={} db={}", DB_HOST, DB_NAME)
        _pool = ConnectionPool(conninfo, min_size=1, max_size=5, open=True)
        logger.debug("Postgres connection pool ready")
    return _pool


@contextmanager
def get_connection() -> Generator[psycopg.Connection, None, None]:
    """Yield a connection from the pool. Caller must use as a context manager."""
    pool = _get_pool()
    with pool.connection() as conn:
        yield conn
