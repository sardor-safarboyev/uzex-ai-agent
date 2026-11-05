"""Validated interpretation contract, never executable SQL."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from backend.semantic.registry import (
    MASS_UNITS,
    METRICS,
    MONETARY_FIELDS,
    PHYSICAL_FIELDS,
    Currency,
    Dimension,
    LookupField,
    Metric,
    NumericField,
    Unit,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Text = Annotated[StrictStr, Field(min_length=1, max_length=500)]


class DateRange(ContractModel):
    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start > self.end:
            raise ValueError("date range start must be on or before end")
        return self


class Filter(ContractModel):
    field: Dimension
    operator: Literal["eq", "ne", "in", "not_in"]
    values: Annotated[list[Text], Field(min_length=1, max_length=100)]
    value_kind: Literal["source", "normalized"] = "source"

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if self.field == Dimension.DEAL_DATE:
            raise ValueError("use date_range for deal_date filters")
        if self.operator in {"eq", "ne"} and len(self.values) != 1:
            raise ValueError("eq and ne require exactly one value")
        if len(set(self.values)) != len(self.values):
            raise ValueError("filter values must be unique")
        if self.field == Dimension.PRODUCT_ID and self.value_kind != "normalized":
            raise ValueError(
                "product_id requires normalized values and verified mappings"
            )
        vocabularies = {
            Dimension.CURRENCY: {c.value for c in Currency},
            Dimension.MEASUREMENT_UNIT: {u.value for u in Unit},
            Dimension.DELIVERY_COMPLETION: {
                "fully_delivered",
                "partially_delivered",
                "not_delivered",
            },
        }
        if self.field in vocabularies:
            if self.value_kind != "normalized":
                raise ValueError(
                    "currency, measurement_unit and delivery_completion "
                    "use normalized values"
                )
            if not set(self.values) <= vocabularies[self.field]:
                raise ValueError(f"unsupported normalized value for {self.field}")
        return self


class MoneyPolicy(ContractModel):
    mode: Literal["source", "convert_to_uzs"]
    source_currency: Currency | None = None

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if self.mode == "convert_to_uzs" and self.source_currency is not None:
            raise ValueError("conversion includes UZS and USD; omit source_currency")
        return self


class UnitPolicy(ContractModel):
    mode: Literal["single", "group_by_unit", "convert_mass"]
    unit: Unit | None = None

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if self.mode == "group_by_unit" and self.unit is not None:
            raise ValueError("group_by_unit forbids unit")
        if self.mode == "single" and self.unit is None:
            raise ValueError("single requires unit")
        if self.mode == "convert_mass" and self.unit not in MASS_UNITS:
            raise ValueError("convert_mass requires target unit kg or tonne")
        return self


class NumericFilter(ContractModel):
    field: NumericField
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    value: Annotated[Decimal, Field(allow_inf_nan=False, ge=0)]

    @field_validator("value", mode="before")
    @classmethod
    def reject_boolean(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("numeric filter value must not be boolean")
        return value


class Sort(ContractModel):
    field: Metric | Dimension
    direction: Literal["asc", "desc"] = "desc"


class Ranking(ContractModel):
    metric: Metric
    direction: Literal["top", "bottom"]
    count: Annotated[int, Field(strict=True, ge=1, le=100)]


class AggregateRequest(ContractModel):
    kind: Literal["aggregate"]
    metrics: Annotated[list[Metric], Field(min_length=1, max_length=5)]
    group_by: Annotated[list[Dimension], Field(max_length=4)] = Field(
        default_factory=list
    )
    filters: Annotated[list[Filter], Field(max_length=20)] = Field(default_factory=list)
    numeric_filters: Annotated[list[NumericFilter], Field(max_length=20)] = Field(
        default_factory=list
    )
    date_range: DateRange | None = None
    money: MoneyPolicy | None = None
    units: UnitPolicy | None = None
    sort: Annotated[list[Sort], Field(max_length=4)] = Field(default_factory=list)
    ranking: Ranking | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=1000)] = 100

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if len(set(self.metrics)) != len(self.metrics):
            raise ValueError("metrics must be unique")
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("group_by dimensions must be unique")
        # Policies alone control these populations, avoiding contradictory filters.
        if any(
            f.field in {Dimension.CURRENCY, Dimension.MEASUREMENT_UNIT}
            for f in self.filters
        ):
            raise ValueError(
                "use money and units policies instead of currency/unit filters"
            )
        monetary_predicates = any(
            f.field in MONETARY_FIELDS for f in self.numeric_filters
        )
        physical_predicates = any(
            f.field in PHYSICAL_FIELDS for f in self.numeric_filters
        )
        monetary = any(METRICS[m].monetary for m in self.metrics) or monetary_predicates
        physical = any(METRICS[m].physical for m in self.metrics) or physical_predicates
        if monetary != (self.money is not None):
            raise ValueError(
                "money policy is required exactly when monetary metrics "
                "or predicates are selected"
            )
        if physical != (self.units is not None):
            raise ValueError(
                "units policy is required exactly when physical metrics "
                "or predicates are selected"
            )
        if monetary_predicates and self.money:
            if self.money.mode == "source" and self.money.source_currency is None:
                raise ValueError(
                    "monetary predicates require one currency or conversion"
                )
        if physical_predicates and self.units and self.units.mode == "group_by_unit":
            raise ValueError("physical predicates require one unit or mass conversion")
        if self.money:
            grouped = Dimension.CURRENCY in self.group_by
            if (
                self.money.mode == "source"
                and not self.money.source_currency
                and not grouped
            ):
                raise ValueError(
                    "source money requires source_currency or group_by currency"
                )
            if self.money.mode == "convert_to_uzs" and grouped:
                raise ValueError(
                    "converted UZS results cannot group by source currency"
                )
        if self.units:
            grouped = Dimension.MEASUREMENT_UNIT in self.group_by
            if (self.units.mode == "group_by_unit") != grouped:
                raise ValueError(
                    "group_by_unit requires measurement_unit grouping; "
                    "single forbids it; convert_mass also forbids source-unit grouping"
                )
        if Metric.AVERAGE_UNIT_PRICE in self.metrics:
            product_filter = any(
                f.field in {Dimension.PRODUCT, Dimension.PRODUCT_ID}
                and f.operator == "eq"
                for f in self.filters
            )
            if (
                not {Dimension.PRODUCT, Dimension.PRODUCT_ID}.intersection(
                    self.group_by
                )
                and not product_filter
            ):
                raise ValueError(
                    "average_unit_price requires one product or product grouping"
                )
        selected = set(self.metrics) | set(self.group_by)
        if any(s.field not in selected for s in self.sort):
            raise ValueError(
                "sort fields must be selected metrics or grouped dimensions"
            )
        if len({s.field for s in self.sort}) != len(self.sort):
            raise ValueError("sort fields must be unique")
        if self.ranking:
            if not self.group_by or self.ranking.metric not in self.metrics:
                raise ValueError("ranking requires grouping and a selected metric")
            if self.sort or self.ranking.count > self.limit:
                raise ValueError("ranking forbids sort and count must not exceed limit")
            if METRICS[self.ranking.metric].monetary and self.money:
                if self.money.mode == "source" and self.money.source_currency is None:
                    raise ValueError(
                        "ranking money requires one currency or conversion"
                    )
            if METRICS[self.ranking.metric].physical and self.units:
                if self.units.mode == "group_by_unit":
                    raise ValueError("ranking physical metrics requires one unit")
        # Sorting values across incompatible groups is also a comparison.
        for order in self.sort:
            if order.field in METRICS:
                definition = METRICS[order.field]
                if definition.monetary and self.money:
                    if (
                        self.money.mode == "source"
                        and self.money.source_currency is None
                    ):
                        raise ValueError(
                            "sorting money requires one currency or conversion"
                        )
                if (
                    definition.physical
                    and self.units
                    and self.units.mode == "group_by_unit"
                ):
                    raise ValueError("sorting physical metrics requires one unit")
        return self


class LookupRequest(ContractModel):
    kind: Literal["lookup"]
    deal_id: Text
    select: Annotated[list[LookupField], Field(min_length=1, max_length=22)]

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if len(set(self.select)) != len(self.select):
            raise ValueError("lookup select fields must be unique")
        monetary = {LookupField.TRANSACTION_AMOUNT, LookupField.EXECUTED_UNIT_PRICE}
        physical = {
            LookupField.LOT_SIZE,
            LookupField.PHYSICAL_VOLUME,
            LookupField.EXECUTED_UNIT_PRICE,
        }
        if (
            monetary.intersection(self.select)
            and LookupField.CURRENCY not in self.select
        ):
            raise ValueError("lookup monetary fields require currency selection")
        if (
            physical.intersection(self.select)
            and LookupField.MEASUREMENT_UNIT not in self.select
        ):
            raise ValueError(
                "lookup physical fields require measurement_unit selection"
            )
        return self


class ComparisonRequest(ContractModel):
    kind: Literal["comparison"]
    baseline: DateRange
    target: DateRange
    aggregate: AggregateRequest
    changes: Annotated[
        list[Literal["absolute_difference", "percentage_change"]],
        Field(min_length=1, max_length=2),
    ]
    zero_baseline: Literal["undefined"] = "undefined"

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if self.baseline.end >= self.target.start:
            raise ValueError(
                "comparison periods must be disjoint with baseline before target"
            )
        query = self.aggregate
        if len(query.metrics) != 1 or query.group_by:
            raise ValueError("comparison requires exactly one metric and no grouping")
        if query.date_range or query.sort or query.ranking:
            raise ValueError(
                "comparison aggregate forbids date_range, sort and ranking"
            )
        if len(set(self.changes)) != len(self.changes):
            raise ValueError("comparison changes must be unique")
        return self


class ClarificationRequest(ContractModel):
    kind: Literal["clarification"]
    reason: Literal["ambiguous_entity", "ambiguous_metric", "currency", "unit", "other"]
    question: Text
    options: Annotated[list[Text], Field(max_length=10)] = Field(default_factory=list)


class UnsupportedRequest(ContractModel):
    kind: Literal["unsupported"]
    reason: Literal[
        "unsupported_operation",
        "unverified_mapping",
        "unavailable_data",
        "currency_conversion",
        "unsupported_unit",
        "unsupported_date",
    ]
    explanation: Text


class QueryPlan(ContractModel):
    version: Literal["1.0", "1.1"]
    language: Literal["uz", "ru"]
    request: Annotated[
        AggregateRequest
        | LookupRequest
        | ComparisonRequest
        | ClarificationRequest
        | UnsupportedRequest,
        Field(discriminator="kind"),
    ]

    @model_validator(mode="after")
    def version_capabilities(self) -> Self:
        if self.version == "1.0":
            if isinstance(self.request, (LookupRequest, ComparisonRequest)):
                raise ValueError("lookup and comparison require version 1.1")
            if isinstance(self.request, AggregateRequest):
                query = self.request
                normalized_product = Dimension.PRODUCT_ID in query.group_by or any(
                    f.field == Dimension.PRODUCT_ID for f in query.filters
                )
                conversion = query.units and query.units.mode == "convert_mass"
                if query.numeric_filters or normalized_product or conversion:
                    raise ValueError(
                        "numeric predicates, product_id and mass conversion "
                        "require version 1.1"
                    )
        return self
