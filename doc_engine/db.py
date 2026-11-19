"""Postgres access: a small async pool that reads the password at connect time and reconnects.

Lakebase credentials can be short-lived tokens used as the password, so every new connection
asks for it again. Broken connections are dropped and the operation is retried on a fresh one.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import ROOT, Section, effective_out_capacity, postgres_conninfo

log = logging.getLogger("doc_engine.db")

REQUIRED_TABLES = ["flows", "flow_versions", "documents", "jobs", "job_steps", "tasks", "quota",
                   "reservations", "profiles", "calls", "events", "cache_warm", "workers"]

__all__ = ["Db", "Jsonb", "sync_models", "apply_schema", "reset_schema", "missing_tables"]


class Db:
    def __init__(self, cfg: Section) -> None:
        self.cfg = cfg
        self.pool_size = int(cfg.postgres.get("pool_size", 16))
        self._free: list[psycopg.AsyncConnection] = []
        self._sem = asyncio.Semaphore(self.pool_size)
        self._open: set[psycopg.AsyncConnection] = set()

    async def connect(self, autocommit: bool = True) -> psycopg.AsyncConnection:
        delay = 0.5
        last: Exception | None = None
        for attempt in range(6):
            try:
                return await psycopg.AsyncConnection.connect(
                    **postgres_conninfo(self.cfg), autocommit=autocommit, row_factory=dict_row, connect_timeout=15)
            except psycopg.OperationalError as e:  # includes auth failures after a token refresh
                last = e
                log.warning("postgres connect failed (attempt %d): %s", attempt + 1, str(e).strip())
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8)
        raise RuntimeError(f"could not connect to Postgres after retries: {last}")

    @asynccontextmanager
    async def conn(self) -> AsyncIterator[psycopg.AsyncConnection]:
        async with self._sem:
            conn = None
            while self._free:
                c = self._free.pop()
                if not c.closed:
                    conn = c
                    break
            if conn is None:
                conn = await self.connect()
                self._open.add(conn)
            try:
                yield conn
            except (psycopg.OperationalError, psycopg.InterfaceError):
                await self._discard(conn)
                raise
            except BaseException:
                # leave no transaction open on a pooled connection
                if not conn.closed and conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                    try:
                        await conn.rollback()
                    except Exception:
                        await self._discard(conn)
                        raise
                self._free.append(conn)
                raise
            else:
                if conn.closed:
                    await self._discard(conn)
                else:
                    self._free.append(conn)

    async def _discard(self, conn: psycopg.AsyncConnection) -> None:
        self._open.discard(conn)
        try:
            await conn.close()
        except Exception:
            pass

    async def run(self, fn: Callable[[psycopg.AsyncConnection], Awaitable[Any]], retries: int = 3) -> Any:
        """Runs fn(conn), retrying on a lost connection or a serialization/deadlock failure."""
        last: Exception | None = None
        for attempt in range(retries):
            try:
                async with self.conn() as conn:
                    return await fn(conn)
            except (psycopg.OperationalError, psycopg.InterfaceError,
                    psycopg.errors.DeadlockDetected, psycopg.errors.SerializationFailure) as e:
                last = e
                log.warning("database operation failed (attempt %d): %s", attempt + 1, str(e).strip())
                await asyncio.sleep(0.2 * (attempt + 1))
        raise RuntimeError(f"database operation failed after {retries} attempts: {last}")

    async def tx(self, fn: Callable[[psycopg.AsyncConnection], Awaitable[Any]], retries: int = 3) -> Any:
        """Runs fn(conn) inside one transaction."""
        async def wrapped(conn: psycopg.AsyncConnection) -> Any:
            async with conn.transaction():
                return await fn(conn)
        return await self.run(wrapped, retries)

    async def fetch(self, sql: str, params: Any = None) -> list[dict]:
        async def go(conn: psycopg.AsyncConnection) -> list[dict]:
            cur = await conn.execute(sql, params)
            return await cur.fetchall()
        return await self.run(go)

    async def fetchone(self, sql: str, params: Any = None) -> dict | None:
        async def go(conn: psycopg.AsyncConnection) -> dict | None:
            cur = await conn.execute(sql, params)
            return await cur.fetchone()
        return await self.run(go)

    async def execute(self, sql: str, params: Any = None) -> int:
        async def go(conn: psycopg.AsyncConnection) -> int:
            cur = await conn.execute(sql, params)
            return cur.rowcount
        return await self.run(go)

    async def close(self) -> None:
        for c in list(self._open):
            await self._discard(c)
        self._free.clear()


async def missing_tables(db: Db) -> list[str]:
    rows = await db.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")
    have = {r["table_name"] for r in rows}
    return [t for t in REQUIRED_TABLES if t not in have]


async def apply_schema(db: Db) -> None:
    sql = (ROOT / "sql" / "001_schema.sql").read_text()
    async with db.conn() as conn:
        await conn.execute(sql)  # no parameters: the whole script runs as one simple query


async def reset_schema(db: Db) -> None:
    sql = (ROOT / "sql" / "reset.sql").read_text()
    async with db.conn() as conn:
        await conn.execute(sql)


async def sync_models(db: Db, cfg: Section) -> None:
    """Copies each model's limits from configuration into its quota row. Ledger state is kept."""
    led = cfg.ledger
    margin = float(led.get("safety_margin_fraction", 0.05))
    for key, m in cfg.models.items():
        await db.execute(
            """INSERT INTO quota (model, gateway_name, itpm, otpm, qph, out_capacity, in_capacity, capacity_mode,
                                  bucket_measured, default_call_s, safety_margin, hold_s, learn, hold_max_s)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (model) DO UPDATE SET gateway_name = excluded.gateway_name, itpm = excluded.itpm,
                   otpm = excluded.otpm, qph = excluded.qph, out_capacity = excluded.out_capacity,
                   in_capacity = excluded.in_capacity, capacity_mode = excluded.capacity_mode,
                   bucket_measured = excluded.bucket_measured, default_call_s = excluded.default_call_s,
                   safety_margin = excluded.safety_margin, hold_s = excluded.hold_s, learn = excluded.learn,
                   hold_max_s = excluded.hold_max_s""",
            (key, m.gateway_name, float(m.itpm), float(m.otpm), float(m.get("qph", 0)),
             effective_out_capacity(cfg, key), float(m.itpm) * (1 - margin), led.get("capacity_mode", "fixed"),
             float(m.get("bucket_measured") or m.get("bucket_capacity_output") or m.otpm),
             float(led.get("default_call_s", 9)), margin, float(led.get("hold_on_429_s", 1)),
             bool(led.get("learn_estimates", True)), float(led.get("hold_on_429_max_s", 15))))
    # A model taken out of the settings leaves the quota panels once nothing of it is waiting or in flight.
    await db.execute(
        """DELETE FROM quota q WHERE NOT (q.model = ANY(%s))
           AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.model = q.model AND t.state IN ('waiting', 'ready', 'running'))
           AND NOT EXISTS (SELECT 1 FROM reservations r WHERE r.model = q.model AND r.released_at IS NULL)""",
        (list(cfg.models),))
