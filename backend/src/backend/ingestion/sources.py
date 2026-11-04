"""Manifest-verified loading into exact-string audit tables, offline only."""

import csv
import hashlib
import json
from pathlib import Path

from backend.ingestion.mappings import MAPPINGS
from backend.profiling.csv_scan import fingerprint, scan_csv
from backend.profiling.spec import SPECS
from backend.profiling.statistics import identifier


class BuildError(ValueError):
    pass


def load_manifest(path: Path, expected_deals: int) -> dict:
    payload = path.read_bytes()
    manifest = json.loads(payload.decode("utf-8"))
    manifest["_manifest_sha256"] = hashlib.sha256(payload).hexdigest()
    if (
        manifest.get("profile_version") != "1.0"
        or manifest.get("status") != "completed"
    ):
        raise BuildError("A completed profiling manifest version 1.0 is required")
    if set(manifest.get("files", {})) != set(SPECS):
        raise BuildError("Manifest must describe exactly the nine expected CSV files")
    if manifest.get("deal_total") != expected_deals:
        raise BuildError(f"Manifest must contain exactly {expected_deals} deals")
    for name, entry in manifest["files"].items():
        if entry.get("status") != "profiled" or not entry.get("csv_valid"):
            raise BuildError(f"Source is not fully profiled: {name}")
        if entry.get("unchanged_after_profiling") is not True:
            raise BuildError(f"Source changed during profiling: {name}")
        table = "deals" if name.startswith("deals_") else name.removesuffix(".csv")
        expected = [field.source for field in MAPPINGS[table]]
        if entry.get("headers") != expected:
            raise BuildError(f"Unapproved source header/order change: {name}")
    return manifest


def verify_hashes(raw: Path, manifest: dict) -> None:
    for name, entry in manifest["files"].items():
        if fingerprint(raw / name) != {
            "sha256": entry["sha256"],
            "size_bytes": entry["size_bytes"],
        }:
            raise BuildError(
                f"Source hash/size differs from profiling manifest: {name}"
            )


def csv_select(entry: dict) -> tuple[str, list]:
    query = """
        SELECT * FROM read_csv(
            ?, columns = ?, delim = ?, encoding = ?, header = true,
            auto_detect = false, quote = '"', escape = '"',
            force_not_null = ?, nullstr = '', strict_mode = true,
            ignore_errors = false, null_padding = false, parallel = false)
    """
    return query, [
        dict.fromkeys(entry["headers"], "VARCHAR"),
        entry["delimiter"],
        "utf-8" if entry["encoding"] == "utf-8-sig" else entry["encoding"],
        entry["headers"],
    ]


def load_sources(connection, raw: Path, manifest: dict) -> None:
    connection.execute("CREATE SCHEMA raw")
    connection.execute("CREATE SCHEMA audit")
    connection.execute("""
        CREATE TABLE audit.source_files (
            source_file VARCHAR PRIMARY KEY, sha256 VARCHAR NOT NULL,
            size_bytes BIGINT NOT NULL, record_count BIGINT NOT NULL,
            encoding VARCHAR NOT NULL, delimiter VARCHAR NOT NULL, headers_json
            VARCHAR NOT NULL)
    """)
    for name in SPECS:
        entry = manifest["files"][name]
        observed = scan_csv(raw / name)
        if (
            not observed["csv_valid"]
            or any(
                observed[key] != entry[key]
                for key in ("headers", "encoding", "delimiter", "sha256", "size_bytes")
            )
            or observed["records_parsed"] != entry["row_count"]
        ):
            raise BuildError(f"Strict CSV validation disagrees with manifest: {name}")
        table = "deals" if name.startswith("deals_") else name.removesuffix(".csv")
        select, parameters = csv_select(entry)
        statement = (
            f"SELECT ?::VARCHAR AS source_file, row_number() OVER ()::BIGINT "
            f"AS source_record, * FROM ({select})"
        )
        args = [name, str(raw / name), *parameters]
        if name == "deals_2022.csv" or table != "deals":
            connection.execute(f"CREATE TABLE raw.{table} AS {statement}", args)
        else:
            connection.execute(f"INSERT INTO raw.{table} {statement}", args)
        connection.execute(
            "INSERT INTO audit.source_files VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                name,
                entry["sha256"],
                entry["size_bytes"],
                entry["row_count"],
                entry["encoding"],
                entry["delimiter"],
                json.dumps(entry["headers"], ensure_ascii=False),
            ],
        )
    # A logical record number excludes the header and survives quoted multiline
    # fields. Single-threaded ordered CSV scans are independently reconciled.
    for table in MAPPINGS:
        connection.execute(
            f"ALTER TABLE raw.{table} ADD PRIMARY KEY (source_file, source_record)"
        )


def verify_raw_source(connection, raw: Path, name: str, entry: dict) -> int:
    table = "deals" if name.startswith("deals_") else name.removesuffix(".csv")
    select, parameters = csv_select(entry)
    columns = ", ".join(identifier(header) for header in entry["headers"])
    # EXCEPT ALL preserves multiplicity and compares every source field plus its
    # ordinal, not a lossy aggregate checksum. Row counts are checked separately.
    return connection.execute(
        f"""
        SELECT count(*) FROM (
            (SELECT source_record, {columns} FROM raw.{table} WHERE source_file = ?)
            EXCEPT ALL
            (SELECT row_number() OVER ()::BIGINT, * FROM ({select}))
        )
    """,
        [name, str(raw / name), *parameters],
    ).fetchone()[0]


SOURCE_EXCEPTIONS = (OSError, ValueError, csv.Error)


def verify_manifest(path: Path, snapshot: dict) -> None:
    if fingerprint(path)["sha256"] != snapshot["_manifest_sha256"]:
        raise BuildError("Profiling manifest changed during ingestion/validation")
