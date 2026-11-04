"""Small synthetic ingestion fixtures plus adversarial compiler/executor tests."""

from decimal import Decimal

import duckdb
import pytest
from pydantic import ValidationError
from test_ingestion import sources as sources

from backend.config import Settings
from backend.ingestion.builder import build_database
from backend.profiling.csv_scan import fingerprint
from backend.query import QueryEngine, QueryExecution
from backend.query.compiler import Statement, compile_plan
from backend.semantic.models import QueryPlan


def plan(kind="aggregate", **fields):
    if kind == "aggregate":
        fields = {"metrics": ["deal_count"], **fields}
    return QueryPlan.model_validate(
        {"version": "1.1", "language": "ru", "request": {"kind": kind, **fields}}
    )


@pytest.fixture
def engine(sources):
    report = build_database(*sources, expected_deals=5)
    assert report["status"] == "passed", report.get("failure")
    return QueryEngine(Settings(database_path=sources[2]))


def rows(response):
    assert response.result.outcome.status == "answered", response.result.outcome
    return response.result.outcome.data.rows


def test_basic_count_has_scope_evidence_and_round_trip(engine):
    result = engine.execute(plan())
    assert rows(result) == [[5]]
    assert result.result.coverage.matched_rows == 5
    assert result.result.coverage.evaluated_rows == 5
    assert result.returned_rows == 1
    assert result.scope.language == "ru"
    assert result.result.evidence
    assert QueryExecution.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "payload",
    [
        "SELECT * FROM deals",
        {"sql": "DROP TABLE deals"},
        Statement("DROP TABLE deals", ()),
        None,
    ],
)
def test_only_plan_objects_enter_execution(payload):
    response = QueryEngine(Settings()).execute(payload)
    assert response.result.outcome.status == "error"
    assert response.result.outcome.code == "validation_failed"


def test_mutated_or_constructed_plans_are_revalidated():
    modified = plan()
    modified.request.metrics.append("sum(transaction_amount); DROP TABLE deals")
    result = QueryEngine(Settings()).execute(modified)
    assert result.result.outcome.status == "error"
    assert result.result.outcome.code == "validation_failed"


@pytest.mark.parametrize(
    "field", ["broker_code", "registration_region", "contract_id; DROP TABLE deals"]
)
def test_unknown_dimensions_are_invalid(field):
    with pytest.raises(ValidationError):
        plan(group_by=[field])


@pytest.mark.parametrize(
    "operator,values",
    [("eq", ["' OR 1=1 --"]), ("in", ["A'); DROP TABLE main.deals; --", "B"])],
)
def test_text_injection_is_bound_and_never_executable(
    engine, sources, operator, values
):
    request = plan(
        filters=[{"field": "product", "operator": operator, "values": values}]
    )
    compiled = compile_plan(request)[0]
    for value in values:
        assert value not in compiled.data.sql
        assert value in compiled.data.parameters
    before = fingerprint(sources[2])
    assert engine.execute(request).result.outcome.status == "no_match"
    assert fingerprint(sources[2]) == before
    assert rows(engine.execute(plan())) == [[5]]


def test_all_join_keys_are_exact_and_no_unsafe_join_can_be_requested():
    query = compile_plan(plan())[0].data.sql
    for edge in (
        "d.contract_id = c.contract_id",
        "d.seller_inn = seller.inn",
        "d.buyer_inn = buyer.inn",
        "d.seller_broker_code = sb.broker_code",
        "d.buyer_broker_code = bb.broker_code",
    ):
        assert edge in query
    assert "d.seller_inn = c.seller_inn" not in query
    assert "d.product_name = c.product_name" not in query
    assert "inn_source" not in query
    assert "raw." not in query


def test_identifiers_and_dates_are_bound(engine):
    request = plan(
        kind="lookup", deal_id="0002022", select=["deal_id", "seller_inn", "buyer_inn"]
    )
    query = compile_plan(request)[0]
    assert "0002022" not in query.data.sql
    assert "0002022" in query.data.parameters
    response = engine.execute(request)
    assert rows(response) == [["0002022", "001", "002"]]
    assert response.provenance[0].source_file == "deals_2022.csv"
    assert response.provenance[0].source_record == 1
    date_plan = plan(date_range={"start": "2022-01-01", "end": "2022-12-31"})
    assert "2022-01-01" not in compile_plan(date_plan)[0].data.sql
    assert rows(engine.execute(date_plan)) == [[1]]


