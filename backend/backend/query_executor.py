"""Executes validated queries as the read-only role, at a given replay time.

Per query: (1) move this connection's replay clock (needs REPLAY_CLOCK_SECRET, which
only the backend knows), (2) open a READ ONLY transaction with a statement timeout,
(3) run the validated SQL wrapped in a row limit, (4) roll back. The role can only
SELECT from the `replay.*` views, and those views only show rows known at the clock,
so even a query that slipped past the validator could not read the future.

Blocking (psycopg is synchronous): call from `asyncio.to_thread`.
"""
from __future__ import annotations

import math
import os
import queue
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from backend.sql_validator import Validated

load_dotenv(Path(__file__).resolve().parent.parent.parent / '.env')

DEFAULT_ROW_LIMIT = 2000
DEFAULT_TIMEOUT_MS = 3000


class ExecutorUnavailable(RuntimeError):
    """The read-only role or clock secret is not configured / the database is unreachable."""


class QueryTimeout(RuntimeError):
    pass


class QueryError(RuntimeError):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    elapsed_ms: float
    truncated: bool

    def as_dicts(self) -> list[dict]:
        return [dict(zip(self.columns, row)) for row in self.rows]


def to_json_value(value):
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, (bytes, memoryview)):
        return None
    return value


class QueryExecutor:
    def __init__(self, pool_size: int = 4, row_limit: int = DEFAULT_ROW_LIMIT, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        self.row_limit = row_limit
        self.timeout_ms = int(timeout_ms)
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size)
        self._pool_size = pool_size
        self._created = 0
        self._catalog: dict[str, dict[str, str]] | None = None

    # ---- connections ---------------------------------------------------------------
    def _secret(self) -> str:
        secret = os.getenv('REPLAY_CLOCK_SECRET')
        if not secret or not os.getenv('RAMP_RO_PASSWORD'):
            raise ExecutorUnavailable('RAMP_RO_PASSWORD / REPLAY_CLOCK_SECRET are not set in .env')
        return secret

    def _connect(self):
        self._secret()
        try:
            return psycopg.connect(
                host=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
                dbname=os.getenv('DB_NAME', 'f1_analytics'), user=os.getenv('RAMP_RO_USER', 'ramp_readonly'),
                password=os.environ['RAMP_RO_PASSWORD'], autocommit=True, connect_timeout=5)
        except psycopg.OperationalError as exc:
            raise ExecutorUnavailable(f'cannot connect as the read-only role: {str(exc).splitlines()[0]}') from None

    def _acquire(self):
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            if self._created < self._pool_size:
                self._created += 1
                try:
                    return self._connect()
                except Exception:
                    self._created -= 1
                    raise
            return self._pool.get(timeout=10)

    def _release(self, conn, broken: bool) -> None:
        if broken or conn.closed:
            try:
                conn.close()
            except Exception:
                pass
            self._created -= 1
        else:
            self._pool.put(conn)

    def close(self) -> None:
        while not self._pool.empty():
            try:
                self._pool.get_nowait().close()
            except Exception:
                pass
        self._created = 0

    # ---- catalog -----------------------------------------------------------------------
    def catalog(self, refresh: bool = False) -> dict[str, dict[str, str]]:
        """View -> {column: type}, read from the database as the read-only role, so it lists
        exactly (and only) the views the role may query."""
        if self._catalog is None or refresh:
            conn = self._acquire()
            broken = False
            try:
                rows = conn.execute("""SELECT table_name, column_name, data_type
                                       FROM information_schema.columns WHERE table_schema = 'replay'
                                       ORDER BY table_name, ordinal_position""").fetchall()
            except psycopg.Error as exc:
                broken = True
                raise ExecutorUnavailable(str(exc).splitlines()[0]) from None
            finally:
                self._release(conn, broken)
            catalog: dict[str, dict[str, str]] = {}
            for table, column, data_type in rows:
                catalog.setdefault(table, {})[column] = data_type
            self._catalog = catalog
        return self._catalog

    # ---- execution --------------------------------------------------------------------
    def run(
        self,
        query: Validated,
        params: dict,
        session_id: int,
        replay_time: datetime,
        row_limit: int | None = None,
    ) -> QueryResult:
        if not isinstance(query, Validated):
            raise TypeError('only validated queries can be executed')
        return self._execute(query.sql, params, session_id, replay_time, row_limit=row_limit)

    def _execute(
        self,
        sql: str,
        params: dict,
        session_id: int,
        replay_time: datetime,
        row_limit: int | None = None,
    ) -> QueryResult:
        effective_limit = self.row_limit if row_limit is None else int(row_limit)
        if effective_limit < 1 or effective_limit > 10000:
            raise ValueError('row_limit must be between 1 and 10000')
        secret = self._secret()
        values = dict(params)
        values['_row_limit'] = effective_limit + 1       # one extra row detects truncation
        wrapped = f'SELECT * FROM ({sql}) AS _q LIMIT %(_row_limit)s'
        conn = self._acquire()
        broken = False
        started = time.perf_counter()
        try:
            conn.execute('SELECT replay.set_clock(%s, %s, %s)', (secret, session_id, replay_time))
            conn.execute('BEGIN READ ONLY')
            try:
                conn.execute(f'SET LOCAL statement_timeout = {self.timeout_ms}')
                cur = conn.execute(wrapped, values)
                columns = [d.name for d in cur.description]
                fetched = cur.fetchall()
            finally:
                conn.execute('ROLLBACK')
        except psycopg.errors.QueryCanceled:
            raise QueryTimeout(f'query exceeded {self.timeout_ms} ms') from None
        except psycopg.errors.InsufficientPrivilege as exc:
            raise QueryError(f'not permitted: {str(exc).splitlines()[0]}') from None
        except psycopg.OperationalError as exc:
            broken = True
            raise ExecutorUnavailable(str(exc).splitlines()[0]) from None
        except psycopg.Error as exc:
            raise QueryError(str(exc).splitlines()[0]) from None
        finally:
            self._release(conn, broken)
        truncated = len(fetched) > effective_limit
        rows = [[to_json_value(v) for v in row] for row in fetched[:effective_limit]]
        return QueryResult(columns, rows, round((time.perf_counter() - started) * 1000, 1), truncated)
