"""Candidate join cardinalities and date-rate coverage, not execution mappings."""

from backend.profiling.statistics import (
    day,
    identifier,
    join_profile,
    number,
    one,
    records,
)

# Explicit hypotheses based on observed matching headers. No normalization or
# deduplication is applied; target multiplicities are measured, never repaired.
RELATIONSHIPS = (
    ("deal_contract", "deals", "Номер контракта", "contracts.csv", "Номер контракта"),
    ("deal_seller", "deals", "ИНН продавца", "participants.csv", "ИНН"),
    ("deal_buyer", "deals", "ИНН покупателя", "participants.csv", "ИНН"),
    ("deal_seller_broker", "deals", "Брокер продавца", "brokers.csv", "Код брокера"),
    ("deal_buyer_broker", "deals", "Брокер покупателя", "brokers.csv", "Код брокера"),
    ("contract_seller", "contracts.csv", "ИНН продавца", "participants.csv", "ИНН"),
    ("broker_inn_candidate", "brokers.csv", "ИНН", "participants.csv", "ИНН"),
)


def relationships(connection, tables: dict) -> dict:
    result = {}
    for name, source, source_key, target, target_key in RELATIONSHIPS:
        if source not in tables or target not in tables:
            result[name] = {
                "status": "unavailable",
                "reason": "missing validated source",
            }
            continue
        result[name] = {
            "status": "measured",
            **join_profile(
                connection, tables[source], source_key, tables[target], target_key
            ),
        }
    for name, source_key, target_key in (
        ("unsafe_seller_to_contract_seller", "ИНН продавца", "ИНН продавца"),
        (
            "unsafe_product_name_to_contract_name",
            "Наименование товара",
            "Наименование продукта",
        ),
    ):
        if "deals" in tables and "contracts.csv" in tables:
            result[name] = {
                "status": "measured",
                "candidate_only": True,
                "note": "Diagnostic unsafe alternative, not an approved relationship.",
                **join_profile(
                    connection,
                    tables["deals"],
                    source_key,
                    tables["contracts.csv"],
                    target_key,
                ),
            }
    return result


def product_variants(connection, tables: dict) -> dict:
    if "deals" not in tables:
        return {"status": "unavailable"}
    table = tables["deals"]
    result = one(
        connection,
        f"""
        WITH variants AS (
            SELECT "Номер контракта" k, count(DISTINCT "Наименование товара") n
            FROM {table} GROUP BY 1
        ) SELECT count(*) contract_keys,
            count(*) FILTER (WHERE n > 1) keys_with_multiple_exact_product_names,
            max(n) maximum_names_per_contract FROM variants
    """,
    )
    result["examples"] = records(
        connection,
        f"""
        SELECT "Номер контракта" contract_key,
            count(DISTINCT "Наименование товара") exact_product_names
        FROM {table} GROUP BY 1 HAVING count(DISTINCT "Наименование товара") > 1
        ORDER BY exact_product_names DESC, contract_key LIMIT 5
    """,
    )
    result["status"] = "measured"
    result["note"] = (
        "Exact names only; differences are not automatically aliases or errors."
    )
    return result


