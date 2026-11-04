# Deterministic query execution (Milestone 3C)

`backend.query.QueryEngine(Settings(...)).execute(plan)` accepts a QueryPlan
object and returns a typed QueryExecution wrapper. It never accepts a SQL string,
dictionary, compiled statement or natural-language question. It revalidates a
serialized copy of the plan, including constructed/mutated models. The pure
`backend.query.compiler.compile_plan(plan)` produces internal parameterized
statements for review; the executor has no compiled-SQL input channel.

The QueryPlan and ExecutionResult models/versions are unchanged. A valid plan
shape does not promise executable semantics; unsupported capabilities produce
the existing typed unsupported outcome with an explanation. No HTTP SQL endpoint,
Groq integration, natural-language generation, ingestion, or frontend is added.
Existing liveness and readiness behavior stays independent of query execution.

## Run locally

From the repository root with the validated snapshot present:

```sh
uv run --project backend python -m backend.query \
  --plan docs/examples/deal-count.json --database data/processed/uzex.duckdb
```

The CLI reads a QueryPlan JSON file and prints QueryExecution JSON. It exits 0
for answered/no_match, 1 otherwise. Invalid/unreadable inputs produce a sanitized
typed validation error. No database is created or modified. A missing database
produces a typed execution error. Python callers should parse untrusted JSON with
QueryPlan.model_validate_json before calling the engine; malformed input is not
an alternative SQL API.

## Supported patterns

| Capability | Execution support |
| --- | --- |
| Exact deal lookup | Approved fields; exact string ID, source filename and logical-record provenance |
| deal_count | One count per deal, including metre/square-metre records |
| deal_value | Original UZS or USD amounts, selected or grouped by currency; never a mixed total |
| physical_volume | Exact quantity × lot size; one selected unit or separate approved unit groups |
| delivered_lots | Sum only when all matching delivered quantities are known |
| average_unit_price | Weighted sum(amount)/sum(physical volume), with required product/currency/unit scope |
| Text filters | Bound eq/ne/in/not_in over approved exact source fields; derived delivery labels have a verified normalized vocabulary |
| Numeric predicates | Bound eq/ne/gt/gte/lt/lte over approved fields; executed-price predicates use exact cross-multiplication |
| Grouping | All mapped dimensions except product_id; broker roles, official status and delivery completion remain separate |
| Sorting and ranking | Approved selected fields only; group keys break ties; NULLS LAST |
| Period comparison | One metric and shared scope across disjoint baseline/target periods; difference and percentage change |
| Clarification / unsupported input | Typed ambiguous/unsupported output, with no database access |

Exact source product names remain distinct, including spelling, case, script and
attributes. No LOWER/TRIM/transliteration/fuzzy matching is introduced. The
existing plan Text model strips outer whitespace during validation; the executor
does not change that contract, so source strings whose outer whitespace matters
cannot be precisely requested through those Text filters. Normalized product
names, product_id and other unverified entity/region alias filters are unsupported.

## Currency and units

Source money requires one selected UZS/USD currency or currency grouping. The
contract prohibits cross-currency ranking/value sorting without conversion.
Unknown currency mappings prevent a monetary answer; they never become UZS by
default. Unverified currency labels in the date/text scope block monetary
queries even if a canonical-currency filter would otherwise exclude them; the
executor cannot assume those rows belong to another currency. Count/money queries over metre or square-metre records remain supported
when no unsupported physical-unit projection is requested.

**convert_to_uzs remains explicitly unsupported.** Ingestion and the semantic
contract still identify unverified transaction-calendar/timezone and FX
precision/rounding rules. Verified positive same-date rates alone do not approve
those rules. The engine never sums the partially populated native-only
transaction_amount_uzs column as if it were a converted grand total. Tests verify
rate availability for 6,590 USD records and typed rejection of conversion rather
than manufacturing converted answers.

Mass conversion uses the verified exact relationship 1 tonne = 1000 kg. It applies
per-deal decimal multipliers 1000 or 0.001, never floating-point division. The
policy restricts the population to source kg/tonne units and reports exclusions.
Single-unit policies similarly restrict the population. Unrecognized source unit
labels block physical requests before unit exclusions; verified metre/square-metre
labels can safely be excluded from a requested mass or single-unit population. These requested exclusions
are distinct from missing evidence. Incompatible unit families never convert.

The result contract's unit vocabulary excludes metre/square metre. Physical
queries/projections or unit-group results whose selected population still contains
unmapped units return typed unsupported outcomes. Explicit single/mass policies
can safely exclude those units; a resulting empty population is no_match. Count
and money grouping by measurement_unit is also unsupported if unmapped unit rows
would appear: merging them into one NULL unit bucket would be misleading.

Average and executed prices divide by the policy-unit physical denominator,
never by starting_price. Scalar ratios and percentages use Decimal precision 38,
ROUND_HALF_EVEN, reported as a technical representation warning; this does not
approve FX rounding. Ratio calculations use exact rational intermediate values;
weighted-price ranking compares exact fractions before display rounding.

