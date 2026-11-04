"""Reproducible local CSV profiling, isolated from the runtime database adapter."""

import csv
import hashlib
import json
import platform
from pathlib import Path

import duckdb

from backend.profiling.csv_scan import fingerprint, scan_csv
from backend.profiling.relationships import (
    combined_join_risk,
    deal_checks,
    product_variants,
    rate_coverage,
    relationships,
)
from backend.profiling.spec import SPECS, SourceSpec
from backend.profiling.statistics import column_profile, duplicate_keys, identifier


def profile_source(connection, path: Path, table: str, spec: SourceSpec) -> dict:
    result = scan_csv(path)
    if not result["csv_valid"]:
        result["status"] = "failed"
        result["failure"] = (
            "Malformed CSV; no rows imported or repaired for column/join diagnostics."
        )
        return result
    headers = result["headers"]
    required = set(
        spec.identifiers
        + spec.dates
        + spec.decimals
        + spec.categories
        + spec.names
        + spec.times
        + (spec.identifier,)
    )
    if missing := sorted(required - set(headers)):
        result.update(
            status="failed", failure=f"Expected profiling headers absent: {missing}"
        )
        return result
    connection.execute(
        f"""
        CREATE TEMP TABLE {table} AS SELECT * FROM read_csv(
            ?, columns = ?, delim = ?, encoding = ?, header = true,
            auto_detect = false, quote = '"', escape = '"',
            nullstr = '', force_not_null = ?, strict_mode = true, ignore_errors = false,
            null_padding = false, parallel = false
        )
    """,
        [
            str(path),
            dict.fromkeys(headers, "VARCHAR"),
            result["delimiter"],
            "utf-8" if result["encoding"] == "utf-8-sig" else result["encoding"],
            headers,
        ],
    )
    loaded = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    if loaded != result["records_parsed"]:
        raise ValueError(f"Python/DuckDB record count disagreement: {loaded}")
    result["row_count"] = loaded
    result["columns"] = {
        column: column_profile(connection, table, column, spec) for column in headers
    }
    result["identifier_duplicates"] = duplicate_keys(connection, table, spec.identifier)
    result["status"] = "profiled"
    return result


def profile_dataset(raw_directory: Path, *, memory_mb: int = 1024) -> dict:
    report = {
        "profile_version": "1.0",
        "tools": {"python": platform.python_version(), "duckdb": duckdb.__version__},
        "method": {
            "source_values": "All fields VARCHAR; exact source strings and "
            "identifiers retained.",
            "csv": "Full strict decoding and CSV validation; no "
            "skipped, padded or repaired records.",
            "nulls": "Empty strings counted separately; whitespace and"
            " literal null markers not coerced.",
            "parsing": "Diagnostic only: DD.MM.YYYY, HH:MM:SS, strict "
            "space-grouped decimals; no source mutation.",
            "joins": "Observed-header hypotheses with exact keys; "
            "duplicate target rows retained in multiplicity "
            "counts.",
            "samples": "Value lists capped at 100; error/duplicate "
            "examples at 5; counts are full-data.",
            "database": "Transient in-memory profiling workspace; runtime"
            " read-only adapter is not used.",
            "memory_mb": memory_mb,
        },
        "files": {},
        "issues": [],
    }
    code = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        code.update(path.name.encode())
        code.update(path.read_bytes())
    report["profiler_sha256"] = code.hexdigest()
    tables = {}
    connection = duckdb.connect(
        ":memory:",
        config={
            "threads": 2,
            "memory_limit": f"{memory_mb}MB",
            "max_temp_directory_size": "0MB",
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
        },
    )
    try:
        for index, (name, spec) in enumerate(SPECS.items()):
            path = raw_directory / name
            table = f"source_{index}"
            try:
                result = profile_source(connection, path, table, spec)
            except (
                OSError,
                UnicodeError,
                ValueError,
                csv.Error,
                duckdb.Error,
            ) as error:
                result = {
                    "file": name,
                    "status": "failed",
                    "failure": str(error),
                    "error_type": type(error).__name__,
                }
                try:
                    result.update(fingerprint(path))
                except OSError:
                    pass  # Missing/unreadable sources already have explicit failures.
            report["files"][name] = result
            if result["status"] == "profiled":
                tables[name] = table
            else:
                report["issues"].append(
                    {
                        "severity": "error",
                        "check": "source_failure",
                        "file": name,
                        "detail": result["failure"],
                    }
                )
        deal_files = [f"deals_{year}.csv" for year in range(2022, 2027)]
        if all(name in tables for name in deal_files):
            headers = [report["files"][name]["headers"] for name in deal_files]
            if all(header == headers[0] for header in headers):
                connection.execute(
                    "CREATE TEMP VIEW all_deals AS "
                    + " UNION ALL ".join(
                        f"SELECT * FROM {tables[name]}" for name in deal_files
                    )
                )
                tables["deals"] = "all_deals"
                report["deal_total"] = connection.execute(
                    "SELECT count(*) FROM all_deals"
                ).fetchone()[0]
                report["deal_id_duplicates_across_years"] = duplicate_keys(
                    connection, "all_deals", "Номер сделки"
                )
                report["deal_checks"] = deal_checks(connection, "all_deals")
                report["deal_rows_outside_file_year"] = {
                    name: connection.execute(
                        f"SELECT count(*) FROM {tables[name]} WHERE "
                        f"year(try_strptime({identifier('Дата сделки')}, "
                        "'%d.%m.%Y')) <> ?",
                        [int(name[6:10])],
                    ).fetchone()[0]
                    for name in deal_files
                }
            else:
                report["issues"].append(
                    {"severity": "error", "check": "deal_headers_differ"}
                )
        report["joins"] = relationships(connection, tables)
        report["combined_join_risk"] = combined_join_risk(connection, tables)
        report["product_variants"] = product_variants(connection, tables)
        report["usd_rate_coverage"] = rate_coverage(connection, tables)
        collect_issues(report)
    except (duckdb.Error, ValueError) as error:
        report["issues"].append(
            {
                "severity": "error",
                "check": "analysis_failure",
                "detail": str(error),
            }
        )
    finally:
        connection.close()
    for name, result in report["files"].items():
        if "sha256" in result:
            try:
                unchanged = fingerprint(raw_directory / name) == {
                    "sha256": result["sha256"],
                    "size_bytes": result["size_bytes"],
                }
            except OSError:
                unchanged = False
            result["unchanged_after_profiling"] = unchanged
            if not unchanged:
                report["issues"].append(
                    {"severity": "error", "check": "source_changed", "file": name}
                )
    report["status"] = (
        "failed"
        if any(i["severity"] == "error" for i in report["issues"])
        else "completed"
    )
    return report