def test_lookup_preserves_missing_delivery_and_official_status(engine):
    response = engine.execute(
        plan(
            kind="lookup",
            deal_id="0002024",
            select=["status", "delivery_completion", "delivered_lots"],
        )
    )
    assert rows(response) == [["Оплачен", None, None]]
    assert response.warnings
    assert (
        engine.execute(
            plan(kind="lookup", deal_id="not-present", select=["deal_id"])
        ).result.outcome.status
        == "no_match"
    )


def test_money_requires_currency_and_never_mixes_it(engine):
    with pytest.raises(ValidationError):
        plan(metrics=["deal_value"], money={"mode": "source"})
    response = engine.execute(
        plan(metrics=["deal_value"], group_by=["currency"], money={"mode": "source"})
    )
    assert rows(response) == [["USD", Decimal("4938")], ["UZS", Decimal("1234.5")]]
    source = engine.execute(
        plan(metrics=["deal_value"], money={"mode": "source", "source_currency": "USD"})
    )
    assert rows(source) == [[Decimal("4938")]]
    assert source.result.outcome.data.columns[0].currency == "USD"


def test_fx_and_unverified_normalization_are_typed_unsupported_without_database():
    engine = QueryEngine(Settings())
    for request in [
        plan(metrics=["deal_value"], money={"mode": "convert_to_uzs"}),
        plan(group_by=["product_id"]),
        plan(
            filters=[
                {
                    "field": "product",
                    "operator": "eq",
                    "values": ["test"],
                    "value_kind": "normalized",
                }
            ]
        ),
    ]:
        result = engine.execute(request)
        assert result.result.outcome.status == "unsupported"
        assert result.result.coverage.state == "unknown"


def test_count_and_money_work_for_unmapped_units_but_volume_does_not(engine):
    scoped = [{"field": "product", "operator": "eq", "values": ["TEST_ONLY"]}]
    assert rows(engine.execute(plan(filters=scoped))) == [[5]]
    assert rows(
        engine.execute(
            plan(
                metrics=["deal_value"],
                filters=scoped,
                money={"mode": "source", "source_currency": "UZS"},
            )
        )
    ) == [[Decimal("1234.5")]]
    result = engine.execute(
        plan(
            metrics=["physical_volume"],
            units={"mode": "group_by_unit"},
            group_by=["measurement_unit"],
        )
    )
    assert result.result.outcome.status == "unsupported"
    assert (
        engine.execute(
            plan(
                kind="lookup",
                deal_id="0002023",
                select=["physical_volume", "measurement_unit"],
            )
        ).result.outcome.status
        == "unsupported"
    )


@pytest.mark.parametrize(
    "target,expected", [("kg", Decimal("4")), ("tonne", Decimal("0.004"))]
)
def test_mass_conversion_is_exact_and_excludes_incompatible_units(
    engine, target, expected
):
    result = engine.execute(
        plan(
            metrics=["physical_volume"], units={"mode": "convert_mass", "unit": target}
        )
    )
    assert rows(result) == [[expected]]
    assert result.result.outcome.data.columns[0].unit == target
    assert any("excluded 1" in warning for warning in result.warnings)
    with pytest.raises(ValidationError):
        plan(
            metrics=["physical_volume"], units={"mode": "convert_mass", "unit": "litre"}
        )


def test_missing_numeric_values_are_not_silently_skipped(engine):
    assert (
        engine.execute(plan(metrics=["delivered_lots"])).result.outcome.status
        == "insufficient_data"
    )
    response = engine.execute(
        plan(
            numeric_filters=[
                {"field": "delivered_lots", "operator": "gt", "value": "0"}
            ]
        )
    )
    assert response.result.outcome.status == "insufficient_data"
    assert response.result.coverage.issues[0].code == "missing_values"
    request = plan(
        metrics=["delivered_lots"],
        filters=[
            {
                "field": "delivery_completion",
                "operator": "eq",
                "values": ["fully_delivered"],
                "value_kind": "normalized",
            }
        ],
    )
    assert rows(engine.execute(request)) == [[Decimal("2")]]