Exact price sorting/ranking must evaluate all groups. It fetches at most 1,001
internal group rows and returns unsupported if there are more than 1,000 groups,
instead of guessing a ranking from a truncated subset. Narrowing scope/grouping
can make such a request executable. Other rankings/sorts are compiled into SQL.
Arithmetic overflow/resource failures produce typed errors, with no float fallback.
Numeric thresholds beyond lossless DECIMAL(38,10) execution precision are typed
unsupported even though the extensible semantic model permits such decimals.

## NULLs, empty sets and comparisons

Missing metric or numeric-predicate inputs yield insufficient_data rather than a
SUM that silently omits records. Numeric predicate coverage is conservative over
the complete currency/unit population before numeric filtering. Another numeric
predicate that might exclude an unknown record does not waive that check.
Lookup may faithfully display NULL fields with a warning; it does not impute them.
A zero price denominator yields NULL with zero_denominator metadata. A comparison
with an undefined period aggregate is insufficient_data, not a zero baseline.

Text predicates follow SQL three-valued logic: NULL values match none of
eq/ne/in/not_in. There is no implicit NULL-to-empty or NULL-to-zero conversion,
and the current contract has no is_null predicate. Missing delivered lots produce
NULL delivery_completion, never not_delivered or payment completion. Official
status preserves the source label and is independent of the derived quantity state.

Successful evaluation with no matching records returns no_match, with complete
coverage and verified evidence. It is not missing data. In comparisons, an empty
period contributes zero to additive metrics; an empty average remains undefined.
Both periods empty produce no_match. Baseline zero yields NULL percentage_change
with zero_baseline metadata (including zero-to-zero); absolute difference remains
defined when period values are defined. Periods use inclusive source DATE values
and are not automatically normalized for different day counts.

## Scope, evidence and execution boundary

QueryExecution contains:

- result: the unchanged ExecutionResult with outcomes and evidence/coverage;
- scope: a revalidated plan copy, preserving language and all explicit policies;
- returned_rows, effective_limit, truncated, and technical warnings;
- lookup source filename/logical-record provenance;
- separate baseline/target coverage for comparisons.

Evidence comes from the snapshot's source hashes, not from user input. Fixed
joins verify all dimensions, so evidence includes the deal and dimension source
manifests with their logical roles. Comparisons identify baseline/target evidence
separately. Covered/evaluated counts are at deal grain, not aggregate-group count:
evaluated_rows counts the date-scoped candidate population and matched_rows counts
records after text, currency/unit and numeric policies. Result limits do not
truncate coverage. Nonanswered failures may retain unknown coverage if evaluation
could not safely finish; partial numerical totals are never returned.

Before querying, the engine checks schema version, mapped columns/storage types,
primary keys, successful build evidence, source manifest entries, fact counts and
exact-key coverage. The only joins are contract_id, seller/buyer INNs and
seller/buyer broker codes. LEFT joins plus unique lookup keys preserve facts;
unmatched keys fail closed instead of disappearing. No product-name contract
join or broker-INN participant join exists. This assumes an operator-managed
immutable validated snapshot; it does not rehash/reconcile CSV bytes per request.
Independent integration tests reconcile the actual database against raw audit
strings and assert the database and all source hashes stay unchanged.

All user-controlled identifiers-as-values, dates, text, regions, numeric values
and result limits are bound parameters. Physical identifiers, expressions,
operators, joins and sort directions come only from closed code allowlists.
No SELECT * is used to expose extra physical columns. Compiled statements are
SELECT/WITH only. Connections go through DuckDBAdapter with read_only=True,
disabled external access/extensions, locked configuration and bounded slots.
Errors expose stable public codes, not engine SQL, paths or stack traces.

UZEX_QUERY_MAX_RESULTS controls 1–1000 returned rows (default 1000). The plan's
lower limit/ranking count is respected; server reductions and truncation are
reported. Existing UZEX_DATABASE_QUERY_TIMEOUT_MS, UZEX_DATABASE_MEMORY_MB,
UZEX_DATABASE_THREADS and UZEX_DATABASE_MAX_CONNECTIONS apply. Timeout is per
statement, not a global wall-clock deadline; engine memory budgets are not hard
process RSS limits. Schema/coverage verification and bounded data queries share
one read-only connection. No persisted cache, database write or ingestion occurs.

The wrapper verifies returned row counts and restores explicitly typed deal_date
cells from ISO strings on JSON decoding; it never guesses dates from product or
other source text. The underlying generic semantic Scalar union is unchanged.

The output language is retained as uz/ru metadata; source values stay untranslated
and technical messages are fixed strings. Natural-language answer generation is
intentionally outside this milestone.

## Verification

```sh
cd backend
uv run pytest
uv run ruff check .
uv run pytest tests/test_query_integration.py -q
```

Real integration tests run when the local snapshot is present and produce ignored
`data/reports/query-integration.json` and `.md`. They independently reconcile
counts by year, statuses and delivery states, exact contract and broker-role joins,
source currency totals, rate evidence/conversion rejection, exact mass conversion,
weighted-price ordering, missing values, lookup and period comparisons. Synthetic
fixtures test injection, invalid/constructed plans, unsafe/ambiguous fields,
unsupported normalization/units, row bounds, resource errors and deterministic ties.
