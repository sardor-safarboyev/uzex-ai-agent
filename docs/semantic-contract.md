# Semantic contract 1.1

Currency-scoped count extension: an explicit source-currency money policy may
select USD or UZS transactions for nonmonetary aggregates/comparisons. Counts
retain transaction units; no amount conversion occurs. The exact contract join,
currency mapping, bound predicates and verified fact grain are unchanged.
Currency-less nonmonetary money policies and nonmonetary conversion are invalid.

Unavailable years are determined from distinct dates in the verified snapshot,
not the current calendar, LLM claims, or duplicated configured year bounds.
Missing coverage is not an observed zero. API classification precedes provider
interpretation for explicit date questions and carries the coverage as metadata.

The supplied typed schema has no net profit/expenses, employee counts, or paid-tax
amounts. `vat_payer_source` denotes status only, not paid taxes. Product rankings
cannot establish causes of leadership. Median and forecasts are not supported
operations; these limitations never produce inferred numerical results.

Analytical grouping extension: `deal_year` is the calendar year extracted from
the verified deal date, not source filename, ingestion year or contract year.
It is available to version 1.1 aggregates only. All year filters continue to use
inclusive date ranges. A product ranking by deal count counts transactions for
each exact source product name; it makes no claim about physical volume or
normalized product identity. Unqualified “most sold” requires measure
clarification. Region results denote the source warehouse region explicitly.
Totals must retain one currency or separate currency groups; omitting currency
from a natural-language total requires clarification, never a mixed USD/UZS sum.

This is a logical vocabulary. Profiled CSV headers and the validated ingestion
snapshot now have explicit [physical mappings](physical-schema.md). Unsupported
normalization and conversion semantics still require approval before execution.
The code registry is `backend.semantic.registry.METRICS`; the validated envelope
is `backend.semantic.QueryPlan`. Neither generates SQL nor executes a query.

## Evidence status

User-supplied README/screenshot knowledge reports deals_2022.csv through
deals_2026.csv with 500,000 synthetic transactions total; contracts.csv with
approximately 6,616 contracts; participants.csv with approximately 14,392
participants; brokers.csv with approximately 120 brokers; and usd_rates.csv
with daily USD/UZS rates. Milestones 3B.1–3B.2 verified row counts, identifiers,
exact-key coverage and date-rate availability for the recorded source hashes.
Business meanings beyond the documented ingestion mappings remain unresolved.
No results are invented.

## Metrics

| Identifier | Definition | Required logical fields | Output |
| --- | --- | --- | --- |
| deal_count | Count transactions at one row per deal; joins must not multiply counts | deal_id | transactions |
| deal_value | Sum executed transaction amounts | transaction_amount, currency | selected currency |
| physical_volume | Sum deal_quantity_lots × lot_size | deal_quantity_lots, lot_size, measurement_unit | selected physical unit |
| delivered_lots | Sum delivered lots | delivered_lots | lots |
| average_unit_price | Sum executed amounts / sum physical volume | transaction_amount, currency, deal_quantity_lots, lot_size, measurement_unit, product | currency per physical unit |

Deal count is neither lot quantity nor physical volume. `delivered_lots` does not
mean delivered physical volume; lot sizes may differ. Average unit price is a
volume-weighted executed price, never starting price and never an unweighted
average of prices. Version 1 requires a single product filter or product grouping
for that metric. Even within a product, attribute comparability requires verified
mappings. Zero denominator gives an undefined price, never zero or infinity.

## Dimensions and values

Allowlisted dimensions are deal_date (daily), warehouse_region, seller_inn,
buyer_inn, seller_broker_code, buyer_broker_code, product, product_id,
contract_type, contract_form, status, currency,
measurement_unit, and delivery_completion. No company registration region is supported.
Warehouse region means the seller warehouse's region. INNs and broker codes are
strings to preserve leading zeros. Broker roles are explicit: seller_broker_code and buyer_broker_code.
Their source mappings and joins must be verified independently. Contract type and form remain distinct.

