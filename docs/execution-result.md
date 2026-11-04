# Future execution-result contract 1.1

`backend.semantic.ExecutionResult` defines response validation only. No executor,
SQL compiler, API route, transaction record, or numerical answer is produced here.
Its JSON Schema is available through `ExecutionResult.model_json_schema()`.

The envelope requires version 1.1, language uz/ru, coverage, and outcome. Evidence
is a list, empty by default for requests that never execute. All nested models
forbid extra fields. Public error messages must be sanitized by the future
executor; schema validation cannot detect secrets embedded in free text.

## Outcomes

| outcome.status | Payload | Required interpretation |
| --- | --- | --- |
| answered | data: AnswerTable | Complete evaluation, matching records and verified evidence |
| no_match | message | Complete evaluation with exactly zero matching records; no data payload |
| insufficient_data | explanation | Coverage issues prevent a supported complete answer; no data payload |
| ambiguous | question, optional options | Clarification needed; do not query speculatively |
| unsupported | explanation | Unsupported operation or capability; no fabricated fallback |
| error | code, message | execution_failed, validation_failed, or internal_error; safe public message |

answered and no_match require nonempty evidence with all mapping_verified flags
true. answered requires matched_rows > 0; no_match requires matched_rows = 0.
An evaluated empty set is not insufficient_data. insufficient_data requires at
least one coverage issue; no other nonanswer carries numerical result data.
Unknown result states, SQL fields, and arbitrary output fields are rejected.

## Evidence and coverage

Each Evidence entry carries source_id, dataset_version, nonempty logical_fields,
and mapping_verified. These are supplied by a trusted future executor from the
actual dataset manifest, not invented by an interpreter. Entries may represent
separate files, periods, rate tables, or normalization mappings. They must cover
all data used by an answer, including conversions and both comparison periods.
No physical paths or columns are assumed by this contract.

Coverage has state complete/partial/unknown/unavailable, optional nonnegative
strict-integer evaluated_rows and matched_rows, and an issues list. Complete
coverage requires both counts; matched_rows cannot exceed evaluated_rows.
Counts refer to deal-grain records, never joined row multiplicity or returned
aggregate rows. For comparisons they cover the union of both disjoint periods;
evidence must identify each period separately. Limits truncate output groups,
not evidence coverage. Requested currency/unit population exclusions are not
missing evidence, but the executor must disclose their scope in evidence fields
and public context. Missing mappings/rates or silent record loss are incomplete.

Issues have code and description. Codes: missing_rate, unverified_mapping,
missing_values, duplicate_id, zero_baseline, zero_denominator, other. Complete
coverage permits zero_baseline/zero_denominator calculation issues, but forbids
unresolved missing-data issues. Undefined arithmetic can coexist with complete
record coverage. Partial or unknown coverage can never produce answered/no_match.
An empty evidence list is acceptable for ambiguous/unsupported/error outcomes.
No-match remains distinct from no available database or no verified mappings.

## Answer table

AnswerTable has 1–30 unique allowlisted ResultColumn objects and 1–1000 rows.
Rows must have exactly one cell per column, in column order. Cells are scalar
strings, integers, finite decimals, dates, or null. This transport shape does not
prove numerical correctness; a future executor must enforce field-specific value
types beyond finite numeric cells, ensure counts are nonnegative integers,
and validate metadata against the
approved plan. Free strings are values, never expressions or executable SQL.

Result fields are approved metrics, lookup fields, dimensions, or comparison
fields baseline, target, absolute_difference, percentage_change. Comparison
columns require metric to state the metric being compared; other columns forbid
metric. Comparison columns in one table must reference the same metric.
Currency metadata is allowed for monetary values only. Physical unit metadata
must be an approved physical unit. Monetary/physical columns require explicit
currency/unit metadata or a selected currency/measurement_unit column for grouped
source values. deal_count requires unit transactions, delivered_lots and
deal_quantity_lots require unit lots. Percentage columns require unit percent
and no currency. Difference columns retain the underlying metric's units/currency.

A null percentage_change requires a zero_baseline coverage issue. The future
executor must return null for baseline zero, including zero-to-zero, and must
never emit infinity or an invented zero percentage. Undefined source period
values are insufficient_data instead. This contract validates metadata and shape;
A supplied zero baseline also rejects a non-null percentage. Numeric result
strings are parsed as finite decimals for lossless JSON round trips. Other
formula evaluation and linkage to request/evidence remain executor duties.

## Milestone 3C implementation

The model remains unchanged. `backend.query.QueryExecution` wraps ExecutionResult
with the original revalidated plan scope, row limits/truncation, technical warnings,
lookup record provenance and comparison-period coverage. This additive wrapper
addresses execution metadata absent from the original result envelope without
changing its allowlists or outcome rules. See [query-execution.md](query-execution.md)
for supported mappings, NULL handling, ratio precision and unsupported semantics.
