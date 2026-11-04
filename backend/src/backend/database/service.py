"""Readiness and bounded catalog inspection, without schema assumptions."""

import duckdb

from backend.database.adapter import DuckDBAdapter
from backend.database.errors import DatabaseAccessError, DatabaseErrorCode
from backend.database.models import (
    ColumnMetadata,
    DatabaseInspection,
    DatabaseReadiness,
    TableMetadata,
)

# Never interpolate identifiers or execute table/view definitions. Defaults,
# comments and SQL definitions are intentionally omitted: they may contain data.
CATALOG_QUERY = """
SELECT t.table_catalog, t.table_schema, t.table_name, t.table_type,
       c.column_name, c.data_type, c.ordinal_position, c.is_nullable
FROM information_schema.tables AS t
LEFT JOIN information_schema.columns AS c
  ON c.table_catalog = t.table_catalog
 AND c.table_schema = t.table_schema AND c.table_name = t.table_name
WHERE t.table_catalog = current_database()
ORDER BY t.table_catalog, t.table_schema, t.table_name, c.ordinal_position
LIMIT ?
"""


class DatabaseService:
    def __init__(self, adapter: DuckDBAdapter, max_metadata_columns: int):
        self._adapter = adapter
        self._max_metadata_columns = max_metadata_columns

    def readiness(self) -> DatabaseReadiness:
        try:
            with self._adapter.connection() as connection:
                connection.execute("SELECT 1").fetchone()
        except DatabaseAccessError as error:
            return DatabaseReadiness(status="not_ready", reason=error.code)
        return DatabaseReadiness(status="ready")

    def inspect(self) -> DatabaseInspection:
        with self._adapter.connection() as connection:
            rows = connection.execute(
                CATALOG_QUERY, [self._max_metadata_columns + 1]
            ).fetchall()
        if len(rows) > self._max_metadata_columns:
            raise DatabaseAccessError(DatabaseErrorCode.RESOURCE_LIMIT)
        tables: dict[tuple[str, str, str], TableMetadata] = {}
        for catalog, schema, name, kind, column, data_type, ordinal, nullable in rows:
            key = (catalog, schema, name)
            if key not in tables:
                tables[key] = TableMetadata(
                    catalog=catalog,
                    schema_name=schema,
                    name=name,
                    kind=kind,
                    columns=[],
                )
            if column is not None:
                tables[key].columns.append(
                    ColumnMetadata(
                        name=column,
                        data_type=data_type,
                        ordinal_position=ordinal,
                        nullable=nullable == "YES",
                    )
                )
        return DatabaseInspection(
            engine_version=duckdb.__version__, tables=list(tables.values())
        )
