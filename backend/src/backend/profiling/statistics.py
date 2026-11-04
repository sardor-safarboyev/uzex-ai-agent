"""Exact aggregate diagnostics over VARCHAR source values in transient DuckDB."""

from backend.profiling.spec import SourceSpec

# A diagnostic numeric grammar, never an instruction to repair source values.
# Grouped thousands require consistent blocks of three; decimal comma is allowed.
NUMBER_PATTERN = (
    r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:[ \x{00A0}\x{202F}][0-9]{3})+)(?:[.,][0-9]{1,10})?"
)


def identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def number(expression: str) -> str:
    clean = (
        f"replace(replace(replace(replace({expression}, ' ', ''), "
        "chr(160), ''), chr(8239), ''), ',', '.')"
    )
    return (
        f"CASE WHEN regexp_full_match({expression}, '{NUMBER_PATTERN}') "
        f"THEN try_cast({clean} AS DECIMAL(38,10)) END"
    )


def day(expression: str) -> str:
    return f"try_strptime({expression}, '%d.%m.%Y')::DATE"


def one(connection, sql: str, parameters=None) -> dict:
    cursor = connection.execute(sql, parameters or [])
    names = [column[0] for column in cursor.description]
    return dict(zip(names, cursor.fetchone(), strict=True))


def records(connection, sql: str, parameters=None) -> list[dict]:
    cursor = connection.execute(sql, parameters or [])
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def duplicate_keys(connection, table: str, column: str) -> dict:
    key = identifier(column)
    result = one(
        connection,
        f"""
        WITH keys AS (SELECT {key} k, count(*) n FROM {table} WHERE {key} <> ''
        GROUP BY 1)
        SELECT count(*) FILTER (WHERE n > 1) duplicate_keys,
               coalesce(sum(n - 1), 0)::BIGINT excess_rows,
               coalesce(max(n), 0)::BIGINT maximum_multiplicity FROM keys
    """,
    )
    result["examples"] = records(
        connection,
        f"""
        SELECT {key} value, count(*) count FROM {table} WHERE {key} <> ''
        GROUP BY 1 HAVING count(*) > 1 ORDER BY count DESC, value LIMIT 5
    """,
    )
    return result


def column_profile(connection, table: str, column: str, spec: SourceSpec) -> dict:
    value = identifier(column)
    result = one(
        connection,
        f"""
        SELECT count(*) rows, count(*) FILTER (WHERE {value} = '') empty,
            count(*) FILTER (WHERE {value} <> '' AND trim({value}) = '')
            whitespace_only,
            count(*) FILTER (WHERE {value} <> trim({value})) outer_whitespace,
            count(*) FILTER (WHERE {value} IN ('NULL', 'null', 'N/A', '\\N'))
            null_marker_candidates,
            count(DISTINCT nullif({value}, '')) distinct_nonempty,
            count(*) FILTER (WHERE regexp_full_match({value}, '0[0-9]+'))
            leading_zero_digit_strings,
            count(*) FILTER (WHERE regexp_full_match({value}, '[+-]?[0-9]+'))
            integer_like
        FROM {table}
    """,
    )
    result["storage_type"] = "VARCHAR"
    result["identifier"] = column in spec.identifiers or column == spec.identifier
    result["observed_type"] = (
        "identifier_string"
        if result["identifier"]
        else "integer_like_string"
        if result["integer_like"] == result["rows"] - result["empty"]
        and result["integer_like"] > 0
        else "string"
    )
    if column in spec.dates or column in spec.times or column in spec.decimals:
        if column in spec.dates:
            parsed, format_name = day(value), "%d.%m.%Y"
        elif column in spec.times:
            parsed, format_name = f"try_strptime({value}, '%H:%M:%S')::TIME", "%H:%M:%S"
        else:
            parsed, format_name = number(value), "strict grouped decimal; scale <= 10"
        result["parsing"] = one(
            connection,
            f"""
            SELECT count(*) FILTER (WHERE {value} <> '' AND ({parsed}) IS NULL)
            failures,
                count(*) FILTER (WHERE ({parsed}) IS NOT NULL) valid,
                min({parsed})::VARCHAR minimum, max({parsed})::VARCHAR maximum
            FROM {table}
        """,
        )
        result["parsing"]["format"] = format_name
        result["observed_type"] = (
            "date_string"
            if column in spec.dates
            else ("time_string" if column in spec.times else "decimal_string")
        )
        result["parsing"]["failure_examples"] = records(
            connection,
            f"""
            SELECT {value} value, count(*) count FROM {table}
            WHERE {value} <> '' AND ({parsed}) IS NULL GROUP BY 1
            ORDER BY count DESC, value LIMIT 5
        """,
        )
        if column in spec.decimals:
            result["parsing"]["negative"] = connection.execute(
                f"SELECT count(*) FROM {table} WHERE ({parsed}) < 0"
            ).fetchone()[0]
            result["parsing"]["grouped_strings"] = connection.execute(
                f"SELECT count(*) FROM {table} WHERE ({parsed}) IS NOT NULL "
                f"AND regexp_matches({value}, '[ \\x{{00A0}}\\x{{202F}}]')"
            ).fetchone()[0]
    if column in spec.categories or column in spec.names:
        result["value_counts"] = records(
            connection,
            f"""
            SELECT {value} value, count(*) count FROM {table}
            GROUP BY 1 ORDER BY count DESC, value LIMIT 100
        """,
        )
        result["value_counts_truncated"] = result["distinct_nonempty"] > 100
    if column in spec.names:
        result["scripts"] = one(
            connection,
            f"""
            SELECT count(*) FILTER (WHERE regexp_matches({value}, '[A-Za-zÀ-ɏ]'))
            latin_rows,
                count(*) FILTER (WHERE regexp_matches({value}, '[Ѐ-ԯ]')) cyrillic_rows,
                count(*) FILTER (WHERE regexp_matches({value}, '[A-Za-zÀ-ɏ]')
                    AND regexp_matches({value}, '[Ѐ-ԯ]')) mixed_script_rows FROM {table}
        """,
        )
    return result


def join_profile(
    connection, source: str, source_key: str, target: str, target_key: str
) -> dict:
    left, right = identifier(source_key), identifier(target_key)
    result = one(
        connection,
        f"""
        WITH keys AS (SELECT {right} k, count(*) n FROM {target} WHERE {right} <> ''
        GROUP BY 1)
        SELECT count(*) source_rows,
            count(*) FILTER (WHERE s.{left} = '') blank_source_keys,
            count(*) FILTER (WHERE k IS NULL AND s.{left} <> '') unmatched_source_rows,
            count(*) FILTER (WHERE n IS NOT NULL) matched_source_rows,
            count(*) FILTER (WHERE n > 1) source_rows_with_multiple_matches,
            coalesce(sum(coalesce(n, 1)), 0)::BIGINT left_join_rows,
            coalesce(sum(n), 0)::BIGINT inner_join_rows,
            coalesce(sum(greatest(coalesce(n, 1) - 1, 0)), 0)::BIGINT
            excess_left_join_rows
        FROM {source} s LEFT JOIN keys ON s.{left} = k
    """,
    )
    result["unmatched_examples"] = records(
        connection,
        f"""
        SELECT s.{left} value, count(*) count FROM {source} s
        WHERE s.{left} <> '' AND NOT EXISTS (
            SELECT 1 FROM {target} t WHERE t.{right} = s.{left})
        GROUP BY 1 ORDER BY count DESC, value LIMIT 5
    """,
    )
    result["target_key_duplicates"] = duplicate_keys(connection, target, target_key)
    result["source_column"], result["target_column"] = source_key, target_key
    return result
