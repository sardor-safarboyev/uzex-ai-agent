# Query plan 1.1

Explicit Uzbek yearly count claims ending in `Tasdiqla` use the existing yearly
`deal_count` aggregate. The claimed number is never a plan filter or result.
After successful execution, the API adds separate `verification` metadata and
compares the claim with the actual database count. Full-string matching excludes
additional instructions. Missing coverage and execution failures are not confirmations.

The exact Uzbek calendar-year percentage-series template returns typed
`unsupported_yearly_series` for a multi-year series: the contract supports one
two-period comparison, not a batch of successive comparisons. An adjacent-year
range uses the existing `comparison` with `changes: ["percentage_change"]`.
Both routes precede Groq and never infer counts or executable SQL.

## Final quality: currency-scoped counts

In version 1.1, a nonmonetary aggregate may use
`money: {"mode":"source","source_currency":"UZS"}` (or USD) to select a
source-currency population. This applies equally to `comparison.aggregate` and
may combine with inclusive date ranges and exact source warehouse-region
filters. It does not convert money or attach currency units to transaction
counts. Version 1.0 rejects this extension. Nonmonetary requests still reject
conversion mode and source policies without a specific currency. Currency text
filters remain forbidden; the typed policy is the single population selector.

The new nonexecuting reason codes are `unavailable_profit`,
`unavailable_employees`, `unavailable_tax`, `unsupported_causality`,
`unsupported_statistic`, and `unsupported_forecast`. The first three surface as
`insufficient_data`; the others as `unsupported`. None authorizes new SQL.

Before interpretation, `/api/ask` checks explicitly requested years against the
distinct actual deal years in a verified read-only snapshot. Missing years
return `insufficient_data`, reason `outside_coverage`, and structured
`availability.available_years` / `missing_years`. No zero count is inferred.
Ordinary empty matches within coverage remain `no_match`. Unavailable/corrupt
snapshot metadata yields a database failure rather than invented coverage.

`truncated` means an unexpected result reduction. Having additional groups beyond
an explicitly requested TOP N does not set it; reducing TOP N below its requested
count because of the server maximum still does. Population coverage is unchanged.

## Analytical reliability extension

Version 1.1 aggregates additionally accept `deal_year` as a grouping/sort dimension.
It is the integer calendar year of the verified logical `deal_date`, compiled
through a fixed allowlisted expression. Version 1.0 rejects this addition.
Neither `deal_year` nor `deal_date` accepts text filters: use inclusive
`date_range` bounds. `deal_year` is not a lookup field or model-supplied expression.

```json
{"version":"1.1","language":"ru","request":{"kind":"aggregate","metrics":["deal_count"],"group_by":["deal_year"]}}
```

Product top-N uses `product`, `deal_count`, an explicit date range and
`ranking: {"metric":"deal_count","direction":"top","count":5}`. It counts
deals for exact source product names. “Most sold” without a measure requires
`ambiguous_metric` clarification. Monetary totals without currency require
`currency` clarification. The only supported region is the warehouse region,
labeled explicitly in the result; seller/buyer geography remains unverified.

Comparison questions use the existing comparison request: two disjoint inclusive
periods, one metric, and deterministic arithmetic in the executor.
Anchored question templates can construct these same validated plans before the
provider call, including nonexecuting clarification plans. Unrecognized wording
or additional clauses go through the existing interpreter; templates never drop
constraints. Both paths revalidate through the same compiler and executor.

`QueryPlan.model_validate(payload)` and `QueryPlan.model_validate_json(text)`
validate the contract. `QueryPlan.model_json_schema()` exports its JSON Schema.
Use runtime validation too: cross-field rules are not fully captured in JSON
Schema. All objects reject extra fields, including SQL-bearing fields. Free text
is data, never executable code. No API endpoint or compiler is added in this milestone.

Required envelope keys are `version: "1.0" | "1.1"`, `language: "uz" | "ru"`, and
`request`. Version and language have no defaults. Language selects response
language, not dataset-value translation. Unknown versions require explicit future
migration; they are never silently accepted.

## Aggregate example

```json
{
  "version": "1.0",
  "language": "uz",
  "request": {
    "kind": "aggregate",
    "metrics": ["deal_value"],
    "date_range": {"start": "2022-01-01", "end": "2026-12-31"},
    "filters": [
      {"field": "product", "operator": "eq", "values": ["Paxta"], "value_kind": "source"}
    ],
    "money": {"mode": "convert_to_uzs"},
    "group_by": ["warehouse_region"],
    "ranking": {"metric": "deal_value", "direction": "top", "count": 10},
    "limit": 10
  }
}
```

This is a structural example, not a claim that the product exists. The date range
is inclusive at both ends using logical transaction dates; execution time-zone
mapping is still unverified. Empty filters/date range mean the full supplied
population, subject to money/unit population restrictions.

`metrics` contains 1–5 unique approved metric IDs. `group_by` contains up to four
unique approved dimensions. No grouping yields one overall aggregate.
`filters` contains at most 20 predicates combined with AND; OR and nested boolean
expressions are deferred. Operators are eq, ne, in, not_in. eq/ne require one
value; membership operators accept 1–100 unique nonempty strings. Fuzzy matching, date predicates, arbitrary expressions and SQL are
unsupported. Numeric predicates use the separate typed numeric_filters list in 1.1. Use date_range for dates; use money/units policies for currency and
unit population selection. Unknown fields/operators are rejected. Text is bounded
to 500 characters; identifiers must be strings, not coerced numbers.

