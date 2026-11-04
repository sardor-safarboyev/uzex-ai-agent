"""Future execution response shapes; no execution or answer generation."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Self

from pydantic import Field, StrictInt, StrictStr, model_validator

from backend.semantic.models import ContractModel, Text
from backend.semantic.registry import (
    METRICS,
    Currency,
    Dimension,
    LookupField,
    Metric,
    NumericField,
    Unit,
)

COMPARISON_FIELDS = {"baseline", "target", "absolute_difference", "percentage_change"}

Count = Annotated[int, Field(strict=True, ge=0)]
FiniteDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]
Scalar = StrictStr | StrictInt | FiniteDecimal | date | None
ResultField = (
    Metric
    | Dimension
    | LookupField
    | Literal["baseline", "target", "absolute_difference", "percentage_change"]
)


class Evidence(ContractModel):
    source_id: Text
    dataset_version: Text
    logical_fields: Annotated[list[Text], Field(min_length=1)]
    mapping_verified: bool


class CoverageIssue(ContractModel):
    code: Literal[
        "missing_rate",
        "unverified_mapping",
        "missing_values",
        "duplicate_id",
        "zero_baseline",
        "zero_denominator",
        "other",
    ]
    description: Text


class Coverage(ContractModel):
    state: Literal["complete", "partial", "unknown", "unavailable"]
    evaluated_rows: Count | None = None
    matched_rows: Count | None = None
    issues: list[CoverageIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_counts(self) -> Self:
        if self.state == "complete" and (
            self.evaluated_rows is None or self.matched_rows is None
        ):
            raise ValueError(
                "complete coverage requires evaluated_rows and matched_rows"
            )
        if self.state == "complete" and any(
            issue.code not in {"zero_baseline", "zero_denominator"}
            for issue in self.issues
        ):
            raise ValueError("complete coverage cannot contain unresolved data issues")
        if self.evaluated_rows is not None and self.matched_rows is not None:
            if self.matched_rows > self.evaluated_rows:
                raise ValueError("matched_rows must not exceed evaluated_rows")
        return self


class ResultColumn(ContractModel):
    field: ResultField
    metric: Metric | None = None
    currency: Currency | None = None
    unit: Unit | Literal["transactions", "lots", "percent"] | None = None

    @model_validator(mode="after")
    def metadata(self) -> Self:
        monetary = self.field in {"transaction_amount", "executed_unit_price"}
        physical = self.field in {"lot_size", "physical_volume", "executed_unit_price"}
        if (self.field in COMPARISON_FIELDS) != (self.metric is not None):
            raise ValueError(
                "comparison columns require metric; other columns forbid it"
            )
        metric = self.metric if self.metric else self.field
        if metric in METRICS:
            monetary |= METRICS[metric].monetary
            physical |= METRICS[metric].physical
        if self.field == "percentage_change":
            if self.unit != "percent" or self.currency is not None:
                raise ValueError(
                    "percentage_change requires percent unit and no currency"
                )
            return self
        if not monetary and self.currency is not None:
            raise ValueError("nonmonetary columns forbid currency metadata")
        if physical and self.unit is not None and self.unit not in set(Unit):
            raise ValueError("physical result columns require a physical unit")
        expected = {
            "deal_count": "transactions",
            "delivered_lots": "lots",
            "deal_quantity_lots": "lots",
        }.get(metric)
        if expected and self.unit != expected:
            raise ValueError(f"{metric} requires unit {expected}")
        if not physical and not expected and self.unit is not None:
            raise ValueError("nonphysical columns forbid unit metadata")
        return self


class AnswerTable(ContractModel):
    columns: Annotated[list[ResultColumn], Field(min_length=1, max_length=30)]
    rows: Annotated[list[list[Scalar]], Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def rectangular(self) -> Self:
        if len({c.field for c in self.columns}) != len(self.columns):
            raise ValueError("result columns must be unique")
        fields = {c.field for c in self.columns}
        comparison_metrics = {c.metric for c in self.columns if c.metric}
        if len(comparison_metrics) > 1:
            raise ValueError("comparison columns must refer to the same metric")
        for column in self.columns:
            metric = column.metric or column.field
            if column.field == "percentage_change":
                continue
            monetary = metric in {"transaction_amount", "executed_unit_price"}
            physical = metric in {"lot_size", "physical_volume", "executed_unit_price"}
            if metric in METRICS:
                monetary |= METRICS[metric].monetary
                physical |= METRICS[metric].physical
            if monetary and not column.currency and "currency" not in fields:
                raise ValueError(
                    "monetary results need currency metadata or currency column"
                )
            if physical and not column.unit and "measurement_unit" not in fields:
                raise ValueError(
                    "physical results need unit metadata or measurement_unit column"
                )
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("each result row must match the columns")
        numeric_fields = (
            set(Metric) | set(NumericField) | COMPARISON_FIELDS | {"lot_size"}
        )
        for row in self.rows:
            for index, column in enumerate(self.columns):
                value = row[index]
                if value is None:
                    continue
                if column.field in numeric_fields:
                    if isinstance(value, str):
                        try:
                            value = Decimal(value)
                        except InvalidOperation as exc:
                            raise ValueError(
                                "numeric result cells require finite numbers"
                            ) from exc
                        row[index] = value
                    if (
                        not isinstance(value, (int, Decimal))
                        or not Decimal(value).is_finite()
                    ):
                        raise ValueError("numeric result cells require finite numbers")
                if column.field == "currency" and value not in set(Currency):
                    raise ValueError("currency result cells must be UZS or USD")
                if column.field == "measurement_unit" and value not in set(Unit):
                    raise ValueError("measurement_unit cells require an approved unit")
        return self


class Answered(ContractModel):
    status: Literal["answered"]
    data: AnswerTable


class NoMatch(ContractModel):
    status: Literal["no_match"]
    message: Text


class InsufficientData(ContractModel):
    status: Literal["insufficient_data"]
    explanation: Text


class Ambiguous(ContractModel):
    status: Literal["ambiguous"]
    question: Text
    options: Annotated[list[Text], Field(max_length=10)] = Field(default_factory=list)


class Unsupported(ContractModel):
    status: Literal["unsupported"]
    explanation: Text


class ExecutionError(ContractModel):
    status: Literal["error"]
    code: Literal["execution_failed", "validation_failed", "internal_error"]
    message: Text
    # Public messages must never contain SQL, credentials, or stack traces.


class ExecutionResult(ContractModel):
    version: Literal["1.1"]
    language: Literal["uz", "ru"]
    evidence: list[Evidence] = Field(default_factory=list)
    coverage: Coverage
    outcome: Annotated[
        Answered
        | NoMatch
        | InsufficientData
        | Ambiguous
        | Unsupported
        | ExecutionError,
        Field(discriminator="status"),
    ]

    @model_validator(mode="after")
    def evidence_requirements(self) -> Self:
        if self.outcome.status in {"answered", "no_match"}:
            if self.coverage.state != "complete":
                raise ValueError("answered/no_match require complete coverage")
            if not self.evidence or not all(e.mapping_verified for e in self.evidence):
                raise ValueError("answered/no_match require verified evidence")
            if self.outcome.status == "no_match" and self.coverage.matched_rows != 0:
                raise ValueError("no_match requires matched_rows = 0")
            if self.outcome.status == "answered" and not self.coverage.matched_rows:
                raise ValueError(
                    "answered requires matching records; use no_match for empty sets"
                )
        if isinstance(self.outcome, Answered):
            fields = [c.field for c in self.outcome.data.columns]
            if "baseline" in fields and "percentage_change" in fields:
                baseline_index = fields.index("baseline")
                percentage_index = fields.index("percentage_change")
                if any(
                    row[baseline_index] == 0 and row[percentage_index] is not None
                    for row in self.outcome.data.rows
                ):
                    raise ValueError("zero baseline requires null percentage_change")
            for index, column in enumerate(self.outcome.data.columns):
                if column.field == "percentage_change" and any(
                    row[index] is None for row in self.outcome.data.rows
                ):
                    if not any(i.code == "zero_baseline" for i in self.coverage.issues):
                        raise ValueError(
                            "undefined percentage requires zero_baseline issue"
                        )
        if self.outcome.status == "insufficient_data":
            if not self.coverage.issues:
                raise ValueError("insufficient_data requires coverage issues")
        return self
