"""Contract fixtures only: values are not dataset records or analytical answers."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.semantic import ExecutionResult, QueryPlan


def query(request, version="1.1"):
    return QueryPlan.model_validate(
        {"version": version, "language": "uz", "request": request}
    )


def aggregate(**changes):
    return {"kind": "aggregate", "metrics": ["deal_count"], **changes}


def comparison(**changes):
    return {
        "kind": "comparison",
        "baseline": {"start": "2024-01-01", "end": "2024-01-31"},
        "target": {"start": "2025-01-01", "end": "2025-01-31"},
        "aggregate": aggregate(),
        "changes": ["absolute_difference", "percentage_change"],
        **changes,
    }


def test_lookup_round_trip():
    parsed = query(
        {
            "kind": "lookup",
            "deal_id": "identifier-placeholder",
            "select": [
                "deal_id",
                "status",
                "delivery_completion",
                "transaction_amount",
                "currency",
                "physical_volume",
                "measurement_unit",
                "seller_broker_code",
                "buyer_broker_code",
            ],
        }
    )
    assert QueryPlan.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"deal_id": 12}, "valid string"),
        ({"deal_id": " "}, "at least 1"),
        ({"select": []}, "at least 1"),
        ({"select": ["deal_id", "deal_id"]}, "must be unique"),
        ({"select": ["secret_column"]}, "Input should be"),
        ({"select": ["starting_price"]}, "Input should be"),
        ({"select": ["transaction_amount"]}, "require currency"),
        ({"select": ["lot_size"]}, "require measurement_unit"),
        ({"select": ["executed_unit_price", "currency"]}, "require measurement_unit"),
        ({"filters": []}, "Extra inputs"),
        ({"sql": "SELECT 1"}, "Extra inputs"),
    ],
)
def test_invalid_lookup(changes, message):
    with pytest.raises(ValidationError, match=message):
        query(
            {
                "kind": "lookup",
                "deal_id": "placeholder",
                "select": ["deal_id"],
                **changes,
            }
        )


@pytest.mark.parametrize(
    "changes",
    [
        ["absolute_difference"],
        ["percentage_change"],
        ["absolute_difference", "percentage_change"],
    ],
)
def test_comparison_round_trip(changes):
    parsed = query(comparison(changes=changes))
    assert parsed.request.zero_baseline == "undefined"
    assert QueryPlan.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize(
    "metric,policies",
    [
        ("deal_value", {"money": {"mode": "convert_to_uzs"}}),
        ("physical_volume", {"units": {"mode": "convert_mass", "unit": "kg"}}),
        (
            "average_unit_price",
            {
                "money": {"mode": "source", "source_currency": "UZS"},
                "units": {"mode": "single", "unit": "kg"},
                "filters": [
                    {
                        "field": "product_id",
                        "operator": "eq",
                        "values": ["logical-id"],
                        "value_kind": "normalized",
                    }
                ],
            },
        ),
    ],
)
def test_comparison_policies(metric, policies):
    assert query(comparison(aggregate=aggregate(metrics=[metric], **policies)))


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"target": {"start": "2024-01-31", "end": "2024-02-28"}}, "disjoint"),
        ({"target": {"start": "2023-01-01", "end": "2023-02-01"}}, "baseline before"),
        (
            {"aggregate": aggregate(metrics=["deal_count", "delivered_lots"])},
            "exactly one",
        ),
        ({"aggregate": aggregate(group_by=["product"])}, "no grouping"),
        (
            {
                "aggregate": aggregate(
                    date_range={"start": "2022-01-01", "end": "2022-01-02"}
                )
            },
            "forbids date_range",
        ),
        (
            {"aggregate": aggregate(sort=[{"field": "deal_count"}])},
            "forbids date_range",
        ),
        ({"changes": []}, "at least 1"),
        ({"changes": ["ratio"]}, "Input should be"),
        ({"changes": ["absolute_difference", "absolute_difference"]}, "must be unique"),
        ({"zero_baseline": "zero"}, "undefined"),
        ({"zero_baseline": "infinity"}, "undefined"),
        ({"expression": "target / baseline"}, "Extra inputs"),
    ],
)
def test_invalid_comparison(changes, message):
    with pytest.raises(ValidationError, match=message):
        query(comparison(**changes))


@pytest.mark.parametrize("role", ["seller_broker_code", "buyer_broker_code"])
def test_broker_roles(role):
    parsed = query(
        aggregate(
            group_by=[role],
            filters=[
                {
                    "field": role,
                    "operator": "eq",
                    "values": ["0001"],
                }
            ],
        )
    )
    assert parsed.request.filters[0].values == ["0001"]


@pytest.mark.parametrize(
    "legacy", ["broker_code", "fulfillment", "registration_region"]
)
def test_ambiguous_or_removed_fields_rejected(legacy):
    with pytest.raises(ValidationError):
        query(aggregate(group_by=[legacy]))
    with pytest.raises(ValidationError):
        query({"kind": "lookup", "deal_id": "placeholder", "select": [legacy]})


def test_official_status_is_separate_from_delivery():
    assert query(
        aggregate(
            group_by=["status", "delivery_completion"],
            filters=[
                {"field": "status", "operator": "eq", "values": ["source-label"]},
                {
                    "field": "delivery_completion",
                    "operator": "in",
                    "value_kind": "normalized",
                    "values": [
                        "fully_delivered",
                        "partially_delivered",
                        "not_delivered",
                    ],
                },
            ],
        )
    )
    with pytest.raises(ValidationError, match="unsupported normalized"):
        query(
            aggregate(
                filters=[
                    {
                        "field": "delivery_completion",
                        "operator": "eq",
                        "values": ["paid"],
                        "value_kind": "normalized",
                    }
                ]
            )
        )


@pytest.mark.parametrize("operator", ["eq", "ne", "gt", "gte", "lt", "lte"])
def test_numeric_operators(operator):
    parsed = query(
        aggregate(
            numeric_filters=[
                {
                    "field": "deal_quantity_lots",
                    "operator": operator,
                    "value": "1.25",
                }
            ]
        )
    )
    assert parsed.request.numeric_filters[0].value == Decimal("1.25")
    assert QueryPlan.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize(
    "field,policy",
    [
        ("delivered_lots", {}),
        ("transaction_amount", {"money": {"mode": "source", "source_currency": "USD"}}),
        ("physical_volume", {"units": {"mode": "convert_mass", "unit": "tonne"}}),
        (
            "executed_unit_price",
            {
                "money": {"mode": "convert_to_uzs"},
                "units": {"mode": "single", "unit": "kg"},
            },
        ),
    ],
)
def test_numeric_field_policies(field, policy):
    assert query(
        aggregate(
            numeric_filters=[{"field": field, "operator": "gt", "value": 0}], **policy
        )
    )


@pytest.mark.parametrize(
    "predicate,policy,message",
    [
        ({"field": "profit", "operator": "gt", "value": 0}, {}, "Input should be"),
        (
            {"field": "starting_price", "operator": "gt", "value": 0},
            {},
            "Input should be",
        ),
        (
            {"field": "delivered_lots", "operator": "between", "value": 0},
            {},
            "Input should be",
        ),
        (
            {"field": "delivered_lots", "operator": "gt", "value": True},
            {},
            "not be boolean",
        ),
        (
            {"field": "delivered_lots", "operator": "gt", "value": -1},
            {},
            "greater than or equal",
        ),
        (
            {"field": "delivered_lots", "operator": "gt", "value": "NaN"},
            {},
            "finite number",
        ),
        (
            {"field": "delivered_lots", "operator": "gt", "value": float("inf")},
            {},
            "finite number",
        ),
        (
            {"field": "transaction_amount", "operator": "gt", "value": 0},
            {},
            "money policy",
        ),
        (
            {"field": "physical_volume", "operator": "gt", "value": 0},
            {},
            "units policy",
        ),
        (
            {"field": "executed_unit_price", "operator": "gt", "value": 0},
            {"money": {"mode": "convert_to_uzs"}},
            "units policy",
        ),
        (
            {"field": "transaction_amount", "operator": "gt", "value": 0},
            {"money": {"mode": "source"}, "group_by": ["currency"]},
            "require one currency",
        ),
        (
            {"field": "physical_volume", "operator": "gt", "value": 0},
            {"units": {"mode": "group_by_unit"}, "group_by": ["measurement_unit"]},
            "require one unit",
        ),
    ],
)
def test_invalid_numeric_predicates(predicate, policy, message):
    with pytest.raises(ValidationError, match=message):
        query(aggregate(numeric_filters=[predicate], **policy))


@pytest.mark.parametrize("unit", ["kg", "tonne"])
@pytest.mark.parametrize("ordering", ["sort", "ranking"])
def test_mass_conversion_allows_comparable_ordering(unit, ordering):
    order = (
        {"sort": [{"field": "physical_volume"}]}
        if ordering == "sort"
        else {"ranking": {"metric": "physical_volume", "direction": "top", "count": 5}}
    )
    assert query(
        aggregate(
            metrics=["physical_volume"],
            group_by=["product_id"],
            units={"mode": "convert_mass", "unit": unit},
            **order,
        )
    )


@pytest.mark.parametrize("unit", [None, "litre", "cubic_metre", "piece"])
def test_incompatible_mass_targets_rejected(unit):
    with pytest.raises(ValidationError, match="kg or tonne"):
        query(
            aggregate(
                metrics=["physical_volume"],
                units={"mode": "convert_mass", "unit": unit},
            )
        )


def test_conversion_forbids_source_unit_grouping():
    with pytest.raises(ValidationError, match="measurement_unit grouping"):
        query(
            aggregate(
                metrics=["physical_volume"],
                units={"mode": "convert_mass", "unit": "kg"},
                group_by=["measurement_unit"],
            )
        )


def test_normalized_product_grouping_and_filters():
    assert query(
        aggregate(
            group_by=["product_id"],
            filters=[
                {
                    "field": "product_id",
                    "operator": "eq",
                    "values": ["logical-id"],
                    "value_kind": "normalized",
                }
            ],
        )
    )
    with pytest.raises(ValidationError, match="requires normalized"):
        query(
            aggregate(
                filters=[{"field": "product_id", "operator": "eq", "values": ["raw"]}]
            )
        )


@pytest.mark.parametrize(
    "request_payload",
    [
        {"kind": "lookup", "deal_id": "placeholder", "select": ["deal_id"]},
        comparison(),
        aggregate(
            numeric_filters=[{"field": "delivered_lots", "operator": "gt", "value": 0}]
        ),
        aggregate(group_by=["product_id"]),
        aggregate(
            metrics=["physical_volume"], units={"mode": "convert_mass", "unit": "kg"}
        ),
    ],
)
def test_new_capabilities_require_version_1_1(request_payload):
    with pytest.raises(ValidationError, match="require version 1.1"):
        query(request_payload, version="1.0")


# These are schema fixtures, not returned transaction data.
def result(status="no_match"):
    outcomes = {
        "answered": {
            "data": {"columns": [{"field": "status"}], "rows": [["placeholder"]]}
        },
        "no_match": {"message": "No matching records"},
        "insufficient_data": {"explanation": "Mappings unavailable"},
        "ambiguous": {"question": "Which product?"},
        "unsupported": {"explanation": "Operation unsupported"},
        "error": {"code": "execution_failed", "message": "Execution failed"},
    }
    evaluated = status in {"answered", "no_match"}
    return {
        "version": "1.1",
        "language": "uz",
        "evidence": [
            {
                "source_id": "test-fixture",
                "dataset_version": "test-only",
                "logical_fields": ["status"],
                "mapping_verified": True,
            }
        ]
        if evaluated
        else [],
        "coverage": (
            {
                "state": "complete",
                "evaluated_rows": 1,
                "matched_rows": 1 if status == "answered" else 0,
            }
            if evaluated
            else {
                "state": "unknown",
                "issues": [
                    {"code": "unverified_mapping", "description": "Not verified"}
                ],
            }
        ),
        "outcome": {"status": status, **outcomes[status]},
    }


@pytest.mark.parametrize(
    "status",
    ["answered", "no_match", "insufficient_data", "ambiguous", "unsupported", "error"],
)
def test_result_outcomes_round_trip(status):
    parsed = ExecutionResult.model_validate(result(status))
    assert parsed.outcome.status == status
    assert ExecutionResult.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize("status", ["answered", "no_match"])
@pytest.mark.parametrize("change", ["evidence", "mapping", "coverage", "matched"])
def test_success_requires_evidence_and_consistent_coverage(status, change):
    payload = result(status)
    if change == "evidence":
        payload["evidence"] = []
    elif change == "mapping":
        payload["evidence"][0]["mapping_verified"] = False
    elif change == "coverage":
        payload["coverage"]["state"] = "partial"
    else:
        payload["coverage"]["matched_rows"] = 0 if status == "answered" else 1
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "complete"},
        {"state": "complete", "evaluated_rows": 0, "matched_rows": 1},
        {"state": "partial", "evaluated_rows": -1},
        {"state": "unknown", "evaluated_rows": True},
        {
            "state": "complete",
            "evaluated_rows": 1,
            "matched_rows": 0,
            "issues": [{"code": "missing_rate", "description": "Rate missing"}],
        },
    ],
)
def test_invalid_coverage(changes):
    payload = result()
    payload["coverage"] = changes
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(payload)


def test_insufficient_data_requires_issues():
    payload = result("insufficient_data")
    payload["coverage"]["issues"] = []
    with pytest.raises(ValidationError, match="requires coverage issues"):
        ExecutionResult.model_validate(payload)


@pytest.mark.parametrize(
    "status", ["no_match", "insufficient_data", "ambiguous", "unsupported", "error"]
)
def test_nonanswers_forbid_data(status):
    payload = result(status)
    payload["outcome"]["data"] = result("answered")["outcome"]["data"]
    with pytest.raises(ValidationError, match="Extra inputs"):
        ExecutionResult.model_validate(payload)


@pytest.mark.parametrize(
    "data",
    [
        {"columns": [{"field": "unknown"}], "rows": [[None]]},
        {"columns": [{"field": "status"}], "rows": []},
        {"columns": [{"field": "status"}], "rows": [[None, None]]},
        {"columns": [{"field": "status"}, {"field": "status"}], "rows": [[None, None]]},
        {"columns": [{"field": "deal_value"}], "rows": [[None]]},
        {"columns": [{"field": "physical_volume"}], "rows": [[None]]},
        {"columns": [{"field": "deal_count", "currency": "USD"}], "rows": [[None]]},
        {"columns": [{"field": "baseline"}], "rows": [[None]]},
        {
            "columns": [
                {"field": "percentage_change", "metric": "deal_count", "unit": "kg"}
            ],
            "rows": [[None]],
        },
    ],
)
def test_invalid_result_tables(data):
    payload = result("answered")
    payload["outcome"]["data"] = data
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(payload)


def test_zero_baseline_percentage_is_explicitly_undefined():
    payload = result("answered")
    payload["outcome"]["data"] = {
        "columns": [
            {"field": "percentage_change", "metric": "deal_count", "unit": "percent"}
        ],
        "rows": [[None]],
    }
    with pytest.raises(ValidationError, match="zero_baseline issue"):
        ExecutionResult.model_validate(payload)
    payload["coverage"]["issues"] = [
        {"code": "zero_baseline", "description": "Undefined"}
    ]
    assert ExecutionResult.model_validate(payload).outcome.data.rows == [[None]]


def test_unknown_result_state_and_sql_rejected():
    payload = result()
    payload["outcome"]["status"] = "success"
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(payload)
    payload = result()
    payload["sql"] = "SELECT 1"
    with pytest.raises(ValidationError, match="Extra inputs"):
        ExecutionResult.model_validate(payload)


def test_schema_is_exportable():
    for model in (QueryPlan, ExecutionResult):
        assert model.model_json_schema()["additionalProperties"] is False


@pytest.mark.parametrize(
    "column",
    [
        {"field": "deal_value", "currency": "UZS"},
        {"field": "physical_volume", "unit": "tonne"},
        {"field": "average_unit_price", "currency": "USD", "unit": "kg"},
        {
            "field": "absolute_difference",
            "metric": "deal_count",
            "unit": "transactions",
        },
    ],
)
def test_numeric_result_metadata_and_decimal_round_trip(column):
    payload = result("answered")
    payload["outcome"]["data"] = {"columns": [column], "rows": [[Decimal("1.25")]]}
    parsed = ExecutionResult.model_validate(payload)
    assert ExecutionResult.model_validate_json(parsed.model_dump_json()) == parsed


def test_source_grouped_currency_and_unit_metadata():
    payload = result("answered")
    payload["outcome"]["data"] = {
        "columns": [
            {"field": "deal_value"},
            {"field": "currency"},
            {"field": "physical_volume"},
            {"field": "measurement_unit"},
        ],
        "rows": [[None, "UZS", None, "kg"]],
    }
    assert ExecutionResult.model_validate(payload)


@pytest.mark.parametrize(
    "value", ["not-a-number", "NaN", "Infinity", float("inf"), True]
)
def test_invalid_numeric_result_cells(value):
    payload = result("answered")
    payload["outcome"]["data"] = {
        "columns": [{"field": "deal_value", "currency": "UZS"}],
        "rows": [[value]],
    }
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(payload)


def test_zero_baseline_cannot_have_numeric_percentage():
    payload = result("answered")
    payload["outcome"]["data"] = {
        "columns": [
            {"field": "baseline", "metric": "deal_count", "unit": "transactions"},
            {"field": "percentage_change", "metric": "deal_count", "unit": "percent"},
        ],
        "rows": [[0, 0]],
    }
    with pytest.raises(ValidationError, match="zero baseline requires null"):
        ExecutionResult.model_validate(payload)
