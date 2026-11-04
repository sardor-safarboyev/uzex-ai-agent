"""Bounded read-only execution of validated plans, without an SQL input channel."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from functools import cmp_to_key

from pydantic import ValidationError

from backend.config import Settings
from backend.database.adapter import DuckDBAdapter
from backend.database.errors import DatabaseAccessError
from backend.query.compiler import (
    UnsupportedPlan,
    compile_plan,
    validate_plan,
)
from backend.query.models import PeriodCoverage, QueryExecution, RowProvenance
from backend.query.snapshot import InsufficientSnapshot, verify_snapshot
from backend.semantic.models import (
    AggregateRequest,
    ClarificationRequest,
    ComparisonRequest,
    LookupRequest,
    UnsupportedRequest,
)
from backend.semantic.registry import METRICS
from backend.semantic.results import (
    AnswerTable,
    Coverage,
    CoverageIssue,
    Evidence,
    ExecutionResult,
    ResultColumn,
)

RATIO_WARNING = (
    "Ratios use Decimal precision 38, ROUND_HALF_EVEN; no FX conversion is performed."
)


def ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return Fraction(numerator) / Fraction(denominator)


def decimal_value(value):
    if isinstance(value, Fraction):
        with localcontext() as context:
            context.prec = 38
            context.rounding = ROUND_HALF_EVEN
            return Decimal(value.numerator) / Decimal(value.denominator)
    return value


def column(field: str, request, metric=None) -> ResultColumn:
    effective = metric or field
    money = request.money if isinstance(request, AggregateRequest) else None
    units = request.units if isinstance(request, AggregateRequest) else None
    definition = METRICS.get(effective)
    currency = (
        money.source_currency if definition and definition.monetary and money else None
    )
    unit = units.unit if definition and definition.physical and units else None
    if effective == "deal_count":
        unit = "transactions"
    elif effective in {"delivered_lots", "deal_quantity_lots"}:
        unit = "lots"
    if field == "percentage_change":
        unit, currency = "percent", None
    return ResultColumn(field=field, metric=metric, currency=currency, unit=unit)


def materialize(row: dict, fields: tuple[str, ...]) -> dict:
    return {
        field: ratio(row.get("_price_num"), row.get("_price_den"))
        if field in {"average_unit_price", "executed_unit_price"}
        else row[field]
        for field in fields
    }


def exact_order(rows: list[dict], request: AggregateRequest) -> list[dict]:
    priorities = (
        [
            (
                request.ranking.metric,
                "desc" if request.ranking.direction == "top" else "asc",
            )
        ]
        if request.ranking
        else [(s.field, s.direction) for s in request.sort]
    )
    used = {field for field, _ in priorities}
    priorities += [(field, "asc") for field in request.group_by if field not in used]

    def compare(left, right):
        for field, direction in priorities:
            a, b = left[field], right[field]
            if a is None or b is None:
                answer = (a is None) - (b is None)  # NULLS LAST in either direction.
            else:
                answer = (a > b) - (a < b)
                if direction == "desc":
                    answer = -answer
            if answer:
                return answer
        return 0

    return sorted(rows, key=cmp_to_key(compare))


class QueryEngine:
    def __init__(self, settings: Settings):
        self._adapter = DuckDBAdapter(settings)
        self._max_results = settings.query_max_results

    def execute(self, value: object) -> QueryExecution:
        plan = None
        try:
            plan = validate_plan(value)
        except (ValueError, TypeError, ValidationError):
            return self._outcome(
                None,
                {
                    "status": "error",
                    "code": "validation_failed",
                    "message": "A valid QueryPlan object is required.",
                },
            )
        if isinstance(plan.request, ClarificationRequest):
            return self._outcome(
                plan,
                {
                    "status": "ambiguous",
                    "question": plan.request.question,
                    "options": plan.request.options,
                },
            )
        if isinstance(plan.request, UnsupportedRequest):
            return self._outcome(
                plan, {"status": "unsupported", "explanation": plan.request.explanation}
            )
        try:
            compiled = compile_plan(plan, max_results=self._max_results)
            with self._adapter.connection() as connection:
                snapshot = verify_snapshot(connection)
                results, statistics = [], []
                warnings = []
                for query in compiled:
                    cursor = connection.execute(query.stats.sql, query.stats.parameters)
                    stats = dict(
                        zip(
                            [d[0] for d in cursor.description],
                            cursor.fetchone(),
                            strict=True,
                        )
                    )
                    statistics.append(stats)
                    request = (
                        plan.request.aggregate
                        if isinstance(plan.request, ComparisonRequest)
                        else plan.request
                    )
                    self._check_coverage(request, stats)
                    if stats["text_rows"] > stats["population_rows"]:
                        warnings.append(
                            f"Currency/unit policy excluded "
                            f"{stats['text_rows'] - stats['population_rows']} "
                            f"source rows."
                        )
                    cursor = connection.execute(query.data.sql, query.data.parameters)
                    names = [d[0] for d in cursor.description]
                    data = [
                        dict(zip(names, row, strict=True))
                        for row in cursor.fetchmany(1001)
                    ]
                    if query.ratio_ordering and len(data) > 1000:
                        raise UnsupportedPlan(
                            "Exact price ordering exceeds the bounded "
                            "1000-group budget; narrow the scope."
                        )
                    results.append(data)
                return self._answer(
                    plan, compiled, results, statistics, snapshot, warnings
                )
        except UnsupportedPlan as error:
            return self._outcome(
                plan, {"status": "unsupported", "explanation": str(error)}
            )
        except InsufficientSnapshot as error:
            return self._outcome(
                plan,
                {"status": "insufficient_data", "explanation": str(error)},
                issue="unverified_mapping",
            )
        except MissingValues as error:
            return self._outcome(
                plan,
                {"status": "insufficient_data", "explanation": str(error)},
                issue="missing_values",
            )
        except DatabaseAccessError as error:
            return self._outcome(
                plan,
                {
                    "status": "error",
                    "code": "execution_failed",
                    "message": f"Database operation failed ({error.code.value}).",
                },
            )
        except (ValidationError, ValueError, TypeError, ArithmeticError):
            return self._outcome(
                plan,
                {
                    "status": "error",
                    "code": "internal_error",
                    "message": "The result could not be represented safely.",
                },
            )

    @staticmethod
    def _check_coverage(request, stats):
        if isinstance(request, LookupRequest):
            physical = {
                "lot_size",
                "physical_volume",
                "executed_unit_price",
                "measurement_unit",
            }.intersection(request.select)
            monetary = {
                "transaction_amount",
                "executed_unit_price",
                "currency",
            }.intersection(request.select)
        else:
            physical = (
                request.units is not None or "measurement_unit" in request.group_by
            )
            monetary = request.money is not None or "currency" in request.group_by
        if physical and stats["unverified_unit_before_policy"]:
            raise UnsupportedPlan(
                "Unverified source unit labels prevent applying "
                "the requested unit policy safely."
            )
        if physical and stats["unknown_units"]:
            raise UnsupportedPlan(
                "The selected scope contains physical units "
                "outside the semantic allowlist; their values "
                "cannot be represented or combined."
            )
        if monetary and stats["unknown_currency_before_policy"]:
            raise MissingValues(
                "Currency mapping is unavailable for matching source records."
            )
        if stats["missing_predicate_values"]:
            raise MissingValues(
                "A numeric predicate depends on missing or "
                "undefined source values; records were not "
                "silently excluded."
            )
        if not isinstance(request, LookupRequest) and stats["missing_metric_values"]:
            raise MissingValues(
                "Matching records contain missing metric values; a "
                "partial total would be misleading."
            )

    def _answer(self, plan, compiled, data, stats, snapshot, warnings):
        request = plan.request
        logical = self._logical_fields(request)
        # The fixed joins verify all dimensions; evidence explicitly covers those
        # source manifests. Rates are not used because FX remains unsupported.
        evidence_fields = {
            "brokers.csv": ["seller_broker_code", "buyer_broker_code"],
            "participants.csv": ["seller_inn", "buyer_inn"],
            "contracts.csv": ["contract_id", "currency"],
        }
        evidence = [
            Evidence(
                source_id=name,
                dataset_version=sha,
                logical_fields=evidence_fields.get(name, logical),
                mapping_verified=True,
            )
            for name, sha in sorted(snapshot.sources.items())
            if name != "usd_rates.csv"
        ]
        evaluated = sum(s["evaluated_rows"] for s in stats)
        matched = sum(s["matched_rows"] for s in stats)
        issues, provenance, periods = [], [], []
        if isinstance(request, ComparisonRequest):
            for role, period, stat in zip(
                ("baseline", "target"),
                (request.baseline, request.target),
                stats,
                strict=True,
            ):
                periods.append(
                    PeriodCoverage(
                        role=role,
                        date_range=period,
                        evaluated_rows=stat["evaluated_rows"],
                        matched_rows=stat["matched_rows"],
                    )
                )
            evidence = [
                Evidence(
                    source_id=f"{e.source_id}#{role}",
                    dataset_version=e.dataset_version,
                    logical_fields=e.logical_fields,
                    mapping_verified=True,
                )
                for role in ("baseline", "target")
                for e in evidence
            ]
        coverage = Coverage(
            state="complete", evaluated_rows=evaluated, matched_rows=matched
        )
        if matched == 0:
            return self._wrap(
                plan,
                {"status": "no_match", "message": "No matching source records."},
                coverage,
                evidence,
                warnings=warnings,
                periods=periods,
            )
        if isinstance(request, ComparisonRequest):
            metric = request.aggregate.metrics[0]
            values = []
            for records, stat in zip(data, stats, strict=True):
                if not stat["matched_rows"]:
                    values.append(None if metric == "average_unit_price" else 0)
                else:
                    values.append(materialize(records[0], compiled[0].fields)[metric])
            if any(v is None for v in values):
                raise MissingValues(
                    "A comparison period has an undefined aggregate; "
                    "it is not a zero baseline."
                )
            baseline, target = values
            exact_difference = Fraction(target) - Fraction(baseline)
            if metric == "average_unit_price":
                difference = exact_difference
            else:
                # Source aggregates have at most 38 significant digits. Avoid
                # the process-wide Decimal default precision during subtraction.
                with localcontext() as context:
                    context.prec = 80
                    difference = target - baseline
            values_by_field = {
                "baseline": baseline,
                "target": target,
                "absolute_difference": difference,
                "percentage_change": None
                if baseline == 0
                else exact_difference / Fraction(baseline) * 100,
            }
            fields = ["baseline", "target", *request.changes]
            columns = [column(field, request.aggregate, metric) for field in fields]
            rows = [[decimal_value(values_by_field[field]) for field in fields]]
            if baseline == 0 and "percentage_change" in request.changes:
                issues.append(
                    CoverageIssue(
                        code="zero_baseline",
                        description=(
                            "Percentage change is undefined for a zero "
                            "baseline, including zero-to-zero."
                        ),
                    )
                )
            if "percentage_change" in request.changes or metric == "average_unit_price":
                warnings.append(RATIO_WARNING)
            truncated, limit = False, 1
        elif isinstance(request, LookupRequest):
            row = data[0][0]
            fields = compiled[0].fields
            values = materialize(row, fields)
            columns = [column(field, request) for field in fields]
            rows = [[decimal_value(values[field]) for field in fields]]
            provenance = [
                RowProvenance(
                    row=1,
                    source_file=row["_source_file"],
                    source_record=row["_source_record"],
                )
            ]
            if any(value is None for value in values.values()):
                warnings.append(
                    "Source NULL values were retained and were not imputed."
                )
            if "executed_unit_price" in fields:
                warnings.append(RATIO_WARNING)
                if row["_price_den"] == 0:
                    issues.append(
                        CoverageIssue(
                            code="zero_denominator",
                            description=(
                                "Executed unit price has a zero physical denominator."
                            ),
                        )
                    )
            truncated, limit = False, 1
        else:
            fields = compiled[0].fields
            logical_rows = [materialize(row, fields) for row in data[0]]
            if compiled[0].ratio_ordering:
                logical_rows = exact_order(logical_rows, request)
            limit = compiled[0].limit
            truncated = len(logical_rows) > limit
            logical_rows = logical_rows[:limit]
            columns = [column(field, request) for field in fields]
            rows = [
                [decimal_value(row[field]) for field in fields] for row in logical_rows
            ]
            if "average_unit_price" in request.metrics:
                warnings.append(RATIO_WARNING)
                if any(row["average_unit_price"] is None for row in logical_rows):
                    issues.append(
                        CoverageIssue(
                            code="zero_denominator",
                            description=(
                                "An average unit price has a zero physical denominator."
                            ),
                        )
                    )
            requested_limit = (
                request.ranking.count if request.ranking else request.limit
            )
            if requested_limit > self._max_results:
                warnings.append(
                    "The result limit was reduced to the configured server maximum."
                )
        if truncated:
            warnings.append(
                "Additional groups exist beyond the result limit; "
                "coverage counts include the full matching "
                "population."
            )
        if isinstance(request, AggregateRequest) and request.filters:
            warnings.append(
                "Text predicates use SQL NULL semantics; NULL "
                "values do not match eq/ne/in/not_in."
            )
        coverage.issues = issues
        table = AnswerTable(columns=columns, rows=rows)
        return self._wrap(
            plan,
            {"status": "answered", "data": table},
            coverage,
            evidence,
            warnings=warnings,
            periods=periods,
            provenance=provenance,
            limit=limit,
            truncated=truncated,
        )

    @staticmethod
    def _logical_fields(request) -> list[str]:
        if isinstance(request, ComparisonRequest):
            return QueryEngine._logical_fields(request.aggregate)
        if isinstance(request, LookupRequest):
            return sorted(set(request.select) | {"deal_id"})
        fields = (
            set(request.metrics)
            | set(request.group_by)
            | {f.field for f in request.filters}
            | {f.field for f in request.numeric_filters}
        )
        for metric in request.metrics:
            fields.update(METRICS[metric].required_fields)
        return sorted(fields | {"deal_date"})

    @staticmethod
    def _wrap(
        plan,
        outcome,
        coverage,
        evidence,
        *,
        warnings=(),
        periods=(),
        provenance=(),
        limit=1,
        truncated=False,
    ):
        result = ExecutionResult(
            version="1.1",
            language=plan.language,
            coverage=coverage,
            evidence=evidence,
            outcome=outcome,
        )
        return QueryExecution(
            result=result,
            scope=plan,
            warnings=list(dict.fromkeys(warnings)),
            periods=list(periods),
            provenance=list(provenance),
            effective_limit=limit,
            truncated=truncated,
            returned_rows=len(outcome["data"].rows)
            if outcome["status"] == "answered"
            else 0,
        )

    @staticmethod
    def _outcome(plan, outcome, issue=None):
        coverage = Coverage(
            state="unknown",
            issues=[CoverageIssue(code=issue, description=outcome["explanation"])]
            if issue
            else [],
        )
        result = ExecutionResult(
            version="1.1",
            language=plan.language if plan else "uz",
            coverage=coverage,
            outcome=outcome,
        )
        return QueryExecution(result=result, scope=plan)


class MissingValues(ValueError):
    pass
