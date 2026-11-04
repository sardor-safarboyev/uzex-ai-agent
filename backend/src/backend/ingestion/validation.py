"""Repeatable checks against source bytes, every raw field, and typed derivations."""

from backend.ingestion.mappings import (
    DELIVERY_COMPLETION,
    KEYS,
    MAPPINGS,
    currency,
    unit,
)
from backend.ingestion.sources import verify_raw_source
from backend.profiling.statistics import identifier, records

JOINS = (
    ("deal_contract", "deals", "contract_id", "contracts", "contract_id"),
    ("deal_seller", "deals", "seller_inn", "participants", "inn"),
    ("deal_buyer", "deals", "buyer_inn", "participants", "inn"),
    ("deal_seller_broker", "deals", "seller_broker_code", "brokers", "broker_code"),
    ("deal_buyer_broker", "deals", "buyer_broker_code", "brokers", "broker_code"),
    ("contract_seller", "contracts", "seller_inn", "participants", "inn"),
)


def validate(connection, raw, manifest: dict, expected_deals: int) -> dict:
    checks = []

    def check(name, actual, expected=0):
        checks.append(
            {
                "name": name,
                "actual": actual,
                "expected": expected,
                "passed": actual == expected,
            }
        )

    def count(sql, parameters=None):
        return connection.execute(sql, parameters or []).fetchone()[0]

    source_counts = {}
    for name, entry in manifest["files"].items():
        table = "deals" if name.startswith("deals_") else name.removesuffix(".csv")
        source_counts[name] = count(
            f"SELECT count(*) FROM main.{table} WHERE source_file = ?", [name]
        )
        check(f"{name}:typed_count", source_counts[name], entry["row_count"])
        check(
            f"{name}:raw_count",
            count(f"SELECT count(*) FROM raw.{table} WHERE source_file = ?", [name]),
            entry["row_count"],
        )
        check(
            f"{name}:all_source_fields_reconcile",
            verify_raw_source(connection, raw, name, entry),
        )
        row = connection.execute(
            "SELECT sha256, size_bytes, record_count FROM "
            "audit.source_files WHERE source_file = ?",
            [name],
        ).fetchone()
        check(
            f"{name}:stored_manifest",
            row == (entry["sha256"], entry["size_bytes"], entry["row_count"]),
            True,
        )
    check(
        "source_manifest_records", count("SELECT count(*) FROM audit.source_files"), 9
    )
    counts = {}
    for table, fields in MAPPINGS.items():
        expected = (
            expected_deals
            if table == "deals"
            else manifest["files"][f"{table}.csv"]["row_count"]
        )
        counts[table] = count(f"SELECT count(*) FROM main.{table}")
        check(f"{table}:total_count", counts[table], expected)
        key = KEYS[table]
        check(
            f"{table}:null_or_empty_identifier",
            count(
                f"SELECT count(*) FROM main.{table} WHERE {key} IS "
                f"NULL OR cast({key} AS VARCHAR) = ''"
            ),
        )
        check(
            f"{table}:duplicate_identifiers",
            count(f"SELECT count(*) - count(DISTINCT {key}) FROM main.{table}"),
        )
        check(
            f"{table}:duplicate_provenance",
            count(
                f"SELECT count(*) - count(DISTINCT (source_file, "
                f"source_record)) FROM main.{table}"
            ),
        )
        check(
            f"{table}:unmatched_provenance",
            count(
                f"SELECT count(*) FROM main.{table} t LEFT JOIN "
                f"raw.{table} r USING (source_file, source_record) "
                f"WHERE r.source_record IS NULL"
            ),
        )
        conditions = " OR ".join(
            f"t.{field.target} IS DISTINCT FROM ({field.expression()})"
            for field in fields
        )
        check(
            f"{table}:typed_source_reconciliation",
            count(
                f"SELECT count(*) FROM main.{table} t JOIN "
                f"raw.{table} r USING (source_file, source_record) "
                f"WHERE {conditions}"
            ),
        )
        if table != "deals":
            for field in fields:
                if field.kind != "text":
                    check(
                        f"{table}:{field.target}:nonempty_parse_failures",
                        count(
                            f"SELECT count(*) FROM raw.{table} r WHERE "
                            f"r.{identifier(field.source)} <> '' AND "
                            f"({field.expression()}) IS NULL"
                        ),
                    )
    join_counts = {}
    for name, source, source_key, target, target_key in JOINS:
        size = counts[source]
        matched = count(
            f"SELECT count(*) FROM main.{source} s JOIN "
            f"main.{target} t ON s.{source_key} = t.{target_key}"
        )
        left = count(
            f"SELECT count(*) FROM main.{source} s LEFT JOIN "
            f"main.{target} t ON s.{source_key} = t.{target_key}"
        )
        join_counts[name] = {
            "source_rows": size,
            "matched_rows": matched,
            "left_join_rows": left,
        }
        check(f"{name}:coverage", matched, size)
        check(f"{name}:cardinality", left, size)
    check(
        "combined_dimension_join_grain",
        count("""
        SELECT count(*) FROM main.deals d
        JOIN main.contracts c ON d.contract_id = c.contract_id
        JOIN main.participants s ON d.seller_inn = s.inn
        JOIN main.participants b ON d.buyer_inn = b.inn
        JOIN main.brokers sb ON d.seller_broker_code = sb.broker_code
        JOIN main.brokers bb ON d.buyer_broker_code = bb.broker_code
    """),
        expected_deals,
    )
    check(
        "positive_unique_rates",
        count(
            "SELECT count(*) FROM main.usd_rates WHERE "
            "usd_uzs_rate IS NULL OR usd_uzs_rate <= 0"
        ),
    )
    check(
        "physical_volume_exact_product",
        count(
            "SELECT count(*) FROM main.deals WHERE "
            "physical_volume IS DISTINCT FROM deal_quantity_lots "
            "* lot_size"
        ),
    )
    check(
        "delivery_completion_quantity_only",
        count(
            f"SELECT count(*) FROM main.deals WHERE "
            f"delivery_completion IS DISTINCT FROM "
            f"({DELIVERY_COMPLETION})"
        ),
    )
    check(
        "unit_label_mapping",
        count(
            f"SELECT count(*) FROM main.deals WHERE "
            f"measurement_unit IS DISTINCT FROM "
            f"({unit('measurement_unit_source')})"
        ),
    )
    check(
        "contract_currency_source",
        count(f"""
        SELECT count(*) FROM main.deals d JOIN main.contracts c USING (contract_id)
        WHERE d.currency_source IS DISTINCT FROM c.currency_source
           OR d.currency IS DISTINCT FROM ({currency("c.currency_source")})
           OR d.contract_source_file IS DISTINCT FROM c.source_file
           OR d.contract_source_record IS DISTINCT FROM c.source_record
    """),
    )
    check(
        "matched_rate_and_provenance",
        count("""
        SELECT count(*) FROM main.deals d LEFT JOIN main.usd_rates r ON d.deal_date
        = r.rate_date
        WHERE d.usd_rate_on_deal_date IS DISTINCT FROM r.usd_uzs_rate
           OR d.rate_source_file IS DISTINCT FROM r.source_file
           OR d.rate_source_record IS DISTINCT FROM r.source_record
    """),
    )
    check(
        "usd_rate_coverage",
        count(
            "SELECT count(*) FROM main.deals WHERE currency = "
            "'USD' AND (usd_rate_on_deal_date IS NULL OR "
            "usd_rate_on_deal_date <= 0)"
        ),
    )
    check(
        "no_unverified_conversion",
        count(
            "SELECT count(*) FROM main.deals WHERE fx_rate_used "
            "IS NOT NULL OR (currency IS DISTINCT FROM 'UZS' AND "
            "transaction_amount_uzs IS NOT NULL)"
        ),
    )
    check(
        "native_uzs_amount_preserved",
        count(
            "SELECT count(*) FROM main.deals WHERE currency = "
            "'UZS' AND transaction_amount_uzs IS DISTINCT FROM "
            "transaction_amount"
        ),
    )
    check(
        "conversion_status",
        count("""
        SELECT count(*) FROM main.deals WHERE conversion_status IS DISTINCT FROM
        CASE currency WHEN 'UZS' THEN 'native_uzs' WHEN 'USD' THEN
        'unverified_conversion_semantics'
        ELSE 'unknown_currency' END
    """),
    )
    exceptions = {
        "usd_conversion_deferred": count(
            "SELECT count(*) FROM main.deals WHERE currency = 'USD'"
        ),
        "unknown_currency": count(
            "SELECT count(*) FROM main.deals WHERE currency IS NULL"
        ),
        "unmapped_semantic_unit": count(
            "SELECT count(*) FROM main.deals WHERE measurement_unit IS NULL"
        ),
        "blank_payment_date": count(
            "SELECT count(*) FROM main.deals WHERE payment_date IS NULL"
        ),
        "blank_delivery_date": count(
            "SELECT count(*) FROM main.deals WHERE delivery_date IS NULL"
        ),
        "blank_delivered_lots": count(
            "SELECT count(*) FROM main.deals WHERE delivered_lots IS NULL"
        ),
        "undefined_delivery_completion": count(
            "SELECT count(*) FROM main.deals WHERE delivery_completion IS NULL"
        ),
        "contract_seller_disagreement": count(
            "SELECT count(*) FROM main.deals d JOIN "
            "main.contracts c USING (contract_id) WHERE "
            "d.seller_inn IS DISTINCT FROM c.seller_inn"
        ),
        "contract_lot_disagreement": count(
            "SELECT count(*) FROM main.deals d JOIN "
            "main.contracts c USING (contract_id) WHERE "
            "d.lot_size IS DISTINCT FROM c.lot_size"
        ),
        "contract_unit_disagreement": count(
            "SELECT count(*) FROM main.deals d JOIN "
            "main.contracts c USING (contract_id) WHERE "
            "d.measurement_unit_source IS DISTINCT FROM "
            "c.measurement_unit_source"
        ),
    }
    schemas = records(
        connection,
        """
        SELECT table_schema schema_name, table_name, column_name, data_type, is_nullable
        FROM information_schema.columns WHERE table_catalog = current_database()
        ORDER BY table_schema, table_name, ordinal_position
    """,
    )
    all_table_counts = {}
    for table in records(
        connection,
        """
        SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_catalog = current_database() AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
    """,
    ):
        schema, name = table["table_schema"], table["table_name"]
        all_table_counts[f"{schema}.{name}"] = count(
            f"SELECT count(*) FROM {identifier(schema)}.{identifier(name)}"
        )
    return {
        "all_table_counts": all_table_counts,
        "status": "passed" if all(c["passed"] for c in checks) else "failed",
        "checks": checks,
        "table_counts": counts,
        "source_counts": source_counts,
        "joins": join_counts,
        "exceptions": exceptions,
        "schema": schemas,
    }
