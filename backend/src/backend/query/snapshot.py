"""Verify the ingestion boundary before trusting its mapped columns or evidence."""

import re
from dataclasses import dataclass

from backend.query.mappings import FROM, PRIMARY_KEYS, REQUIRED_COLUMNS, SOURCES


class InsufficientSnapshot(ValueError):
    pass


@dataclass(frozen=True)
class Snapshot:
    sources: dict[str, str]
    total_deals: int
    manifest_sha256: str


def verify_snapshot(connection) -> Snapshot:
    columns = connection.execute("""
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns WHERE table_catalog = current_database()
    """).fetchall()
    actual = {(schema, table, column): kind for schema, table, column, kind in columns}
    for table, fields in REQUIRED_COLUMNS.items():
        if any(("main", table, field) not in actual for field in fields):
            raise InsufficientSnapshot(
                "Verified ingestion schema columns are unavailable."
            )
    audit = {
        "build_info": {"key", "value"},
        "source_files": {"source_file", "sha256", "record_count"},
        "validation_checks": {"passed"},
    }
    if any(
        ("audit", table, field) not in actual
        for table, fields in audit.items()
        for field in fields
    ):
        raise InsufficientSnapshot("Verified build metadata is unavailable.")
    for table, key in PRIMARY_KEYS.items():
        if actual["main", table, key] != "VARCHAR":
            raise InsufficientSnapshot("Identifier columns must retain string types.")
    text_fields = REQUIRED_COLUMNS["deals"] - {
        "deal_date",
        "transaction_amount",
        "deal_quantity_lots",
        "lot_size",
        "delivered_lots",
        "source_record",
    }
    if any(actual["main", "deals", field] != "VARCHAR" for field in text_fields):
        raise InsufficientSnapshot(
            "Source text/identifier types do not match verified mappings."
        )
    if actual["main", "deals", "deal_date"] != "DATE" or any(
        not actual["main", "deals", field].startswith("DECIMAL(")
        for field in (
            "transaction_amount",
            "deal_quantity_lots",
            "lot_size",
            "delivered_lots",
        )
    ):
        raise InsufficientSnapshot(
            "Date/decimal storage types do not match verified mappings."
        )
    keys = connection.execute("""
        SELECT tc.table_name, k.column_name FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage k
          ON tc.constraint_catalog = k.constraint_catalog
         AND tc.constraint_schema = k.constraint_schema AND tc.constraint_name =
         k.constraint_name
        WHERE tc.table_schema = 'main' AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY tc.table_name, k.ordinal_position
    """).fetchall()
    for table, key in PRIMARY_KEYS.items():
        if [field for name, field in keys if name == table] != [key]:
            raise InsufficientSnapshot(
                "One-row-per-key primary constraints are unverified."
            )
    info = dict(
        connection.execute("SELECT key, value FROM audit.build_info").fetchall()
    )
    manifest = info.get("profile_manifest_sha256", "")
    if info.get("schema_version") != "1.0" or not re.fullmatch(
        r"[a-f0-9]{64}", manifest
    ):
        raise InsufficientSnapshot(
            "The ingestion schema version or manifest is unverified."
        )
    count, failures = connection.execute(
        "SELECT count(*), count(*) FILTER (WHERE NOT "
        "passed OR passed IS NULL) FROM "
        "audit.validation_checks"
    ).fetchone()
    if not count or failures:
        raise InsufficientSnapshot(
            "The snapshot has no successful build validation evidence."
        )
    rows = connection.execute(
        "SELECT source_file, sha256, record_count FROM "
        "audit.source_files ORDER BY source_file"
    ).fetchall()
    if (
        len(rows) != 9
        or {row[0] for row in rows} != SOURCES
        or any(not re.fullmatch(r"[a-f0-9]{64}", row[1]) or row[2] < 0 for row in rows)
    ):
        raise InsufficientSnapshot("Source manifest entries are incomplete or invalid.")
    declared = sum(row[2] for row in rows if row[0].startswith("deals_"))
    # This check is independent of query filters and prevents unnoticed unmatched
    # dimensions or a multiplied fact population from yielding confident answers.
    total, unique, missing = connection.execute(f"""
        SELECT count(*), count(DISTINCT d.deal_id), count(*) FILTER (
            WHERE c.contract_id IS NULL OR seller.inn IS NULL OR buyer.inn IS NULL
               OR sb.broker_code IS NULL OR bb.broker_code IS NULL)
        {FROM}
    """).fetchone()
    if total != declared or unique != declared or missing:
        raise InsufficientSnapshot(
            "Fact grain or exact-key dimension coverage failed verification."
        )
    return Snapshot({name: sha for name, sha, _ in rows}, total, manifest)