`money` is required for monetary metrics or numeric monetary predicates.
`units` is required for physical metrics or numeric physical predicates.
For example, a physical-volume request uses
`"units": {"mode": "single", "unit": "kg"}` or
`"units": {"mode": "group_by_unit"}` with measurement_unit grouping.
Average price additionally needs product grouping or an eq product filter.
See [metric semantics](semantic-contract.md) for population and comparability rules.

`sort` accepts at most four unique selected metrics or grouped dimensions, with
asc/desc (default desc). `ranking` specifies a selected metric, top/bottom, and
count 1–100; it requires grouping and excludes sort. `limit` is a strict integer
1–1000 (default 100); ranking count must not exceed it. Booleans and numeric strings
are not limits. Ranking is global over groups, not a per-partition window.
A future compiler must use grouped dimension keys as stable tie breakers, choose
exactly the requested count where available, and never include all ties implicitly.
Absent sort/ranking, no row-order meaning is promised. A limit does not imply top-N.

## Clarification example

```json
{
  "version": "1.0",
  "language": "ru",
  "request": {
    "kind": "clarification",
    "reason": "currency",
    "question": "В какой валюте показать сумму: UZS или USD?",
    "options": ["UZS", "USD"]
  }
}
```

Reasons: ambiguous_entity, ambiguous_metric, currency, unit, other. A nonempty
question is required; options are optional (at most ten). This outcome cannot
carry aggregate fields and must not trigger a query. Ask about ambiguous meanings
such as “volume” (transactions, lots, or physical volume), region, product identity,
currency, or delivery completion instead of choosing a default interpretation.

## Unsupported example

```json
{
  "version": "1.0",
  "language": "uz",
  "request": {
    "kind": "unsupported",
    "reason": "unverified_mapping",
    "explanation": "So‘ralgan maydon uchun tasdiqlangan ma’lumot xaritasi yo‘q."
  }
}
```

Reasons: unsupported_operation, unverified_mapping, unavailable_data. A nonempty
explanation is required; aggregate fields are forbidden. This outcome also must
not trigger a query. No-match results after a valid future query are not
unavailable_data. The future result shapes and coverage rules are defined in
[execution-result.md](execution-result.md); execution remains deferred.


## Version 1.1 lookup example

```json
{
  "version": "1.1",
  "language": "uz",
  "request": {
    "kind": "lookup",
    "deal_id": "identifier-placeholder",
    "select": ["deal_id", "status", "delivery_completion", "transaction_amount", "currency"]
  }
}
```

The identifier is a placeholder, not a supplied transaction. Select 1–22 unique
LookupField identifiers; no wildcard, SQL, filter expression, or arbitrary field.
Numeric values preserve source currency/unit; no lookup conversion policy exists.

## Version 1.1 comparison example

```json
{
  "version": "1.1",
  "language": "ru",
  "request": {
    "kind": "comparison",
    "baseline": {"start": "2024-01-01", "end": "2024-01-31"},
    "target": {"start": "2025-01-01", "end": "2025-01-31"},
    "aggregate": {
      "kind": "aggregate",
      "metrics": ["physical_volume"],
      "units": {"mode": "convert_mass", "unit": "tonne"},
      "filters": [
        {"field": "product_id", "operator": "eq", "values": ["logical-product-placeholder"], "value_kind": "normalized"}
      ],
      "numeric_filters": [
        {"field": "deal_quantity_lots", "operator": "gte", "value": "1"}
      ]
    },
    "changes": ["absolute_difference", "percentage_change"],
    "zero_baseline": "undefined"
  }
}
```

Comparison reuses AggregateRequest with exactly one metric and no grouping,
sorting, ranking, or date_range. Limit is inherited but has no effect on its one
comparison row. `changes` selects one or both operations without duplicates.
zero_baseline only accepts undefined (default); see the semantic contract for
null percentage and empty-period rules. This is a structural plan, not a dataset
mapping or computed result.

## Version 1.1 aggregate additions

`numeric_filters` accepts up to 20 NumericFilter objects, independent of the
existing text filters list. Each has field, operator, value (one finite,
nonnegative decimal threshold). Currency/unit policy requirements are inferred
from numeric fields as well as metrics; source mixed-currency and grouped-unit
thresholds are rejected. Policies apply before predicates and aggregation.

`units.mode=convert_mass` requires unit kg or tonne; other targets are rejected.
It forbids measurement_unit grouping because that dimension denotes source unit.
Sorting/ranking physical metrics is allowed after verified mass conversion.

`group_by: ["product_id"]` groups by normalized product identity; `product`
continues to group source names. product_id filters require value_kind normalized.
A product_id grouping or equality predicate satisfies average_unit_price's product
scope requirement. All normalization mappings must be verified before execution;
validation alone is not an execution approval.

Use seller_broker_code/buyer_broker_code explicitly. Official status and derived
delivery_completion are separate dimensions. The latter accepts normalized
fully_delivered, partially_delivered, not_delivered labels. Legacy broker_code,
fulfillment, and old fulfillment labels are rejected as semantic corrections;
see [migration details](semantic-contract.md#corrections-and-compatibility).

## Milestone 3C execution support

The plan schema and versions are unchanged. The separate deterministic compiler
and read-only executor support the verified subset described in
[query-execution.md](query-execution.md). Accepted plan shapes with unverified FX,
product normalization, unmapped unit projections or unsupported numeric precision
produce typed unsupported outcomes; validation never implies a guessed mapping.

Unsupported reason vocabulary also includes `currency_conversion`,
`unsupported_unit`, and `unsupported_date` for deterministic bilingual
presentation. These reasons never authorize execution. The ask endpoint resolves
its response language (automatic cues or explicit override) and revalidates the
plan with that language before passing it to the unchanged compiler.
