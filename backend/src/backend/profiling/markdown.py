"""Human-readable measured findings; complete diagnostics remain in JSON."""

import json


def cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_markdown(report: dict) -> str:
    lines = [
        "# CSV dataset profile",
        "",
        f"Profile status: **{report['status']}**.",
        "",
        "Measured source data only. No raw files changed,"
        " source values repaired, names merged, "
        "or runtime schema mappings established.",
        "",
        "## Method and reproducibility",
        "",
        f"- Profiler code SHA-256: `{report['profiler_sha256']}`",
        f"- Python {report['tools']['python']}; DuckDB {report['tools']['duckdb']}.",
    ]
    lines += [f"- {key}: {value}" for key, value in report["method"].items()]
    lines += [
        "",
        "## Source inventory",
        "",
        "| File | Rows | Encoding | Delimiter | Width "
        "errors | Syntax errors | SHA-256 |",
        "| --- | ---: | --- | --- | ---: | ---: | --- |",
    ]
    for name, source in report["files"].items():
        lines.append(
            "| "
            + " | ".join(
                cell(v)
                for v in (
                    name,
                    source.get("row_count", "unavailable"),
                    source.get("encoding", "unverified"),
                    repr(source.get("delimiter")),
                    source.get("width_error_records", "?"),
                    source.get("syntax_error_groups", "?"),
                    source.get("sha256", "unavailable"),
                )
            )
            + " |"
        )
        if source["status"] == "failed":
            lines += ["", f"**{name} failure:** {source['failure']}", ""]
    lines += [
        "",
        f"Total measured deal rows: **{report.get('deal_total', 'unavailable')}**.",
        "",
        "## Join cardinality (exact source keys)",
        "",
        "| Relationship | Source rows | Unmatched | Rows "
        "with multiple matches | Left join rows | Excess "
        "rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, join in report.get("joins", {}).items():
        lines.append(
            "| "
            + " | ".join(
                cell(v)
                for v in (
                    name,
                    join.get("source_rows", "?"),
                    join.get("unmatched_source_rows", "?"),
                    join.get("source_rows_with_multiple_matches", "?"),
                    join.get("left_join_rows", "?"),
                    join.get("excess_left_join_rows", "?"),
                )
            )
            + " |"
        )
    for title, key in [
        ("Combined join risk", "combined_join_risk"),
        ("Exact product-name variation within contracts", "product_variants"),
        ("Transaction-date USD-rate coverage", "usd_rate_coverage"),
        ("Deal checks and official status versus delivery", "deal_checks"),
        ("Cross-year deal identifier uniqueness", "deal_id_duplicates_across_years"),
        ("Transaction date outside filename year", "deal_rows_outside_file_year"),
    ]:
        lines += [
            "",
            f"## {title}",
            "",
            "```json",
            json.dumps(
                report.get(key, {"status": "unavailable"}),
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "```",
        ]
    for name, source in report["files"].items():
        if source["status"] != "profiled":
            continue
        lines += [
            "",
            f"## {name}",
            "",
            "Identifier duplicates: "
            + json.dumps(source["identifier_duplicates"], ensure_ascii=False),
            "",
            "| Observed column | Diagnostic type | Empty | "
            "Whitespace-only | Distinct nonempty | Parse "
            "failures | Leading-zero digit strings |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for column, stats in source["columns"].items():
            lines.append(
                "| "
                + " | ".join(
                    cell(v)
                    for v in (
                        column,
                        stats["observed_type"],
                        stats["empty"],
                        stats["whitespace_only"],
                        stats["distinct_nonempty"],
                        stats.get("parsing", {}).get("failures", "n/a"),
                        stats["leading_zero_digit_strings"],
                    )
                )
                + " |"
            )
        for column, stats in source["columns"].items():
            if "value_counts" in stats:
                lines += [
                    "",
                    f"**{column} — observed values (top 15; more in JSON):**",
                    "",
                    "| Source value | Rows |",
                    "| --- | ---: |",
                ]
                lines += [
                    f"| {cell(row['value'])} | {row['count']} |"
                    for row in stats["value_counts"][:15]
                ]
                if "scripts" in stats:
                    lines += ["", "Script diagnostics: " + json.dumps(stats["scripts"])]
    lines += ["", "## Unresolved quality issues", ""]
    if report["issues"]:
        lines += [
            "- " + json.dumps(issue, ensure_ascii=False, sort_keys=True, default=str)
            for issue in report["issues"]
        ]
    else:
        lines += [
            "No configured checks found anomalies; this is not semantic certification."
        ]
    lines += [
        "",
        "## Next recommendations",
        "",
        "- Resolve source parsing failures and duplicate "
        "identifier ownership with the dataset provider; "
        "never discard or deduplicate silently.",
        "- Confirm grain and role-aware composite keys "
        "before designing joins; multiplicities above "
        "show how naive joins can inflate totals.",
        "- Confirm money, lot-size, physical-unit, rate-"
        "date and timezone semantics using the source "
        "documentation before analytical use.",
        "- Review missing keys and rates; unavailable "
        "evidence must remain distinct from a valid empty"
        " result.",
        "- Review company/product aliases manually. "
        "Preserve raw names and version any approved "
        "normalization separately.",
        "- Treat metre and square-metre units, if "
        "present, as separate families; do not force them"
        " into the existing semantic unit allowlist.",
        "- Freeze source hashes and an approved mapping "
        "contract before implementing import or semantic "
        "compilation.",
        "",
    ]
    return "\n".join(lines)
