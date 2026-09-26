"""The async Postgres pool both services use."""

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


async def open_pool(dsn: str, *, max_size: int = 5) -> AsyncConnectionPool:
    """Open a pool and wait until it can hand out a connection.

    Waiting here makes a wrong DSN fail at startup, where the container
    healthcheck and the deploy log show it, rather than on the first request.
    """
    pool = AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=max_size,
        open=False,
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            # No server-side prepared statements, so the same code works behind
            # Supavisor's transaction pooler as well as the session pooler.
            "prepare_threshold": None,
        },
    )
    await pool.open(wait=True, timeout=30)
    return pool