def rate_coverage(connection, tables: dict) -> dict:
    required = {"deals", "contracts.csv", "usd_rates.csv"}
    if not required <= tables.keys():
        return {"status": "unavailable", "reason": "missing validated source"}
    deals, contracts, rates = (
        tables[k] for k in ("deals", "contracts.csv", "usd_rates.csv")
    )
    deal_date, rate_date = day('d."Дата сделки"'), day('"Дата"')
    rate = number('"Курс"')
    cte = f"""
        WITH c AS (
            SELECT "Номер контракта" k, count(*) contract_rows,
                count(DISTINCT "Валюта") currency_labels, min("Валюта") currency
            FROM {contracts} GROUP BY 1
        ), r AS (
            SELECT {rate_date} rate_day, count(*) rate_rows,
                count(*) FILTER (WHERE ({rate}) > 0) positive_rates
            FROM {rates} GROUP BY 1
        ), coverage AS (
            SELECT {deal_date} deal_day, contract_rows, currency_labels, currency,
                rate_rows, positive_rates
            FROM {deals} d LEFT JOIN c ON d."Номер контракта" = c.k
            LEFT JOIN r ON {deal_date} = r.rate_day
        )
    """
    summary = one(
        connection,
        cte
        + """
        SELECT count(*) deal_rows,
            count(*) FILTER (WHERE deal_day IS NULL) invalid_deal_dates,
            count(*) FILTER (WHERE contract_rows IS NULL) missing_contract,
            count(*) FILTER (WHERE contract_rows > 1) ambiguous_contract_rows,
            count(*) FILTER (WHERE currency_labels <> 1 OR currency NOT IN
                ('Доллар США', 'Узбекский сум')) unsupported_currency_rows,
            count(*) FILTER (WHERE rate_rows IS NULL AND deal_day IS NOT NULL)
            all_deals_without_date_rate,
            count(*) FILTER (WHERE contract_rows = 1 AND currency = 'Доллар США')
            usd_deals,
            count(*) FILTER (WHERE contract_rows = 1 AND currency = 'Доллар США'
                AND deal_day IS NULL) usd_invalid_dates,
            count(*) FILTER (WHERE contract_rows = 1 AND currency = 'Доллар США'
                AND deal_day IS NOT NULL AND rate_rows IS NULL) usd_missing_rate,
            count(*) FILTER (WHERE contract_rows = 1 AND currency = 'Доллар США'
                AND rate_rows > 1) usd_duplicate_rate,
            count(*) FILTER (WHERE contract_rows = 1 AND currency = 'Доллар США'
                AND rate_rows = 1 AND positive_rates <> 1) usd_invalid_rate,
            count(*) FILTER (WHERE contract_rows = 1 AND currency = 'Доллар США'
                AND rate_rows = 1 AND positive_rates = 1) usd_rate_ready
        FROM coverage
    """,
    )
    summary["missing_date_examples"] = records(
        connection,
        cte
        + """
        SELECT deal_day::VARCHAR date, count(*) deals FROM coverage
        WHERE deal_day IS NOT NULL AND rate_rows IS NULL
        GROUP BY 1 ORDER BY date LIMIT 10
    """,
    )
    summary["rate_calendar"] = one(
        connection,
        f"""
        SELECT min({rate_date})::VARCHAR first_date, max({rate_date})::VARCHAR
        last_date,
            count(DISTINCT {rate_date}) distinct_parsed_dates,
            date_diff('day', min({rate_date}), max({rate_date})) + 1
                - count(DISTINCT {rate_date}) interior_missing_dates
        FROM {rates}
    """,
    )
    summary["status"] = "measured"
    summary["currency_labels"] = {"USD": "Доллар США", "UZS": "Узбекский сум"}
    summary["note"] = (
        "Exact observed contract labels only; no rates applied or amounts combined."
    )
    return summary


def deal_checks(connection, table: str) -> dict:
    quantity, delivered, lot = (
        number(identifier(c)) for c in ("Количество", "Поставлено", "Лот")
    )
    result = one(
        connection,
        f"""
        SELECT count(*) FILTER (WHERE ({quantity}) <= 0) nonpositive_quantity,
            count(*) FILTER (WHERE ({lot}) <= 0) nonpositive_lot_size,
            count(*) FILTER (WHERE ({delivered}) > ({quantity})) over_delivered,
            count(*) FILTER (WHERE ({delivered}) < 0) negative_delivered,
            count(*) FILTER (WHERE {day(identifier("Дата оплаты"))}
                < {day(identifier("Дата сделки"))}) payment_before_deal,
            count(*) FILTER (WHERE {day(identifier("Дата поставки"))}
                < {day(identifier("Дата сделки"))}) delivery_before_deal
        FROM {table}
    """,
    )
    result["status_vs_delivery"] = records(
        connection,
        f"""
        SELECT "Состояние сделки" status,
            CASE WHEN ({quantity}) <= 0 OR ({quantity}) IS NULL OR ({delivered}) IS NULL
                OR ({delivered}) < 0 OR ({delivered}) > ({quantity}) THEN 'undefined'
            WHEN ({delivered}) = ({quantity}) THEN 'fully_delivered'
            WHEN ({delivered}) = 0 THEN 'not_delivered' ELSE 'partially_delivered'
            END delivery,
            count(*) count
        FROM {table} GROUP BY 1, 2 ORDER BY 1, 2
    """,
    )
    result["note"] = (
        "Delivery quantities do not establish payment "
        "completion or override official status."
    )
    return result


def combined_join_risk(connection, tables: dict) -> dict:
    edges = [edge for edge in RELATIONSHIPS if edge[1] == "deals"]
    if (
        not {"deals", "contracts.csv", "participants.csv", "brokers.csv"}
        <= tables.keys()
    ):
        return {"status": "unavailable"}
    ctes, joins, factors = [], [], []
    for index, (_, _, source_key, target, target_key) in enumerate(edges):
        ctes.append(
            f"k{index} AS (SELECT {identifier(target_key)} k, count(*) n "
            f"FROM {tables[target]} WHERE {identifier(target_key)} <> '' GROUP BY 1)"
        )
        joins.append(f"LEFT JOIN k{index} ON d.{identifier(source_key)} = k{index}.k")
        factors.append(f"coalesce(k{index}.n, 1)")
    result = one(
        connection,
        "WITH "
        + ", ".join(ctes)
        + f" SELECT count(*) deal_rows, sum({' * '.join(factors)})::BIGINT "
        f"naive_combined_left_join_rows FROM {tables['deals']} d " + " ".join(joins),
    )
    result["excess_rows"] = (
        result["naive_combined_left_join_rows"] - result["deal_rows"]
    )
    result["status"] = "measured"
    result["note"] = (
        "Five exact-key joins (contract, seller, buyer, "
        "two broker roles); no deduplication."
    )
    return result