def test_numeric_predicates_are_bound_and_price_predicates_use_rational_comparison(
    engine,
):
    request = plan(
        numeric_filters=[
            {"field": "transaction_amount", "operator": "gte", "value": "1000"}
        ],
        money={"mode": "source", "source_currency": "USD"},
    )
    sql = compile_plan(request)[0].data
    assert Decimal("1000") in sql.parameters
    assert rows(engine.execute(request)) == [[4]]
    price = engine.execute(
        plan(
            numeric_filters=[
                {"field": "executed_unit_price", "operator": "gt", "value": "1200"}
            ],
            money={"mode": "source", "source_currency": "USD"},
            units={"mode": "single", "unit": "kg"},
        )
    )
    assert rows(price) == [[4]]


def test_weighted_price_lookup_and_exact_price_ordering(engine):
    result = engine.execute(
        plan(
            kind="lookup",
            deal_id="0002022",
            select=["executed_unit_price", "currency", "measurement_unit"],
        )
    )
    assert rows(result) == [[Decimal("1234.5"), "USD", "kg"]]
    response = engine.execute(
        plan(
            metrics=["average_unit_price"],
            group_by=["product"],
            money={"mode": "source", "source_currency": "USD"},
            units={"mode": "single", "unit": "kg"},
            ranking={"metric": "average_unit_price", "direction": "top", "count": 2},
        )
    )
    assert rows(response) == [["TEST_ONLY", Decimal("1234.5")]]


def test_limits_ordering_and_ties_are_deterministic(engine, sources):
    request = plan(
        group_by=["deal_date"],
        ranking={"metric": "deal_count", "direction": "top", "count": 2},
    )
    response = engine.execute(request)
    assert [row[0].year for row in rows(response)] == [2022, 2023]
    assert response.truncated is True
    assert QueryExecution.model_validate_json(response.model_dump_json()) == response
    assert response.result.coverage.matched_rows == 5
    assert engine.execute(request).model_dump_json() == response.model_dump_json()
    capped = QueryEngine(
        Settings(database_path=sources[2], query_max_results=1)
    ).execute(request)
    assert capped.returned_rows == capped.effective_limit == 1
    assert capped.truncated is True


def comparison(baseline="2020", target="2022"):
    return plan(
        kind="comparison",
        baseline={"start": f"{baseline}-01-01", "end": f"{baseline}-12-31"},
        target={"start": f"{target}-01-01", "end": f"{target}-12-31"},
        aggregate={"kind": "aggregate", "metrics": ["deal_count"]},
        changes=["absolute_difference", "percentage_change"],
    )


def test_period_comparisons_zero_baseline_and_empty_periods(engine):
    result = engine.execute(comparison())
    assert rows(result) == [[0, 1, 1, None]]
    assert result.result.coverage.issues[0].code == "zero_baseline"
    assert len(result.periods) == 2
    assert any(e.source_id.endswith("#baseline") for e in result.result.evidence)
    assert rows(engine.execute(comparison("2022", "2023"))) == [[1, 1, 0, Decimal(0)]]
    assert (
        engine.execute(comparison("2020", "2021")).result.outcome.status == "no_match"
    )


def test_clarification_and_unsupported_do_not_open_database():
    engine = QueryEngine(Settings())
    assert (
        engine.execute(
            plan(
                kind="clarification",
                reason="ambiguous_entity",
                question="Which product?",
            )
        ).result.outcome.status
        == "ambiguous"
    )
    assert (
        engine.execute(
            plan(
                kind="unsupported",
                reason="unsupported_operation",
                explanation="No writes.",
            )
        ).result.outcome.status
        == "unsupported"
    )


def test_unverified_schema_and_database_failures_are_typed(tmp_path):
    missing = QueryEngine(Settings(database_path=tmp_path / "missing.duckdb")).execute(
        plan()
    )
    assert missing.result.outcome.status == "error"
    assert "missing.duckdb" not in missing.result.outcome.message
    assert not (tmp_path / "missing.duckdb").exists()
    path = tmp_path / "empty.duckdb"
    duckdb.connect(str(path)).close()
    result = QueryEngine(Settings(database_path=path)).execute(plan())
    assert result.result.outcome.status == "insufficient_data"