Raw source strings and normalized identifiers are separate concepts. Text filters
explicitly carry `value_kind=source` (default) or `normalized`. Source filters use
exact source spelling; normalized filters need a verified alias mapping. Mixed
Latin/Cyrillic spelling must not be merged heuristically. Grouping textual fields
uses exact source values. The separate product_id dimension supports normalized
product grouping and normalized-only identifier filters in version 1.1, requiring
a verified, versioned source-to-product mapping before execution. A logical ID
is never inferred from a spelling or transliteration. Codes retain
source identity. `currency`, `measurement_unit`, and `delivery_completion` groupings use
the logical normalized vocabulary. Unsupported or ambiguous entity resolution
must yield an unsupported or clarification outcome, not a guessed filter.

Status preserves official dataset status values and does not infer payment or
delivery completion. Delivery completion is a separate derived concept:
fully_delivered means delivered_lots = deal_quantity_lots > 0;
partially_delivered means 0 < delivered_lots < deal_quantity_lots;
not_delivered means delivered_lots = 0 with positive deal quantity. Missing,
negative, over-delivered, or zero-quantity values require data-quality handling;
they cannot silently become one of these categories. These categories do not
assert payment completion, cancellation, or dataset status labels.

## Currency and units

Monetary metrics require a money policy. `source` with source_currency restricts
the transaction population to UZS or USD; without it, group_by must include
currency and produces separate totals. `convert_to_uzs` retains UZS amounts and
converts each USD transaction using its transaction-date USD/UZS rate before
aggregation. Ingestion retains contract currency through the validated unique
contract-number join, but does not perform USD conversion. Conversion
requires the additional logical fields deal_date and usd_uzs_rate, a verified
date/time convention, unique rates, and defined precision/rounding rules.
Missing rates must block affected answers or be disclosed as incomplete coverage;
never assume a rate or silently drop records. No USD target or fallback rate is
supported in v1. Converted results cannot group by source currency.

Physical metrics require a units policy. `single` restricts the population to a
specified normalized unit; `group_by_unit` keeps units in separate groups.
Supported identifiers are kg, tonne, litre, cubic_metre, piece. These are an
allowlist for future mappings, not assertions about actual dataset spellings.
Version 1.1 also supports `convert_mass` with target unit kg or tonne. Only
verified source kg/tonne mappings enter this population: one tonne = 1000 kg
exactly. Convert per-deal physical volume before aggregation. Executed unit prices
use the converted physical denominator (currency/kg vs currency/tonne); never
multiply unit prices by the volume conversion factor. No litre, piece, or cubic
metre conversion is permitted, including density-based conversion. Missing or
ambiguous unit mappings are insufficient data, not permission to guess. The policy
restricts the population to the mass family; excluded incompatible families must
be disclosed in future coverage metadata. `single` retains its original behavior
and performs no conversion. `group_by_unit` still keeps source units separate. Currency and unit filters
are expressed only through policies to avoid contradictory constraints.

Ranking and metric sorting require comparable values: one source currency or
UZS conversion for monetary metrics; one selected unit or mass conversion for
physical metrics.
Incompatible groups can be displayed, but cannot be ranked or sorted by values.

## Evidence and empty results

Validation proves contract shape and semantic compatibility, not data availability
or permission to execute. A later compiler must verify mappings, row grain,
join cardinality, aliases, units, currencies and conversion coverage before running
approved operations against read-only DuckDB. Unknown mappings or unsupported
units require clarification or an unsupported outcome.

No matching records is a legitimate empty result after successful evaluation,
not automatically missing evidence. A future response must distinguish empty
matches from unavailable data, invalid mappings, missing conversion rates, and
undefined calculations. Counts over an empty set can be zero; undefined prices
remain undefined. The future typed result envelope is documented in [execution-result.md](execution-result.md).


## Record lookup and numeric predicates

