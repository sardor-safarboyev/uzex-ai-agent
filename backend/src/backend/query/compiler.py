"""Pure allowlisted compilation. Compiled statements are internal, never inputs."""

from dataclasses import dataclass

from backend.query.mappings import (
    FIELDS,
    FROM,
    METRIC_SQL,
    NUMERIC_OPERATORS,
    TEXT_OPERATORS,
    VOLUME,
    quoted,
)
from backend.semantic.models import (
    AggregateRequest,
    ComparisonRequest,
    DateRange,
    LookupRequest,
    QueryPlan,
)


class UnsupportedPlan(ValueError):
    pass


@dataclass(frozen=True)
class Statement:
    sql: str
    parameters: tuple


@dataclass(frozen=True)
class CompiledRequest:
    stats: Statement
    data: Statement
    fields: tuple[str, ...]
    limit: int
    ratio_ordering: bool = False


def validate_plan(value: object) -> QueryPlan:
    if type(value) is not QueryPlan:
        raise ValueError("Only validated QueryPlan objects are accepted")
    # Also rejects model_construct(), mutated enum values, and unchecked copies.
    return QueryPlan.model_validate_json(value.model_dump_json(warnings="error"))


def check_capabilities(request: AggregateRequest | LookupRequest) -> None:
    fields = request.select if isinstance(request, LookupRequest) else request.group_by
    if "product_id" in fields:
        raise UnsupportedPlan(
            "Normalized product identifiers require a verified mapping."
        )
    if isinstance(request, AggregateRequest):
        if request.money and request.money.mode == "convert_to_uzs":
            raise UnsupportedPlan(
                "USD conversion is unsupported: rounding and "
                "transaction timezone rules are unverified."
            )
        for item in request.filters:
            if item.field == "product_id" or (
                item.value_kind == "normalized" and item.field != "delivery_completion"
            ):
                raise UnsupportedPlan(
                    "Normalized entity filters require a verified "
                    "mapping; exact source matching is available."
                )
        for item in request.numeric_filters:
            value = item.value
            if (
                not value.is_finite()
                or max(-value.as_tuple().exponent, 0) > 10
                or value.adjusted() >= 28
            ):
                raise UnsupportedPlan(
                    "Numeric predicates require lossless DECIMAL(38,10) values."
                )


def mass_expression(request: AggregateRequest | LookupRequest) -> str:
    if (
        isinstance(request, LookupRequest)
        or not request.units
        or request.units.mode != "convert_mass"
    ):
        return VOLUME
    if request.units.unit == "kg":
        factor = (
            "CASE d.measurement_unit_source WHEN 'тонна' THEN "
            "1000::DECIMAL(4,0) ELSE 1::DECIMAL(4,0) END"
        )
    else:
        factor = (
            "CASE d.measurement_unit_source WHEN 'килограмм' "
            "THEN 0.001::DECIMAL(4,3) ELSE 1.000::DECIMAL(4,3) "
            "END"
        )
    return f"({VOLUME} * ({factor}))"