def test_broken_exact_key_coverage_fails_closed(engine, sources):
    with duckdb.connect(str(sources[2])) as connection:
        connection.execute(
            "UPDATE deals SET buyer_inn = 'UNMATCHED' WHERE deal_id = '0002022'"
        )
    response = engine.execute(plan())
    assert response.result.outcome.status == "insufficient_data"


def test_price_ordering_has_a_bounded_group_budget(engine, sources):
    # Additional invented records keep every key/provenance constraint intact.
    # The declared manifest is updated for this test-only database, not UZEX.
    with duckdb.connect(str(sources[2])) as connection:
        connection.execute("""
            INSERT INTO deals BY NAME
            SELECT d.* REPLACE ('EXTRA' || i::VARCHAR AS deal_id,
                              i + 100 AS source_record,
                              'PRODUCT' || i::VARCHAR AS product_name)
            FROM deals d, range(1001) r(i) WHERE deal_id = '0002022'
        """)
        connection.execute(
            "UPDATE audit.source_files SET record_count = "
            "record_count + 1001 WHERE source_file = "
            "'deals_2022.csv'"
        )
    request = plan(
        metrics=["average_unit_price"],
        group_by=["product"],
        money={"mode": "source", "source_currency": "USD"},
        units={"mode": "single", "unit": "kg"},
        ranking={"metric": "average_unit_price", "direction": "top", "count": 1},
    )
    response = engine.execute(request)
    assert response.result.outcome.status == "unsupported"
    assert "1000-group budget" in response.result.outcome.explanation


def test_unrepresentable_numeric_precision_is_explicitly_unsupported():
    request = plan(
        numeric_filters=[
            {
                "field": "deal_quantity_lots",
                "operator": "gt",
                "value": "0.0000000000001",
            }
        ]
    )
    assert (
        QueryEngine(Settings()).execute(request).result.outcome.status == "unsupported"
    )


def test_exact_product_matching_does_not_casefold_or_merge(engine):
    request = plan(
        filters=[{"field": "product", "operator": "eq", "values": ["test_only"]}]
    )
    assert engine.execute(request).result.outcome.status == "no_match"


def test_resource_errors_are_sanitized_typed_results(engine, monkeypatch):
    from contextlib import contextmanager

    from backend.database.errors import DatabaseAccessError, DatabaseErrorCode

    @contextmanager
    def fail():
        raise DatabaseAccessError(DatabaseErrorCode.RESOURCE_LIMIT)
        yield  # Context-manager protocol; no connection is actually opened.

    monkeypatch.setattr(engine._adapter, "connection", fail)
    result = engine.execute(plan())
    assert result.result.outcome.status == "error"
    assert result.result.outcome.code == "execution_failed"
    assert (
        result.result.outcome.message == "Database operation failed (resource_limit)."
    )


def test_unknown_currency_cannot_disappear_through_source_currency_policy(
    engine, sources
):
    with duckdb.connect(str(sources[2])) as connection:
        connection.execute(
            "UPDATE contracts SET currency_source = 'UNVERIFIED' "
            "WHERE contract_id = '0007'"
        )
    response = engine.execute(
        plan(metrics=["deal_value"], money={"mode": "source", "source_currency": "USD"})
    )
    assert response.result.outcome.status == "insufficient_data"
    assert rows(engine.execute(plan())) == [[5]]


def test_unknown_unit_label_cannot_disappear_through_mass_policy(engine, sources):
    with duckdb.connect(str(sources[2])) as connection:
        connection.execute(
            "UPDATE deals SET measurement_unit_source = 'UNVERIFIED_MASS' "
            "WHERE deal_id = '0002022'"
        )
    response = engine.execute(
        plan(metrics=["physical_volume"], units={"mode": "convert_mass", "unit": "kg"})
    )
    assert response.result.outcome.status == "unsupported"
    assert rows(engine.execute(plan())) == [[5]]
