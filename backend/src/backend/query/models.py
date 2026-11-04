"""Execution metadata wrapper; semantic QueryPlan/ExecutionResult stay unchanged."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from backend.semantic.models import ContractModel, DateRange, QueryPlan, Text
from backend.semantic.results import ExecutionResult


class PeriodCoverage(ContractModel):
    role: Literal["baseline", "target"]
    date_range: DateRange
    evaluated_rows: int = Field(ge=0)
    matched_rows: int = Field(ge=0)


class RowProvenance(ContractModel):
    row: int = Field(ge=1)
    source_file: Text
    source_record: int = Field(ge=1)


class QueryExecution(ContractModel):
    result: ExecutionResult
    scope: QueryPlan | None = None
    returned_rows: int = Field(default=0, ge=0, le=1000)
    effective_limit: int = Field(default=1, ge=1, le=1000)
    truncated: bool = False
    warnings: list[Text] = Field(default_factory=list)
    provenance: list[RowProvenance] = Field(default_factory=list)
    periods: list[PeriodCoverage] = Field(default_factory=list)

    @model_validator(mode="after")
    def result_shape(self) -> Self:
        if self.result.outcome.status != "answered":
            if self.returned_rows:
                raise ValueError("Nonanswers cannot have returned rows")
            return self
        table = self.result.outcome.data
        if self.returned_rows != len(table.rows):
            raise ValueError("returned_rows must match the answer table")
        # The existing generic Scalar union prefers strings on JSON decoding.
        # Restore only explicitly typed logical date columns, never guess dates
        # from arbitrary source text or alter the semantic result model.
        for index, column in enumerate(table.columns):
            if column.field == "deal_date":
                for row in table.rows:
                    if isinstance(row[index], str):
                        row[index] = date.fromisoformat(row[index])
        return self
