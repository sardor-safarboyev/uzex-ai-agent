"""Independent raw-source reconciliation against the real local immutable snapshot."""

import json
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import duckdb
import pytest

from backend.config import Settings
from backend.profiling.csv_scan import fingerprint
from backend.query import QueryEngine
from backend.semantic.models import QueryPlan

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data" / "processed" / "uzex.duckdb"
pytestmark = pytest.mark.skipif(
    not DATABASE.is_file(), reason="Real local snapshot is not supplied on CI"
)
OBSERVED = []


def reference(sql, params=()):
    # A separate read-only connection, hand-written SQL and raw audit strings;
    # no compiler expression or mapper is reused to calculate expectations.
    with duckdb.connect(str(DATABASE), read_only=True) as connection:
        return connection.execute(sql, params).fetchall()


def request(**changes):
    return QueryPlan.model_validate(
        {
            "version": "1.1",
            "language": "uz",
            "request": {
                "kind": "aggregate",
                "metrics": ["deal_count"],
                **changes,
            },
        }
    )


def execute(plan):
    return QueryEngine(Settings(database_path=DATABASE)).execute(plan)


def answer(plan):
    response = execute(plan)
    assert response.result.outcome.status == "answered", response.result.outcome
    return response.result.outcome.data.rows


@pytest.fixture(scope="module", autouse=True)
def immutable_snapshot_and_report(request):
    before = fingerprint(DATABASE)
    manifest = ROOT / "data" / "reports" / "profile.json"
    source_hashes = json.loads(manifest.read_text())["files"]
    failed_before = request.session.testsfailed
    yield
    assert fingerprint(DATABASE) == before
    assert all(
        fingerprint(ROOT / "data" / "raw" / name)["sha256"] == data["sha256"]
        for name, data in source_hashes.items()
    )
    report = {
        "status": "passed"
        if request.session.testsfailed == failed_before
        else "failed",
        "database": before,
        "database_unchanged": True,
        "sources_unchanged": True,
        "reconciliations": OBSERVED,
    }
    directory = ROOT / "data" / "reports"
    directory.mkdir(exist_ok=True)
    (directory / "query-integration.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Read-only query integration",
        "",
        f"Status: **{report['status']}**.",
        "",
        "Database and all nine source hashes remained unchanged.",
        "",
        "| Independent reconciliation | Measured result |",
        "| --- | --- |",
    ]
    lines += [
        (
            f"| {row['check']} | "
            f"{json.dumps(row['actual'], ensure_ascii=False, default=str)} "
            f"|"
        )
        for row in OBSERVED
    ]
    (directory / "query-integration.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


@pytest.mark.parametrize("year", range(2022, 2027))
def test_transaction_counts_by_year(year):
    expected = reference(
        "SELECT count(*) FROM raw.deals WHERE source_file = ?", [f"deals_{year}.csv"]
    )[0][0]
    actual = answer(
        request(date_range={"start": f"{year}-01-01", "end": f"{year}-12-31"})
    )
    assert actual == [[expected]]
    OBSERVED.append({"check": f"deals_{year}", "actual": expected})


def test_official_statuses_and_delivery_are_independent():
    expected = reference(
        'SELECT "Состояние сделки", count(*) FROM raw.deals GROUP BY 1 ORDER BY 1'
    )
    actual = answer(request(group_by=["status"]))
    assert actual == [list(row) for row in expected]
    paid = execute(
        request(
            metrics=["delivered_lots"],
            filters=[{"field": "status", "operator": "eq", "values": ["Оплачен"]}],
        )
    )
    assert paid.result.outcome.status == "insufficient_data"
    completed = reference(
        
            'SELECT count(*) FROM raw.deals WHERE "Поставлено" '
            "<> '' AND cast(\"Поставлено\" AS DECIMAL(38,10)) "
            '= cast("Количество" AS DECIMAL(38,10))'
        
    )[0][0]
    assert answer(
        request(
            filters=[
                {
                    "field": "delivery_completion",
                    "operator": "eq",
                    "value_kind": "normalized",
                    "values": ["fully_delivered"],
                }
            ]
        )
    ) == [[completed]]
    OBSERVED.append({"check": "official_statuses", "actual": actual})
    OBSERVED.append({"check": "fully_delivered", "actual": completed})


def test_contract_currency_joins_and_source_amounts():
    expected = reference("""
        SELECT CASE c."Валюта" WHEN 'Доллар США' THEN 'USD' ELSE 'UZS' END currency,
            sum(cast(replace(d."Сумма сделки", ' ', '') AS DECIMAL(38,10)))
        FROM raw.deals d JOIN raw.contracts c ON d."Номер контракта" =
        c."Номер контракта"
        GROUP BY 1 ORDER BY 1
    """)
    actual = answer(
        request(metrics=["deal_value"], money={"mode": "source"}, group_by=["currency"])
    )
    assert actual == [list(row) for row in expected]
    joined = reference(
        
            "SELECT count(*) FROM raw.deals d JOIN "
            'raw.contracts c ON d."Номер контракта" = c."Номер '
            'контракта"'
        
    )[0][0]
    assert joined == answer(request())[0][0] == 500000
    OBSERVED.append({"check": "exact_contract_join_rows", "actual": joined})
    OBSERVED.append({"check": "separate_source_currency_totals", "actual": actual})


def test_usd_rate_evidence_and_explicit_conversion_rejection():
    matched, valid = reference("""
        SELECT count(*), count(*) FILTER (WHERE cast(r."Курс" AS DECIMAL(38,10)) > 0)
        FROM raw.deals d JOIN raw.contracts c ON d."Номер контракта" =
        c."Номер контракта"
        JOIN raw.usd_rates r ON strptime(d."Дата сделки", '%d.%m.%Y') =
        strptime(r."Дата", '%d.%m.%Y')
        WHERE c."Валюта" = 'Доллар США'
    """)[0]
    assert matched == valid == 6590
    unsupported = execute(
        request(metrics=["deal_value"], money={"mode": "convert_to_uzs"})
    )
    assert unsupported.result.outcome.status == "unsupported"
    assert reference(
        
            "SELECT count(*) FROM main.deals WHERE currency = "
            "'USD' AND (fx_rate_used IS NOT NULL OR "
            "transaction_amount_uzs IS NOT NULL)"
        
    ) == [(0,)]
    OBSERVED.append({"check": "USD_date_rate_coverage", "actual": matched})
    OBSERVED.append(
        {"check": "USD_conversion", "actual": unsupported.result.outcome.status}
    )


@pytest.mark.parametrize("target", ["kg", "tonne"])
def test_exact_unit_aware_mass_conversion(target):
    totals = dict(
        reference("""
        SELECT "Единица измерения", sum(cast("Количество" AS DECIMAL(38,10)) *
        cast("Лот" AS DECIMAL(38,10)))
        FROM raw.deals WHERE "Единица измерения" IN ('килограмм', 'тонна') GROUP BY 1
    """)
    )
    with localcontext() as context:
        context.prec = 60
        expected = totals["килограмм"] + totals["тонна"] * 1000
        if target == "tonne":
            expected *= Decimal("0.001")
    actual = answer(
        request(
            metrics=["physical_volume"], units={"mode": "convert_mass", "unit": target}
        )
    )
    assert actual == [[expected]]
    assert isinstance(actual[0][0], Decimal)
    OBSERVED.append({"check": f"mass_in_{target}", "actual": actual[0][0]})


def test_unsupported_unit_rows_still_support_count_and_money():
    name = reference(
        
            'SELECT min("Наименование товара") FROM raw.deals '
            "WHERE \"Единица измерения\" = 'метр'"
        
    )[0][0]
    count = reference(
        'SELECT count(*) FROM raw.deals WHERE "Наименование товара" = ?', [name]
    )[0][0]
    filters = [{"field": "product", "operator": "eq", "values": [name]}]
    assert answer(request(filters=filters)) == [[count]]
    money = answer(
        request(
            metrics=["deal_value"],
            money={"mode": "source"},
            group_by=["currency"],
            filters=filters,
        )
    )
    expected = reference(
        """
        SELECT CASE c."Валюта" WHEN 'Доллар США' THEN 'USD' ELSE 'UZS' END,
            sum(cast(replace(d."Сумма сделки", ' ', '') AS DECIMAL(38,10)))
        FROM raw.deals d JOIN raw.contracts c ON d."Номер контракта" =
        c."Номер контракта"
        WHERE d."Наименование товара" = ? GROUP BY 1 ORDER BY 1
    """,
        [name],
    )
    assert money == [list(row) for row in expected]
    rejected = execute(
        request(
            metrics=["physical_volume"],
            units={"mode": "group_by_unit"},
            group_by=["measurement_unit"],
            filters=filters,
        )
    )
    assert rejected.result.outcome.status == "unsupported"
    OBSERVED.append({"check": "unsupported_unit_safe_count", "actual": count})


def test_weighted_price_ranking_reconciles_raw_sums_exactly():
    source = reference("""
        SELECT d."Наименование товара",
            sum(cast(replace(d."Сумма сделки", ' ', '') AS DECIMAL(38,10))),
            sum(cast(d."Количество" AS DECIMAL(38,10)) * cast(d."Лот" AS
            DECIMAL(38,10)))
        FROM raw.deals d JOIN raw.contracts c ON d."Номер контракта" =
        c."Номер контракта"
        WHERE c."Валюта" = 'Узбекский сум' AND d."Единица измерения" = 'килограмм'
        GROUP BY 1
    """)
    ordered = sorted(
        source, key=lambda row: (-Fraction(row[1]) / Fraction(row[2]), row[0])
    )[:3]
    with localcontext() as context:
        context.prec = 38
        expected = [
            [
                name,
                Decimal((Fraction(amount) / Fraction(volume)).numerator)
                / Decimal((Fraction(amount) / Fraction(volume)).denominator),
            ]
            for name, amount, volume in ordered
        ]
    actual = answer(
        request(
            metrics=["average_unit_price"],
            group_by=["product"],
            money={"mode": "source", "source_currency": "UZS"},
            units={"mode": "single", "unit": "kg"},
            ranking={"metric": "average_unit_price", "direction": "top", "count": 3},
        )
    )
    assert actual == expected
    OBSERVED.append({"check": "weighted_price_exact_top3", "actual": actual})


def test_missing_values_exact_lookup_and_no_match():
    missing = reference("SELECT count(*) FROM raw.deals WHERE \"Поставлено\" = ''")[0][
        0
    ]
    assert missing == 46291
    assert (
        execute(request(metrics=["delivered_lots"])).result.outcome.status
        == "insufficient_data"
    )
    identifier = reference(
        
            'SELECT "Номер сделки" FROM raw.deals WHERE '
            '"Поставлено" = \'\' ORDER BY "Номер сделки" LIMIT '
            "1"
        
    )[0][0]
    lookup = QueryPlan.model_validate(
        {
            "version": "1.1",
            "language": "ru",
            "request": {
                "kind": "lookup",
                "deal_id": identifier,
                "select": [
                    "deal_id",
                    "status",
                    "delivery_completion",
                    "delivered_lots",
                ],
            },
        }
    )
    response = execute(lookup)
    assert response.result.outcome.status == "answered"
    assert response.result.outcome.data.rows[0][2:] == [None, None]
    no_match = execute(
        request(
            filters=[
                {
                    "field": "product",
                    "operator": "eq",
                    "values": ["' OR 1=1; DROP TABLE main.deals; --"],
                }
            ]
        )
    )
    assert no_match.result.outcome.status == "no_match"
    OBSERVED.append({"check": "missing_delivered_values_preserved", "actual": missing})


def test_count_period_comparison_against_raw_files():
    baseline = reference(
        "SELECT count(*) FROM raw.deals WHERE source_file = 'deals_2022.csv'"
    )[0][0]
    target = reference(
        "SELECT count(*) FROM raw.deals WHERE source_file = 'deals_2023.csv'"
    )[0][0]
    comparison = QueryPlan.model_validate(
        {
            "version": "1.1",
            "language": "uz",
            "request": {
                "kind": "comparison",
                "baseline": {"start": "2022-01-01", "end": "2022-12-31"},
                "target": {"start": "2023-01-01", "end": "2023-12-31"},
                "aggregate": {"kind": "aggregate", "metrics": ["deal_count"]},
                "changes": ["absolute_difference", "percentage_change"],
            },
        }
    )
    with localcontext() as context:
        context.prec = 38
        percentage = Decimal((target - baseline) * 100) / baseline
    actual = answer(comparison)
    assert actual == [[baseline, target, target - baseline, percentage]]
    OBSERVED.append({"check": "period_comparison_2022_2023", "actual": actual[0]})


def test_broker_roles_and_lookup_keys_preserve_grain():
    for role, source in [
        ("seller_broker_code", "Брокер продавца"),
        ("buyer_broker_code", "Брокер покупателя"),
    ]:
        expected = reference(
            f'SELECT "{source}", count(*) FROM raw.deals GROUP BY 1 ORDER BY 1'
        )
        actual = answer(request(group_by=[role], limit=1000))
        assert actual == [list(row) for row in expected]
        assert sum(row[1] for row in actual) == 500000
        OBSERVED.append(
            {"check": role, "actual": {"groups": len(actual), "deals": 500000}}
        )


def test_missing_delivery_is_not_classified_as_not_delivered():
    expected = reference("""
        SELECT CASE WHEN "Поставлено" = '' THEN NULL
            WHEN cast("Поставлено" AS DECIMAL(38,10)) = cast("Количество" AS
            DECIMAL(38,10))
                THEN 'fully_delivered'
            WHEN cast("Поставлено" AS DECIMAL(38,10)) = 0 THEN 'not_delivered'
            ELSE 'partially_delivered' END completion, count(*)
        FROM raw.deals GROUP BY 1 ORDER BY 1 NULLS LAST
    """)
    actual = answer(request(group_by=["delivery_completion"]))
    assert actual == [list(row) for row in expected]
    assert [row for row in actual if row[0] is None] == [[None, 46291]]
    OBSERVED.append(
        {"check": "delivery_completion_with_unknown_bucket", "actual": actual}
    )