Lookup selects one deal_id exactly, with no fuzzy search, aggregation, sorting,
conversion, or arbitrary projection expressions. IDs remain strings. The
LookupField enum is the authoritative projection allowlist: deal_id, all current
dimensions, deal_quantity_lots, delivered_lots, lot_size, transaction_amount,
physical_volume, and executed_unit_price. Monetary projections require currency
selection; lot_size/physical_volume/executed_unit_price require measurement_unit.
Raw values and source units/currency are preserved. A duplicate deal_id is
insufficient_data, never an arbitrary first record. Missing ID is no_match only
after verified complete evaluation. Normalized product_id selection needs mapping
verification; it never replaces the source product name implicitly.

Numeric predicates are per-deal, before aggregation, and combined with all other
predicates using AND. Allowlisted fields: deal_quantity_lots, delivered_lots,
transaction_amount, physical_volume, executed_unit_price. Executed unit price is
transaction_amount / (deal_quantity_lots * lot_size), never starting price.
Operators: eq, ne, gt, gte, lt, lte. Values are finite nonnegative Decimal values;
JSON numbers or decimal strings are accepted, booleans are rejected. Nonnegative
thresholds do not establish that source data are clean; invalid source values
must be assessed at execution. Missing values and zero price denominators require
coverage handling, not silent predicate exclusion. No HAVING or expression syntax.

Monetary predicates require one source currency or convert_to_uzs, even for a
count-only query. Physical predicates require single or convert_mass. Policies
apply to the whole request population and to predicate values as well as metrics.
Convert amounts and physical quantities before evaluating thresholds. Price
thresholds are expressed in policy currency per policy unit. Grouped mixed
currency or mixed unit predicates are forbidden.

## Period comparison

Comparison applies one aggregate definition and identical filters, money and unit
policies to two inclusive, disjoint date ranges, baseline strictly before target.
It supports exactly one metric and no grouping, sorting, ranking, or nested date
range. Period lengths may differ; no automatic per-day normalization occurs.
Absolute difference = target - baseline, retaining the metric's currency/unit.
Percentage change = (target - baseline) / baseline * 100, in percent.
A zero baseline, including zero-to-zero, produces null percentage_change with
zero_baseline metadata, never zero percent or infinity. Absolute difference is
still defined when both period values are defined. A missing/undefined period
value is insufficient_data; it is not a zero baseline. A completely evaluated
empty period has zero for additive totals/counts, but average_unit_price remains
undefined. Both periods empty means no_match. One empty additive period can
participate in comparison; evidence/coverage must cover both periods.

## Corrections and compatibility

The plan envelope accepts 1.0 for existing aggregate/clarification/unsupported
shapes and 1.1 for new capabilities. Lookup, comparison, numeric predicates,
product_id, and convert_mass require 1.1. The ambiguous broker_code and fulfillment
identifiers are rejected in both versions as documented semantic corrections:
choose seller_broker_code or buyer_broker_code based on user intent (otherwise
clarify), and replace fulfillment with delivery_completion. Old fully_fulfilled,
partially_fulfilled, unfulfilled labels become fully_delivered,
partially_delivered, not_delivered. They describe delivery quantities only and
never payment completion. No automatic broker-role migration is safe.


## Ingestion boundary (Milestone 3B.2)

The QueryPlan contract stays at versions 1.0/1.1. The separate ingestion schema
version 1.0 maps observed columns into raw audit and typed tables; it does not
add a semantic compiler or execute plans. See [physical-schema.md](physical-schema.md)
for every field mapping, source provenance and unresolved product/region/unit/FX
semantics. USD rate candidates are retained, but applied rates and converted USD
amounts remain NULL. Starting price remains separate from executed unit price,
and blank delivered quantities do not become zero or payment completion.

## Response presentation (agent quality fix)

The ask API accepts language `auto` (default), `uz`, or `ru`. Explicit language
overrides win; automatic mode uses conservative Uzbek/Russian question-word cues
and falls back to Uzbek for ambiguous input. Source names and values are never
translated. The effective language is applied to a revalidated plan before
execution, including nonanswers and provider failures.

Unsupported requests may identify `currency_conversion`, `unsupported_unit`,
or `unsupported_date` in addition to the existing reasons. These are presentation
restrictions, not additional executable capabilities. Currency conversion remains
unsupported because rate application and rounding rules are unverified.
