"""Atomic local reports; the database also retains its build evidence."""

import json
import os
import tempfile
from pathlib import Path


def write_report(report: dict, directory: Path, stem: str = "build-validation") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, default=str)
        + "\n"
    )
    lines = [
        "# Ingestion validation",
        "",
        f"Status: **{report['status']}**.",
        "",
        f"Published database: {report.get('published', False)}.",
        f"Database: `{report.get('database', 'unavailable')}`; "
        f"size: {report.get('database_size_bytes', 'unavailable')} bytes.",
        "",
    ]
    if report.get("failure"):
        lines += [f"Failure: {report['failure']}", ""]
    validation = report.get("validation", {})
    lines += ["## Table counts", "", "| Table | Rows |", "| --- | ---: |"]
    lines += [
        f"| {name} | {count} |"
        for name, count in validation.get("all_table_counts", {}).items()
    ]
    checks = validation.get("checks", [])
    lines += [
        "",
        f"Checks passed: {sum(c['passed'] for c in checks)}/{len(checks)}.",
        "",
    ]
    lines += [
        "- FAILED: " + json.dumps(c, ensure_ascii=False)
        for c in checks
        if not c["passed"]
    ]
    lines += [
        "## Exceptions and unresolved semantics",
        "",
        "```json",
        json.dumps(validation.get("exceptions", {}), ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    lines += [f"- {item}" for item in report.get("unresolved_semantics", [])]
    lines += [
        "",
        "## Source hashes",
        "",
        "| File | Rows | SHA-256 |",
        "| --- | ---: | --- |",
    ]
    for name, source in report.get("sources", {}).items():
        lines.append(f"| {name} | {source['row_count']} | {source['sha256']} |")
    lines += [
        "",
        "## Actual database schema",
        "",
        "| Table | Column | Type | Nullable |",
        "| --- | --- | --- | --- |",
    ]
    for column in validation.get("schema", []):
        lines.append(
            f"| {column['schema_name']}.{column['table_name']} | "
            f"{column['column_name']} | {column['data_type']} | "
            f"{column['is_nullable']} |"
        )
    lines += [
        "",
        "Full check values, provenance and build fingerprints are in the JSON report.",
        "",
    ]
    for suffix, content in (("json", encoded), ("md", "\n".join(lines))):
        target = directory / f"{stem}.{suffix}"
        if target.is_symlink():
            raise ValueError(f"Refusing to replace report symlink: {target.name}")
        descriptor, temporary = tempfile.mkstemp(prefix=f".{stem}-", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