def scope_cte(
    request: AggregateRequest | LookupRequest, period: DateRange | None = None
) -> tuple[str, tuple]:
    fields = dict(FIELDS)
    fields["physical_volume"] = mass_expression(request)
    projection = ", ".join(f"{sql} AS {quoted(name)}" for name, sql in fields.items())
    parameters = []
    date_condition = "TRUE"
    if period is not None:
        date_condition = "d.deal_date >= ? AND d.deal_date <= ?"
        parameters += [period.start, period.end]
    text, policy, numeric = [], [], []
    if isinstance(request, LookupRequest):
        text.append("deal_id = ?")
        parameters.append(request.deal_id)
    else:
        for item in request.filters:
            column = quoted(item.field)
            operator = TEXT_OPERATORS[item.operator]
            if item.operator in {"in", "not_in"}:
                text.append(
                    f"{column} {operator} ({', '.join('?' for _ in item.values)})"
                )
            else:
                text.append(f"{column} {operator} ?")
            parameters.extend(item.values)
        if request.money and request.money.source_currency:
            policy.append("currency = ?")
            parameters.append(request.money.source_currency.value)
        if request.units:
            if request.units.mode == "single":
                policy.append("measurement_unit = ?")
                parameters.append(request.units.unit.value)
            elif request.units.mode == "convert_mass":
                policy.append("measurement_unit IN ('kg', 'tonne')")
        for item in request.numeric_filters:
            operator = NUMERIC_OPERATORS[item.operator]
            if item.field == "executed_unit_price":
                # Exact rational comparison, never binary floating division.
                numeric.append(f"transaction_amount {operator} (? * physical_volume)")
            else:
                numeric.append(f"{quoted(item.field)} {operator} ?")
            parameters.append(item.value)
    sql = f"""
        WITH candidates AS (
            SELECT {projection}, d.source_file AS _source_file,
                   d.source_record AS _source_record,
                   d.measurement_unit_source AS _unit_source
            {FROM} WHERE {date_condition}
        ), text_scope AS (SELECT * FROM candidates WHERE
        {" AND ".join(text) or "TRUE"}),
        policy_scope AS (SELECT * FROM text_scope WHERE
        {" AND ".join(policy) or "TRUE"}),
        matched AS (SELECT * FROM policy_scope WHERE {" AND ".join(numeric) or "TRUE"})
    """
    return sql, tuple(parameters)


def required_values(
    request: AggregateRequest | LookupRequest,
) -> tuple[set[str], set[str]]:
    metrics, predicates = set(), set()
    if isinstance(request, LookupRequest):
        for field in request.select:
            if field in {
                "transaction_amount",
                "deal_quantity_lots",
                "delivered_lots",
                "lot_size",
            }:
                metrics.add(field)
            if field in {"physical_volume", "executed_unit_price"}:
                metrics.update({"deal_quantity_lots", "lot_size"})
            if field == "executed_unit_price":
                metrics.add("transaction_amount")
    else:
        for metric in request.metrics:
            metrics.update(
                {
                    "deal_value": {"transaction_amount"},
                    "delivered_lots": {"delivered_lots"},
                    "physical_volume": {"deal_quantity_lots", "lot_size"},
                    "average_unit_price": {
                        "transaction_amount",
                        "deal_quantity_lots",
                        "lot_size",
                    },
                }.get(metric, set())
            )
        for item in request.numeric_filters:
            predicates.update(
                {
                    "physical_volume": {"deal_quantity_lots", "lot_size"},
                    "executed_unit_price": {
                        "transaction_amount",
                        "deal_quantity_lots",
                        "lot_size",
                    },
                }.get(item.field, {item.field})
            )
    return metrics, predicates


