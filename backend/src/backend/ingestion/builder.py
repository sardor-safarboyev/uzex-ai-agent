"""Offline transactional build/publish and independent read-only validation."""

import hashlib
import json
import os
import platform
import tempfile
from pathlib import Path

import duckdb

from backend.ingestion.mappings import UNRESOLVED
from backend.ingestion.reporting import write_report
from backend.ingestion.sources import (
    SOURCE_EXCEPTIONS,
    BuildError,
    load_manifest,
    load_sources,
    verify_hashes,
    verify_manifest,
)
from backend.ingestion.tables import create_typed_tables
from backend.ingestion.validation import validate
from backend.profiling.csv_scan import fingerprint


def code_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    for name in ("csv_scan.py", "statistics.py", "spec.py"):
        path = Path(__file__).parents[1] / "profiling" / name
        digest.update(name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def configuration(memory_mb: int) -> dict:
    if memory_mb < 64:
        raise BuildError("memory_mb must be at least 64")
    return {
        "threads": 1,
        "memory_limit": f"{memory_mb}MB",
        "preserve_insertion_order": True,
        "max_temp_directory_size": "0MB",
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
    }


def paths_safe(raw: Path, manifest: Path, database: Path, reports: Path) -> None:
    if (
        database == manifest
        or reports == raw
        or reports.is_relative_to(raw)
        or database.is_relative_to(raw)
    ):
        raise BuildError(
            "Database and reports must be outside raw inputs and "
            "cannot overwrite the manifest"
        )
    targets = {
        reports / f"{stem}.{extension}"
        for stem in ("build-validation", "validation")
        for extension in ("json", "md")
    }
    if database in targets or manifest in targets:
        raise BuildError("Report targets must not overlap database or manifest")
    if database == reports or reports.is_relative_to(database):
        raise BuildError("Database and report directory paths overlap")


def metadata(connection, snapshot: dict, expected_deals: int) -> dict:
    info = {
        "schema_version": "1.0",
        "builder_sha256": code_fingerprint(),
        "profile_manifest_sha256": snapshot["_manifest_sha256"],
        "python": platform.python_version(),
        "duckdb": duckdb.__version__,
        "expected_deals": str(expected_deals),
        "unresolved_semantics": json.dumps(UNRESOLVED, ensure_ascii=False),
    }
    connection.execute(
        "CREATE TABLE audit.build_info (key VARCHAR PRIMARY "
        "KEY, value VARCHAR NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO audit.build_info VALUES (?, ?)", sorted(info.items())
    )
    connection.execute("""
        CREATE TABLE audit.validation_checks (
            check_name VARCHAR PRIMARY KEY, actual_json VARCHAR NOT NULL,
            expected_json VARCHAR NOT NULL, passed BOOLEAN NOT NULL)
    """)
    return info


def preflight(raw: Path, manifest: Path, expected_deals: int) -> dict:
    snapshot = load_manifest(manifest, expected_deals)
    verify_hashes(raw, snapshot)
    verify_manifest(manifest, snapshot)
    return snapshot


def inspect_existing(
    raw: Path,
    manifest: Path,
    database: Path,
    *,
    expected_deals: int = 500000,
    memory_mb: int = 1024,
) -> dict:
    snapshot = preflight(raw, manifest, expected_deals)
    if not database.is_file():
        raise BuildError("Validation requires an existing database file")
    # Deliberately read-only, but with CSV reads enabled for offline reconciliation.
    connection = duckdb.connect(
        str(database), read_only=True, config=configuration(memory_mb)
    )
    try:
        result = validate(connection, raw, snapshot, expected_deals)
        stored = dict(
            connection.execute("SELECT key, value FROM audit.build_info").fetchall()
        )
        valid_metadata = (
            stored.get("profile_manifest_sha256") == snapshot["_manifest_sha256"]
            and stored.get("schema_version") == "1.0"
            and stored.get("expected_deals") == str(expected_deals)
        )
        result["checks"].append(
            {
                "name": "build_metadata_matches_manifest",
                "actual": valid_metadata,
                "expected": True,
                "passed": valid_metadata,
            }
        )
        if not valid_metadata:
            result["status"] = "failed"
    finally:
        connection.close()
    verify_hashes(raw, snapshot)
    verify_manifest(manifest, snapshot)
    return result


def build_database(
    raw: Path,
    manifest: Path,
    database: Path,
    reports: Path,
    *,
    expected_deals: int = 500000,
    memory_mb: int = 1024,
) -> dict:
    raw, manifest, database, reports = (
        p.resolve() for p in (raw, manifest, database, reports)
    )
    paths_safe(raw, manifest, database, reports)
    report = {
        "status": "failed",
        "published": False,
        "database": database.name,
        "unresolved_semantics": list(UNRESOLVED),
    }
    lock = database.with_name(database.name + ".build.lock")
    descriptor = None
    try:
        config = configuration(memory_mb)
        snapshot = preflight(raw, manifest, expected_deals)
        report["sources"] = {
            name: {"sha256": f["sha256"], "row_count": f["row_count"]}
            for name, f in snapshot["files"].items()
        }
        database.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with tempfile.TemporaryDirectory(
            prefix=".uzex-build-", dir=database.parent
        ) as folder:
            temporary = Path(folder) / database.name
            connection = duckdb.connect(str(temporary), config=config)
            try:
                connection.execute("BEGIN TRANSACTION")
                load_sources(connection, raw, snapshot)
                report["build_info"] = metadata(connection, snapshot, expected_deals)
                create_typed_tables(connection)
                validation = validate(connection, raw, snapshot, expected_deals)
                report["validation"] = validation
                if validation["status"] != "passed":
                    raise BuildError("Integrity checks failed; output was not replaced")
                connection.executemany(
                    "INSERT INTO audit.validation_checks VALUES (?, ?, ?, ?)",
                    [
                        (
                            c["name"],
                            json.dumps(c["actual"]),
                            json.dumps(c["expected"]),
                            c["passed"],
                        )
                        for c in validation["checks"]
                    ],
                )
                connection.execute("COMMIT")
                connection.execute("CHECKPOINT")
            finally:
                connection.close()
            # Reopen the finished snapshot read-only and repeat all checks before
            # atomic publication. This also verifies source hashes again.
            report["validation"] = inspect_existing(
                raw,
                manifest,
                temporary,
                expected_deals=expected_deals,
                memory_mb=memory_mb,
            )
            if report["validation"]["status"] != "passed":
                raise BuildError("Read-only snapshot validation failed")
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            report["database_size_bytes"] = temporary.stat().st_size
            report["database_sha256"] = fingerprint(temporary)["sha256"]
            report["status"] = "passed"
            # Prestage the complete validation report before replacing the DB.
            write_report(report, reports)
            os.replace(temporary, database)
            report["published"] = True
            write_report(report, reports)
    except (*SOURCE_EXCEPTIONS, duckdb.Error) as error:
        report["status"] = "failed"
        report["failure"] = f"{type(error).__name__}: {error}"
        write_report(report, reports)
    finally:
        if descriptor is not None:
            os.close(descriptor)
            lock.unlink(missing_ok=True)
    return report