def collect_issues(report: dict) -> None:
    def issue(check, **details):
        report["issues"].append({"severity": "warning", "check": check, **details})

    for name, source in report["files"].items():
        if source["status"] != "profiled":
            continue
        if source["identifier_duplicates"]["duplicate_keys"]:
            issue("duplicate_identifier", file=name, **source["identifier_duplicates"])
        for column, stats in source["columns"].items():
            if stats.get("parsing", {}).get("failures"):
                issue("parse_failure", file=name, column=column, **stats["parsing"])
            if (
                stats["empty"]
                or stats["whitespace_only"]
                or stats["null_marker_candidates"]
            ):
                issue(
                    "missing_value_candidates",
                    file=name,
                    column=column,
                    empty=stats["empty"],
                    whitespace_only=stats["whitespace_only"],
                    literal_markers=stats["null_marker_candidates"],
                )
            if stats.get("scripts", {}).get("mixed_script_rows"):
                issue(
                    "mixed_script_names", file=name, column=column, **stats["scripts"]
                )
    duplicates = report.get("deal_id_duplicates_across_years", {})
    if duplicates.get("duplicate_keys"):
        issue("cross_year_duplicate_deal_id", **duplicates)
    for name, join in report["joins"].items():
        if join["status"] == "measured":
            if join.get("candidate_only"):
                if join["excess_left_join_rows"] or join["unmatched_source_rows"]:
                    issue(
                        "unsafe_join_candidate",
                        relationship=name,
                        excess_rows=join["excess_left_join_rows"],
                        unmatched_rows=join["unmatched_source_rows"],
                    )
                continue
            if join["unmatched_source_rows"]:
                issue(
                    "unmatched_join_key",
                    relationship=name,
                    count=join["unmatched_source_rows"],
                )
            if join["excess_left_join_rows"]:
                issue(
                    "join_inflation",
                    relationship=name,
                    excess_rows=join["excess_left_join_rows"],
                )
    rates = report["usd_rate_coverage"]
    if rates["status"] == "measured":
        for check in (
            "usd_missing_rate",
            "usd_duplicate_rate",
            "usd_invalid_rate",
            "usd_invalid_dates",
            "missing_contract",
            "ambiguous_contract_rows",
            "unsupported_currency_rows",
        ):
            if rates[check]:
                issue(check, count=rates[check])
    for check, count in report.get("deal_checks", {}).items():
        if isinstance(count, int) and count:
            issue(check, count=count)


def write_reports(report: dict, directory: Path) -> None:
    from backend.profiling.markdown import render_markdown

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "profile.json").write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=str,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (directory / "profile.md").write_text(render_markdown(report), encoding="utf-8")
