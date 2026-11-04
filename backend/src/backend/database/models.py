"""Catalog-only response types; no sample values, SQL, or file paths."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.database.errors import DatabaseErrorCode


class MetadataModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ColumnMetadata(MetadataModel):
    name: str
    data_type: str
    ordinal_position: int
    nullable: bool


class TableMetadata(MetadataModel):
    catalog: str
    schema_name: str
    name: str
    kind: Literal["BASE TABLE", "VIEW"]
    columns: list[ColumnMetadata]


class DatabaseInspection(MetadataModel):
    engine: Literal["duckdb"] = "duckdb"
    engine_version: str
    read_only: Literal[True] = True
    tables: list[TableMetadata]


class DatabaseReadiness(MetadataModel):
    status: Literal["ready", "not_ready"]
    reason: DatabaseErrorCode | None = None
