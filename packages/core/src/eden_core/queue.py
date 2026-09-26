"""Thin wrappers over pgmq (Supabase Queues) for the one queue this project uses.

Plain SQL rather than a client library: pgmq is a handful of functions, and
calling them on the caller's own connection is what lets the API enqueue a job in
the same transaction that creates its session.
"""

from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

QUEUE = "scrape"


@dataclass(frozen=True, slots=True)
class Message:
    msg_id: int
    read_ct: int
    body: dict[str, Any]


async def send(conn: AsyncConnection, body: dict[str, Any], *, delay: int = 0) -> int:
    cur = await conn.execute(
        "select * from pgmq.send(%s, %s, %s) as msg_id", (QUEUE, Jsonb(body), delay)
    )
    row = await cur.fetchone()
    assert row is not None
    return int(row["msg_id"])


async def read(conn: AsyncConnection, *, vt: int, qty: int, poll_seconds: int = 5) -> list[Message]:
    """Up to `qty` messages, waiting up to `poll_seconds` for the first.

    Each message stays invisible to other readers for `vt` seconds. If the job is
    neither deleted nor archived by then, it reappears with `read_ct` one higher.
    """
    cur = await conn.execute(
        "select msg_id, read_ct, message from pgmq.read_with_poll(%s, %s, %s, %s, 250)",
        (QUEUE, vt, qty, poll_seconds),
    )
    rows = await cur.fetchall()
    return [Message(int(r["msg_id"]), int(r["read_ct"]), r["message"]) for r in rows]


async def delete(conn: AsyncConnection, msg_id: int) -> None:
    await conn.execute("select pgmq.delete(%s, %s::bigint)", (QUEUE, msg_id))


async def archive(conn: AsyncConnection, msg_id: int) -> None:
    """Move a message to `pgmq.a_scrape` so the failure stays inspectable."""
    await conn.execute("select pgmq.archive(%s, %s::bigint)", (QUEUE, msg_id))
