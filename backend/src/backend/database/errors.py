"""Stable, sanitized database failure codes for service and HTTP callers."""

from enum import StrEnum

import duckdb


class DatabaseErrorCode(StrEnum):
    NOT_CONFIGURED = "not_configured"
    NOT_FOUND = "not_found"
    NOT_A_FILE = "not_a_file"
    PERMISSION_DENIED = "permission_denied"
    INVALID_DATABASE = "invalid_database"
    BUSY = "busy"
    RESOURCE_LIMIT = "resource_limit"
    QUERY_TIMEOUT = "query_timeout"
    READ_ONLY = "read_only_violation"
    UNAVAILABLE = "unavailable"


class DatabaseAccessError(Exception):
    def __init__(self, code: DatabaseErrorCode):
        self.code = code
        super().__init__(code.value)


def translate_error(error: Exception) -> DatabaseAccessError:
    if isinstance(error, FileNotFoundError):
        code = DatabaseErrorCode.NOT_FOUND
    elif isinstance(error, PermissionError):
        code = DatabaseErrorCode.PERMISSION_DENIED
    elif isinstance(error, duckdb.OutOfMemoryException):
        code = DatabaseErrorCode.RESOURCE_LIMIT
    elif isinstance(error, duckdb.InterruptException):
        code = DatabaseErrorCode.QUERY_TIMEOUT
    else:
        # DuckDB's IOException covers several OS/storage failures. Inspect only
        # for classification; never include its path/SQL-bearing text in HTTP.
        message = str(error).lower()
        if "permission denied" in message or "access is denied" in message:
            code = DatabaseErrorCode.PERMISSION_DENIED
        elif any(
            s in message
            for s in ("not a valid duckdb", "not valid duckdb", "corrupt", "checksum")
        ):
            code = DatabaseErrorCode.INVALID_DATABASE
        elif "read-only" in message or "read only" in message:
            code = DatabaseErrorCode.READ_ONLY
        else:
            code = DatabaseErrorCode.UNAVAILABLE
    return DatabaseAccessError(code)
