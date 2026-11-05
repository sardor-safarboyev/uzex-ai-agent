"""Guarded execution of model-written SQL against the read-only snapshot.

Defence in depth: (1) the database file is opened read-only with external
file/network access and extension loading disabled and configuration locked;
(2) exactly one SELECT statement is accepted (parsed by DuckDB itself);
(3) execution time, memory and returned rows are bounded.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb

from backend.agent.semantic import VIEWS_SQL

MAX_ROWS = 200
_FORBIDDEN = re.compile(
    r"\b(read_csv|read_parquet|read_json|read_text|read_blob|glob|attach|copy|"
    r"install|load|pragma|export|import|httpfs|getenv|query_table)\b",
    re.IGNORECASE,
)


class SQLRejected(Exception):
    pass


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    ms: int


class SQLRunner:
    def __init__(
        self,
        path: Path,
        config: dict | None = None,
        timeout_ms: int = 15000,
        max_connections: int = 4,
    ):
        self.path = path
        self._config = config or {
            "threads": 2,
            "memory_limit": "1024MB",
            "max_temp_directory_size": "0MB",
            "enable_external_access": False,
            "lock_configuration": True,
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
            "allow_community_extensions": False,
            "allow_unsigned_extensions": False,
        }
        self._timeout_ms = timeout_ms
        self._slots = threading.BoundedSemaphore(max_connections)
        self._local = threading.local()
        self._base: duckdb.DuckDBPyConnection | None = None
        self._base_lock = threading.Lock()

    def _connection(self) -> duckdb.DuckDBPyConnection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            with self._base_lock:
                if self._base is None:
                    self._base = duckdb.connect(
                        str(self.path), read_only=True, config=self._config
                    )
                connection = self._base.cursor()
            connection.execute(VIEWS_SQL)
            self._local.connection = connection
        return connection

    @staticmethod
    def check(sql: str) -> str:
        text = sql.strip().rstrip(";").strip()
        if not text:
            raise SQLRejected("empty SQL")
        if _FORBIDDEN.search(text):
            raise SQLRejected("forbidden function or keyword")
        try:
            statements = duckdb.extract_statements(text)
        except duckdb.Error as error:
            raise SQLRejected(f"parse error: {error}") from error
        if len(statements) != 1:
            raise SQLRejected("exactly one statement is allowed")
        if statements[0].type != duckdb.StatementType.SELECT:
            raise SQLRejected("only SELECT queries are allowed")
        return text

    def run(self, sql: str) -> QueryResult:
        text = self.check(sql)
        if not self._slots.acquire(timeout=20):
            raise SQLRejected("database busy")
        try:
            connection = self._connection()
            started = time.monotonic()
            timer = threading.Timer(self._timeout_ms / 1000, connection.interrupt)
            timer.start()
            try:
                cursor = connection.execute(text)
                columns = [c[0] for c in cursor.description or []]
                rows = cursor.fetchmany(MAX_ROWS + 1)
            finally:
                timer.cancel()
            ms = int((time.monotonic() - started) * 1000)
        finally:
            self._slots.release()
        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]
        return QueryResult(
            sql=text,
            columns=columns,
            rows=[[_json_value(v) for v in row] for row in rows],
            row_count=len(rows),
            truncated=truncated,
            ms=ms,
        )


def _json_value(value):
    if isinstance(value, decimal.Decimal):
        # exact: integers stay numbers, fractional values become exact strings
        if value == value.to_integral_value():
            return int(value)
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.days if value.seconds == 0 else str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    return value
