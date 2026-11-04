"""Offline build and validation entry point."""

import argparse
from pathlib import Path

import duckdb

from backend.ingestion.builder import build_database, inspect_existing, paths_safe
from backend.ingestion.mappings import UNRESOLVED
from backend.ingestion.reporting import write_report
from backend.ingestion.sources import SOURCE_EXCEPTIONS
from backend.profiling.csv_scan import fingerprint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or validate a source-reconciled DuckDB snapshot"
    )
    parser.add_argument(
        "action", choices=("build", "validate"), nargs="?", default="build"
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/reports/profile.json")
    )
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/uzex.duckdb")
    )
    parser.add_argument("--report-dir", type=Path, default=Path("data/reports"))
    parser.add_argument("--memory-mb", type=int, default=1024)
    args = parser.parse_args(argv)
    raw, manifest, database, reports = (
        p.resolve()
        for p in (args.raw_dir, args.manifest, args.database, args.report_dir)
    )
    try:
        paths_safe(raw, manifest, database, reports)
        if args.action == "build":
            report = build_database(
                raw, manifest, database, reports, memory_mb=args.memory_mb
            )
        else:
            validation = inspect_existing(
                raw, manifest, database, memory_mb=args.memory_mb
            )
            report = {
                "status": validation["status"],
                "validation": validation,
                "database": database.name,
                "database_size_bytes": database.stat().st_size,
                "database_sha256": fingerprint(database)["sha256"],
                "unresolved_semantics": list(UNRESOLVED),
            }
            write_report(report, reports, "validation")
    except (*SOURCE_EXCEPTIONS, duckdb.Error) as error:
        print(f"Ingestion failed: {type(error).__name__}: {error}")
        return 1
    print(f"Ingestion {args.action}: {report['status']}")
    if "failure" in report:
        print(report["failure"])
    print(f"Counts: {report.get('validation', {}).get('table_counts', {})}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
