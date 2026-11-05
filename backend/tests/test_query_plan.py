from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.semantic import METRICS, QueryPlan
from backend.semantic.registry import Metric


def plan(**changes):
    request = {"kind": "aggregate", "metrics": ["deal_count"]}
    request.update(changes)
    return {"version": "1.0", "language": "uz", "request": request}


@pytest.mark.parametrize("language", ["uz", "ru"])
def test_count_round_trip(language):
    payload = plan(
        date_range={"start": "2022-01-01", "end": "2026-12-31"},
        group_by=["warehouse_region"],
        filters=[{"field": "seller_inn", "operator": "eq", "values": ["001234567"]}],
        ranking={"metric": "deal_count", "direction": "top", "count": 10},
    )
    payload["language"] = language
    parsed = QueryPlan.model_validate(payload)
    assert parsed.request.filters[0].values == ["001234567"]
    assert QueryPlan.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize(
    "metrics,extra",
    [
        (["deal_value"], {"money": {"mode": "source", "source_currency": "USD"}}),
        (["deal_value"], {"money": {"mode": "source"}, "group_by": ["currency"]}),
        (["deal_value"], {"money": {"mode": "convert_to_uzs"}}),
        (["physical_volume"], {"units": {"mode": "single", "unit": "kg"}}),
        (
            ["physical_volume"],
            {"units": {"mode": "group_by_unit"}, "group_by": ["measurement_unit"]},
        ),
        (["delivered_lots"], {}),
        (
            ["average_unit_price"],
            {
                "money": {"mode": "convert_to_uzs"},
                "units": {"mode": "single", "unit": "tonne"},
                "group_by": ["product"],
            },
        ),
    ],
)
def test_metric_policies(metrics, extra):
    assert QueryPlan.model_validate(plan(metrics=metrics, **extra))


@pytest.mark.parametrize(
    "kind,content",
    [
        (
            "clarification",
            {
                "reason": "ambiguous_entity",
                "question": "Qaysi mahsulot?",
                "options": ["source spelling A", "source spelling B"],
            },
        ),
        (
            "unsupported",
            {"reason": "unverified_mapping", "explanation": "Mapping not verified"},
        ),
    ],
)
def test_non_query_outcomes(kind, content):
    result = QueryPlan.model_validate(
        {
            "version": "1.0",
            "language": "ru",
            "request": {"kind": kind, **content},
        }
    )
    assert result.request.kind == kind
    assert "metrics" not in result.request.model_dump()


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"metrics": ["profit"]}, "Input should be"),
        ({"metrics": []}, "at least 1"),
        ({"metrics": ["deal_count", "deal_count"]}, "metrics must be unique"),
        ({"group_by": ["registration_region"]}, "Input should be"),
        ({"group_by": ["product", "product"]}, "dimensions must be unique"),
        ({"sql": "SELECT 1"}, "Extra inputs"),
        ({"limit": 0}, "greater than or equal"),
        ({"limit": 1001}, "less than or equal"),
        ({"limit": True}, "valid integer"),
        ({"limit": "10"}, "valid integer"),
        ({"date_range": {"start": "2026-01-02", "end": "2026-01-01"}}, "on or before"),
        ({"date_range": {"start": "yesterday", "end": "2026-01-01"}}, "valid date"),
        ({"metrics": ["deal_value"]}, "money policy"),
        ({"money": {"mode": "source", "source_currency": "USD"}}, "money policy"),
        ({"metrics": ["deal_value"], "money": {"mode": "source"}}, "source_currency"),
        (
            {
                "metrics": ["deal_value"],
                "money": {"mode": "source", "source_currency": "EUR"},
            },
            "Input should be",
        ),
        (
            {
                "metrics": ["deal_value"],
                "money": {"mode": "convert_to_uzs", "source_currency": "USD"},
            },
            "omit source_currency",
        ),
        (
            {
                "metrics": ["deal_value"],
                "money": {"mode": "convert_to_uzs"},
                "group_by": ["currency"],
            },
            "cannot group",
        ),
        ({"metrics": ["physical_volume"]}, "units policy"),
        ({"units": {"mode": "single", "unit": "kg"}}, "units policy"),
        (
            {"metrics": ["physical_volume"], "units": {"mode": "single"}},
            "single requires",
        ),
        (
            {
                "metrics": ["physical_volume"],
                "units": {"mode": "single", "unit": "unknown"},
            },
            "Input should be",
        ),
        (
            {
                "metrics": ["physical_volume"],
                "units": {"mode": "group_by_unit", "unit": "kg"},
            },
            "group_by_unit forbids",
        ),
        (
            {"metrics": ["physical_volume"], "units": {"mode": "group_by_unit"}},
            "measurement_unit grouping",
        ),
        (
            {
                "metrics": ["physical_volume"],
                "units": {"mode": "single", "unit": "kg"},
                "group_by": ["measurement_unit"],
            },
            "single forbids",
        ),
        (
            {
                "metrics": ["average_unit_price"],
                "money": {"mode": "convert_to_uzs"},
                "units": {"mode": "single", "unit": "kg"},
            },
            "requires one product",
        ),
        ({"sort": [{"field": "deal_value"}]}, "sort fields must be selected"),
        (
            {"sort": [{"field": "deal_count"}, {"field": "deal_count"}]},
            "must be unique",
        ),
        (
            {"ranking": {"metric": "deal_count", "direction": "top", "count": 10}},
            "ranking requires grouping",
        ),
        (
            {
                "group_by": ["product"],
                "ranking": {"metric": "deal_value", "direction": "top", "count": 10},
            },
            "selected metric",
        ),
        (
            {
                "group_by": ["product"],
                "limit": 5,
                "ranking": {"metric": "deal_count", "direction": "top", "count": 10},
            },
            "must not exceed",
        ),
        (
            {
                "group_by": ["product"],
                "sort": [{"field": "deal_count"}],
                "ranking": {"metric": "deal_count", "direction": "top", "count": 10},
            },
            "forbids sort",
        ),
    ],
)
def test_invalid_aggregate(changes, message):
    with pytest.raises(ValidationError, match=message):
        QueryPlan.model_validate(plan(**changes))


