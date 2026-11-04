"""Deterministic typed tables, with explicit unresolved derivations."""

from backend.ingestion.mappings import (
    DELIVERY_COMPLETION,
    KEYS,
    MAPPINGS,
    currency,
    unit,
)
from backend.ingestion.sources import BuildError
from backend.profiling.statistics import identifier


def create_typed_tables(connection) -> None:
    for table, fields in MAPPINGS.items():
        for field in fields:
            if field.kind == "text":
                continue
            failures = connection.execute(
                f"SELECT count(*) FROM raw.{table} r WHERE "
                f"r.{identifier(field.source)} <> '' AND ({field.expression()}) IS NULL"
            ).fetchone()[0]
            if failures:
                raise BuildError(
                    f"{table}.{field.target}: {failures} nonempty parsing failures"
                )
        projection = ", ".join(f"{f.expression()} AS {f.target}" for f in fields)
        connection.execute(
            f"CREATE TABLE main.{table} AS SELECT "
            f"source_file, source_record, {projection} FROM raw.{table} r"
        )
        connection.execute(f"ALTER TABLE main.{table} ADD PRIMARY KEY ({KEYS[table]})")
    # Lookup rows must already be unique before enrichment. There is deliberately
    # no join on broker INNs, names, or company/warehouse region labels.
    connection.execute(f"""
        CREATE TABLE main.deals_enriched AS
        SELECT d.*, c.currency_source, {currency("c.currency_source")} AS currency,
            c.source_file AS contract_source_file, c.source_record AS
            contract_source_record,
            {unit("d.measurement_unit_source")} AS measurement_unit,
            d.deal_quantity_lots * d.lot_size AS physical_volume,
            {DELIVERY_COMPLETION} AS delivery_completion,
            r.usd_uzs_rate AS usd_rate_on_deal_date,
            r.source_file AS rate_source_file, r.source_record AS rate_source_record,
            NULL::DECIMAL(38,10) AS fx_rate_used,
            CASE WHEN {currency("c.currency_source")} = 'UZS'
                 THEN d.transaction_amount END AS transaction_amount_uzs,
            CASE {currency("c.currency_source")}
                 WHEN 'UZS' THEN 'native_uzs'
                 WHEN 'USD' THEN 'unverified_conversion_semantics'
                 ELSE 'unknown_currency' END AS conversion_status
        FROM main.deals d
        LEFT JOIN main.contracts c ON d.contract_id = c.contract_id
        LEFT JOIN main.usd_rates r ON d.deal_date = r.rate_date
    """)
    connection.execute("DROP TABLE main.deals")
    connection.execute("ALTER TABLE main.deals_enriched RENAME TO deals")
    connection.execute("ALTER TABLE main.deals ADD PRIMARY KEY (deal_id)")
