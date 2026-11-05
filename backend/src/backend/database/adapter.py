"""Short-lived, bounded read-only connections for trusted backend code."""

import stat
from collections.abc import Iterator
from contextlib import contextmanager
from threading import BoundedSemaphore

import duckdb

from backend.config import Settings
from backend.database.errors import (
    DatabaseAccessError,
    DatabaseErrorCode,
    translate_error,
)


def connection_config(settings: Settings) -> dict:
    """Engine settings shared by every connection in this process.

    DuckDB refuses a second connection to the same file with a different
    configuration, so all components (adapter, agent) must use this.
    """
    return {
        "threads": settings.database_threads,
        "memory_limit": f"{settings.database_memory_mb}MB",
        "max_execution_time": settings.database_query_timeout_ms,
        "max_temp_directory_size": "0MB",
        "enable_external_access": False,
        "lock_configuration": True,
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
        "allow_community_extensions": False,
        "allow_unsigned_extensions": False,
    }


class DuckDBAdapter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._slots = BoundedSemaphore(settings.database_max_connections)

    @contextmanager
    def connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        if not self._slots.acquire(blocking=False):
            raise DatabaseAccessError(DatabaseErrorCode.BUSY)
        connection = None
        try:
            path = self._settings.database_path
            if path is None:
                raise DatabaseAccessError(DatabaseErrorCode.NOT_CONFIGURED)
            path = path.resolve(strict=True)
            if not stat.S_ISREG(path.stat().st_mode):
                raise DatabaseAccessError(DatabaseErrorCode.NOT_A_FILE)
            # Catch ordinary OS read-permission failures before engine startup.
            with path.open("rb"):
                pass
            connection = duckdb.connect(
                database=str(path),
                read_only=True,
                config=connection_config(self._settings),
            )
            yield connection
        except (duckdb.Error, OSError) as error:
            raise translate_error(error) from error
        finally:
            try:
                if connection is not None:
                    connection.close()
            finally:
                self._slots.release()