def compile_request(
    request: AggregateRequest | LookupRequest,
    *,
    period: DateRange | None = None,
    max_results: int = 1000,
) -> CompiledRequest:
    check_capabilities(request)
    if isinstance(request, AggregateRequest) and period is None:
        period = request.date_range
    cte, params = scope_cte(request, period)
    metric_values, predicate_values = required_values(request)
    missing_metric = (
        " OR ".join(f"{quoted(field)} IS NULL" for field in sorted(metric_values))
        or "FALSE"
    )
    missing_predicate = (
        " OR ".join(f"{quoted(field)} IS NULL" for field in sorted(predicate_values))
        or "FALSE"
    )
    if isinstance(request, AggregateRequest) and any(
        f.field == "executed_unit_price" for f in request.numeric_filters
    ):
        missing_predicate += " OR physical_volume <= 0"
    stats = Statement(
        cte
        + f"""
        SELECT (SELECT count(*) FROM candidates) evaluated_rows,
            (SELECT count(*) FROM text_scope) text_rows,
            (SELECT count(*) FROM policy_scope) population_rows,
            (SELECT count(*) FROM matched) matched_rows,
            (SELECT count(*) FROM matched WHERE measurement_unit IS NULL) unknown_units,
            (SELECT count(*) FROM matched WHERE currency IS NULL) unknown_currencies,
            (SELECT count(*) FROM text_scope WHERE currency IS NULL)
                unknown_currency_before_policy,
            (SELECT count(*) FROM text_scope WHERE measurement_unit IS NULL AND
                (_unit_source IS NULL OR _unit_source NOT IN ('метр', 'кв.метр')))
                unverified_unit_before_policy,
            (SELECT count(*) FROM matched WHERE {missing_metric}) missing_metric_values,
            (SELECT count(*) FROM policy_scope WHERE {missing_predicate})
            missing_predicate_values
    """,
        params,
    )
    if isinstance(request, LookupRequest):
        selected = [
            quoted(field) for field in request.select if field != "executed_unit_price"
        ]
        if "executed_unit_price" in request.select:
            selected += [
                "transaction_amount AS _price_num",
                "physical_volume AS _price_den",
            ]
        selected += [
            "_source_file",
            "_source_record",
            "measurement_unit AS _unit",
            "currency AS _currency",
        ]
        return CompiledRequest(
            stats,
            Statement(
                cte
                + " SELECT "
                + ", ".join(selected)
                + " FROM matched ORDER BY deal_id ASC NULLS LAST LIMIT ?",
                params + (2,),
            ),
            tuple(request.select),
            1,
        )
    limit = min(
        request.ranking.count if request.ranking else request.limit, max_results
    )
    selection = [quoted(field) for field in request.group_by]
    for metric in request.metrics:
        if metric == "average_unit_price":
            selection += [
                "sum(transaction_amount) AS _price_num",
                "sum(physical_volume) AS _price_den",
            ]
        else:
            selection.append(f"{METRIC_SQL[metric]} AS {quoted(metric)}")
    ratio_ordering = (
        request.ranking is not None and request.ranking.metric == "average_unit_price"
    ) or any(s.field == "average_unit_price" for s in request.sort)
    ordering = []
    if not ratio_ordering:
        if request.ranking:
            direction = "DESC" if request.ranking.direction == "top" else "ASC"
            ordering.append(f"{quoted(request.ranking.metric)} {direction} NULLS LAST")
        ordering += [
            f"{quoted(s.field)} {'ASC' if s.direction == 'asc' else 'DESC'} NULLS LAST"
            for s in request.sort
        ]
    ordered = (
        {request.ranking.metric} if request.ranking and not ratio_ordering else set()
    )
    if not ratio_ordering:
        ordered.update(s.field for s in request.sort)
    ordering += [
        f"{quoted(field)} ASC NULLS LAST"
        for field in request.group_by
        if field not in ordered
    ]
    group = (
        " GROUP BY " + ", ".join(quoted(f) for f in request.group_by)
        if request.group_by
        else ""
    )
    order = " ORDER BY " + ", ".join(ordering) if ordering else ""
    sql = (
        cte
        + " SELECT "
        + ", ".join(selection)
        + " FROM matched"
        + group
        + order
        + " LIMIT ?"
    )
    return CompiledRequest(
        stats,
        Statement(sql, params + ((1001 if ratio_ordering else limit + 1),)),
        tuple(request.group_by) + tuple(request.metrics),
        limit,
        ratio_ordering,
    )


def compile_plan(
    plan: QueryPlan, *, max_results: int = 1000
) -> tuple[CompiledRequest, ...]:
    plan = validate_plan(plan)
    if not 1 <= max_results <= 1000:
        raise ValueError("max_results must be 1..1000")
    if isinstance(plan.request, ComparisonRequest):
        return tuple(
            compile_request(
                plan.request.aggregate, period=period, max_results=max_results
            )
            for period in (plan.request.baseline, plan.request.target)
        )
    if isinstance(plan.request, (AggregateRequest, LookupRequest)):
        return (compile_request(plan.request, max_results=max_results),)
    return ()
