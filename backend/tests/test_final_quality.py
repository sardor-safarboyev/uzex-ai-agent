"""Final user regressions; independent read-only expectations and mocked Groq."""

import json
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_analytics_reliability import invoke

from backend.config import Settings
from backend.interpretation.templates import template_plan
from backend.main import create_app
from backend.profiling.csv_scan import fingerprint
from backend.semantic.models import QueryPlan

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data/processed/uzex.duckdb"
COMPLEX = (
    "2024 va 2025-yillarda UZS valyutasidagi bitimlar sonini alohida ko‘rsat "
    "va qaysi yilda ko‘proq bo‘lganini aniqlang."
)
pytestmark = pytest.mark.skipif(
    not DATABASE.is_file(), reason="Local snapshot required"
)


@pytest.fixture(scope="module", autouse=True)
def unchanged_inputs():
    paths = [DATABASE, *(ROOT / "data/raw").glob("*.csv")]
    before = {path: fingerprint(path) for path in paths}
    yield
    assert {path: fingerprint(path) for path in paths} == before


def reference(sql, parameters=()):
    with duckdb.connect(str(DATABASE), read_only=True) as connection:
        return connection.execute(sql, parameters).fetchall()


def ask(question, language="auto"):
    # Templates and availability must function without a provider key.
    with TestClient(create_app(Settings(database_path=DATABASE))) as client:
        response = client.post(
            "/api/ask", json={"question": question, "language": language}
        )
        assert response.status_code == 200, response.text
        return response.json()


def rows(result):
    assert result["status"] == "answered", result
    return result["execution"]["result"]["outcome"]["data"]["rows"]


def test_currency_comparison_reproduction_and_fix():
    # Before the fix neither money on count nor a currency Filter was allowed.
    # The latter remains forbidden; explicit source currency is now supported.
    plan = template_plan(COMPLEX)
    assert plan.request.aggregate.money.source_currency == "UZS"
    invalid = plan.model_dump(mode="json")
    invalid["request"]["aggregate"]["money"] = None
    invalid["request"]["aggregate"]["filters"] = [
        {
            "field": "currency",
            "operator": "eq",
            "values": ["UZS"],
            "value_kind": "normalized",
        }
    ]
    result = invoke(COMPLEX, invalid).json()
    assert result["error"] == "invalid_response"
    assert result["execution"] is None
    assert "Savolni aniqroq" not in result["answer"]

    expected = reference(
        "SELECT year(d.deal_date), count(*) FROM deals d JOIN contracts c "
        "ON d.contract_id=c.contract_id WHERE year(d.deal_date) IN (2024,2025) "
        "AND c.currency_source=? GROUP BY 1 ORDER BY 1",
        ["Узбекский сум"],
    )
    assert expected == [(2024, 105320), (2025, 114396)]
    result = ask(COMPLEX)
    assert rows(result) == [[expected[0][1], expected[1][1], 9076]]
    assert "105 320" in result["answer"] and "9 076" in result["answer"]
    assert "2025" in result["answer"] and "UZS" in result["answer"]
    # The provider path accepts the same valid plan, without changing filters.
    assert invoke(COMPLEX, plan.model_dump(mode="json")).json() == result


@pytest.mark.parametrize("year", [2021, 2027, 2028])
@pytest.mark.parametrize("language", ["uz", "ru"])
def test_years_outside_verified_coverage(year, language):
    question = (
        f"{year}-yilda UZEX orqali nechta bitim tuzilgan?"
        if language == "uz"
        else f"Сколько сделок за {year} год?"
    )
    result = ask(question)
    assert result["language"] == language
    assert result["status"] == "insufficient_data"
    assert result["reason"] == "outside_coverage"
    assert result["error"] is None and result["execution"] is None
    assert result["availability"] == {
        "available_years": [2022, 2023, 2024, 2025, 2026],
        "missing_years": [year],
    }
    assert "2022–2026" in result["answer"] and str(year) in result["answer"]
    assert "0 ta" not in result["answer"]


def test_coverage_respects_override_and_valid_years():
    result = ask("2028-yilda nechta bitim tuzilgan?", "ru")
    assert result["language"] == "ru" and "Данных" in result["answer"]
    counts = []
    for year in range(2022, 2027):
        count = rows(ask(f"{year}-yilda UZEX orqali nechta bitim tuzilgan?"))[0][0]
        assert (
            count
            == reference("SELECT count(*) FROM deals WHERE year(deal_date)=?", [year])[
                0
            ][0]
        )
        counts.append(count)
    assert counts == [84299, 93985, 106647, 115763, 99306]
    assert sum(counts) == rows(ask("Сколько всего сделок?"))[0][0] == 500000


def test_combined_currency_year_region_and_bound_source_text():
    expected = reference(
        "SELECT count(*) FROM deals d JOIN contracts c ON d.contract_id=c.contract_id "
        "WHERE year(d.deal_date)=? AND c.currency_source=? "
        "AND d.warehouse_region_source=?",
        [2024, "Узбекский сум", "Toshkent shahri"],
    )[0][0]
    question = (
        "2024-yilda UZS valyutasidagi bitimlar soni, ombor hududi: Toshkent shahri"
    )
    result = ask(question)
    assert rows(result) == [[expected]]
    assert result["execution"]["scope"]["request"]["filters"][0]["values"] == [
        "Toshkent shahri"
    ]
    # SQL-looking region text remains a bound source value, never an OR clause.
    injection = ask(question + "' OR 1=1 --")
    assert injection["status"] == "no_match"
    assert injection["execution"]["result"]["coverage"]["matched_rows"] == 0