@pytest.mark.parametrize(
    "field,operator,values,kind,message",
    [
        ("starting_price", "eq", ["100"], "source", "Input should be"),
        ("product", "contains", ["oil"], "source", "Input should be"),
        ("product", "eq", ["a", "b"], "source", "exactly one"),
        ("product", "in", [], "source", "at least 1"),
        ("product", "in", ["a", "a"], "source", "must be unique"),
        ("product", "eq", [123], "source", "valid string"),
        ("product", "eq", [" "], "source", "at least 1"),
        ("deal_date", "eq", ["2022-01-01"], "source", "use date_range"),
        ("delivery_completion", "eq", ["done"], "normalized", "unsupported normalized"),
        (
            "delivery_completion",
            "eq",
            ["fully_delivered"],
            "source",
            "normalized values",
        ),
        ("currency", "eq", ["USD"], "normalized", "use money and units"),
        ("measurement_unit", "eq", ["kg"], "normalized", "use money and units"),
    ],
)
def test_invalid_filter(field, operator, values, kind, message):
    with pytest.raises(ValidationError, match=message):
        QueryPlan.model_validate(
            plan(
                filters=[
                    {
                        "field": field,
                        "operator": operator,
                        "values": values,
                        "value_kind": kind,
                    }
                ]
            )
        )


@pytest.mark.parametrize(
    "field,values,kind",
    [
        ("product", ["Пахта", "Paxta"], "source"),
        ("product", ["cotton"], "normalized"),
        (
            "delivery_completion",
            ["fully_delivered", "partially_delivered"],
            "normalized",
        ),
        ("status", ["dataset-specific status"], "source"),
    ],
)
def test_valid_filters(field, values, kind):
    assert QueryPlan.model_validate(
        plan(
            filters=[
                {
                    "field": field,
                    "operator": "in",
                    "values": values,
                    "value_kind": kind,
                }
            ]
        )
    )


@pytest.mark.parametrize("physical", [False, True])
@pytest.mark.parametrize("ranking", [False, True])
def test_reject_cross_unit_or_currency_comparisons(physical, ranking):
    metric = "physical_volume" if physical else "deal_value"
    extra = (
        {"units": {"mode": "group_by_unit"}, "group_by": ["measurement_unit"]}
        if physical
        else {"money": {"mode": "source"}, "group_by": ["currency"]}
    )
    extra.update(
        {"ranking": {"metric": metric, "direction": "bottom", "count": 5}}
        if ranking
        else {"sort": [{"field": metric}]}
    )
    with pytest.raises(ValidationError, match="requires one"):
        QueryPlan.model_validate(plan(metrics=[metric], **extra))


def test_valid_price_filter_and_sort():
    assert QueryPlan.model_validate(
        plan(
            metrics=["average_unit_price"],
            money={"mode": "source", "source_currency": "UZS"},
            units={"mode": "single", "unit": "kg"},
            filters=[{"field": "product", "operator": "eq", "values": ["Paxta"]}],
            group_by=["warehouse_region"],
            sort=[{"field": "average_unit_price"}],
        )
    )


@pytest.mark.parametrize("field,value", [("version", "2.0"), ("language", "en")])
def test_version_and_language(field, value):
    payload = plan()
    payload[field] = value
    with pytest.raises(ValidationError):
        QueryPlan.model_validate(payload)


def test_non_query_cannot_carry_query_or_sql():
    for kind, content in [
        ("clarification", {"reason": "unit", "question": "Which unit?"}),
        (
            "unsupported",
            {"reason": "unsupported_operation", "explanation": "No writes"},
        ),
    ]:
        payload = {
            "version": "1.0",
            "language": "uz",
            "request": {"kind": kind, **content},
        }
        for extra in [{"metrics": ["deal_count"]}, {"sql": "SELECT 1"}]:
            invalid = deepcopy(payload)
            invalid["request"].update(extra)
            with pytest.raises(ValidationError, match="Extra inputs"):
                QueryPlan.model_validate(invalid)


def test_registry_is_complete_and_immutable():
    assert set(METRICS) == set(Metric)
    assert all(d.definition and d.required_fields for d in METRICS.values())
    with pytest.raises(TypeError):
        METRICS[Metric.DEAL_COUNT] = METRICS[Metric.DEAL_VALUE]


def test_documented_examples_parse():
    import re
    from pathlib import Path

    document = Path(__file__).resolve().parents[2] / "docs" / "query-plan.md"
    examples = re.findall(r"```json\n(.*?)\n```", document.read_text(), re.DOTALL)
    assert len(examples) == 6
    assert {QueryPlan.model_validate_json(e).request.kind for e in examples} == {
        "aggregate",
        "clarification",
        "unsupported",
        "lookup",
        "comparison",
    }


def test_sql_like_text_is_only_a_literal_source_value():
    literal = "'; DROP TABLE deals; --"
    parsed = QueryPlan.model_validate(
        plan(
            filters=[
                {
                    "field": "product",
                    "operator": "eq",
                    "values": [literal],
                }
            ]
        )
    )
    assert parsed.request.filters[0].values == [literal]


def test_schema_has_discriminated_outcomes():
    schema = QueryPlan.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["request"]["discriminator"]["propertyName"] == "kind"