@pytest.mark.parametrize("count", [5, 10])
def test_product_rankings_intentionally_limited(count):
    expected = reference(
        "SELECT product_name,count(*) n FROM deals WHERE year(deal_date)=2025 "
        "GROUP BY 1 ORDER BY n DESC,1 LIMIT ?",
        [count],
    )
    result = ask(f"2025-yilda bitimlar soni bo‘yicha top {count} mahsulot")
    assert rows(result) == [list(row) for row in expected]
    assert not result["execution"]["truncated"]
    assert not any(
        "Additional groups" in warning for warning in result["execution"]["warnings"]
    )


def test_region_leader_and_unfiltered_comparison_summaries():
    result = ask("2023-yilda qaysi hududda eng ko'p bitim tuzilgan?")
    assert rows(result) == [["Toshkent shahri", 14856]]
    assert not result["execution"]["truncated"]
    assert "14 856" in result["answer"] and "Toshkent shahri" in result["answer"]
    result = ask("Сравни количество сделок за 2024 и 2025 годы.")
    assert rows(result) == [[106647, 115763, 9116]]
    assert "9 116" in result["answer"] and result["language"] == "ru"
    assert "строк" not in result["answer"]


@pytest.mark.parametrize(
    "question,reason,status",
    [
        (
            "2025-yilda kompaniyalarning sof foydasi qancha?",
            "unavailable_profit",
            "insufficient_data",
        ),
        (
            "2024-yilda kompaniyalarda nechta xodim ishlagan?",
            "unavailable_employees",
            "insufficient_data",
        ),
        (
            "2025-yilda qaysi broker eng ko‘p soliq to‘lagan?",
            "unavailable_tax",
            "insufficient_data",
        ),
        (
            "2024-yilda barcha USD bitimlarini UZS ga aylantir.",
            "currency_conversion",
            "unsupported",
        ),
        (
            "2025-yilda eng ko‘p sotilgan mahsulot nima sababdan yetakchi bo‘lgan?",
            "unsupported_causality",
            "unsupported",
        ),
        (
            "2025-yilda bitim qiymatining medianasi qancha?",
            "unsupported_statistic",
            "unsupported",
        ),
        ("2027-yil uchun prognoz", "outside_coverage", "insufficient_data"),
    ],
)
def test_specific_missing_fields_and_unsupported_operations(question, reason, status):
    result = ask(question)
    assert result["status"] == status and result["reason"] == reason
    assert result["error"] is None
    assert "aniqlashtiring" not in result["answer"]


def test_money_scope_strictness_and_currency_clarification():
    result = ask("2024-yildagi bitimlarning umumiy qiymati qancha?")
    assert result["status"] == "ambiguous" and result["reason"] == "currency"
    assert "UZS yoki USD" in result["answer"]
    assert "sana" not in result["answer"] and "mahsulot" not in result["answer"]
    valid = template_plan(COMPLEX).model_dump(mode="json")
    for money in (
        {"mode": "convert_to_uzs"},
        {"mode": "source"},
        {"mode": "source", "source_currency": "EUR"},
    ):
        value = json.loads(json.dumps(valid))
        value["request"]["aggregate"]["money"] = money
        with pytest.raises(ValidationError):
            QueryPlan.model_validate(value)


def test_provider_failures_remain_distinct_and_safe():
    question = "Покажи число сделок за 2024 год по складам"
    for status, error in [
        (429, "rate_limit"),
        (401, "provider_error"),
        (200, "invalid_response"),
    ]:
        result = invoke(question, {"sql": "SELECT secret"}, status=status).json()
        assert result["status"] == "error" and result["error"] == error
        assert result["execution"] is None
        assert "secret" not in result["answer"] and "Уточните" not in result["answer"]


@pytest.mark.parametrize(
    "body",
    [
        {"question": "", "language": "ru"},
        {"question": "x" * 4001},
        {"question": "Count", "sql": "SELECT secret"},
        {"question": {}, "language": []},
    ],
)
def test_invalid_input_is_structured_and_never_echoed(body):
    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/ask", json=body)
    assert response.status_code == 422
    result = response.json()
    assert result["status"] == "error" and result["error"] == "invalid_input"
    assert "secret" not in response.text and "detail" not in result
    if body.get("language") == "ru":
        assert result["language"] == "ru"


def test_russian_currency_comparison_and_source_totals():
    result = ask("Сравни количество сделок в UZS за 2024 и 2025 годы.")
    assert rows(result) == [[105320, 114396, 9076]]
    assert "Больше сделок в 2025" in result["answer"]
    for currency, source in [("UZS", "Узбекский сум"), ("USD", "Доллар США")]:
        expected = reference(
            "SELECT sum(d.transaction_amount) FROM deals d JOIN contracts c "
            "ON d.contract_id=c.contract_id WHERE year(d.deal_date)=2024 "
            "AND c.currency_source=?",
            [source],
        )[0][0]
        result = ask(f"Общая сумма сделок в {currency} за 2024 год.")
        from decimal import Decimal

        assert Decimal(rows(result)[0][0]) == expected
        assert (
            result["execution"]["result"]["outcome"]["data"]["columns"][0]["currency"]
            == currency
        )
    assert rows(ask("Топ 10 товаров по количеству сделок за 2025 год.")) == [
        list(row)
        for row in reference(
            "SELECT product_name,count(*) n FROM deals WHERE year(deal_date)=2025 "
            "GROUP BY 1 ORDER BY n DESC,1 LIMIT 10"
        )
    ]


def test_coverage_does_not_treat_region_value_as_another_date():
    from backend.api.availability import requested_years

    assert requested_years("2024-yilda ombor hududi: 2028") == {2024}
    assert requested_years(COMPLEX) == {2024, 2025}
    assert requested_years("deal_id 2028") == set()
