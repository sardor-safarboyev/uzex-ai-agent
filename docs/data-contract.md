# Data contract status

The project will analyze a fixed, supplied synthetic dataset of 500,000 exchange
transactions. Milestone 1 does not load, generate, transform, or query data.
No database file is required for the health endpoint.

The final dataset schema is pending inspection of the supplied dataset and its
owner-provided documentation. No column names, types, keys, units, currencies,
time zones, nullability rules, or table relationships are assumed here.

Before implementing analytics, document and validate the actual file format,
schema, row count, field meanings, units, date/time semantics, missing values,
and dataset version or checksum. Establish supported Uzbek/Russian terminology
and query behavior using those verified definitions.

Future analytics must open DuckDB in read-only mode. Keep original source data
immutable and outside version control and container images. The health endpoint
must remain independent of database availability and Groq credentials.

Milestone 2 records provisional README/screenshot knowledge and defines logical
metrics, dimensions, currency/unit policies, and delivery-completion semantics in
[semantic-contract.md](semantic-contract.md). These are not validated CSV mappings
or a final physical schema. The versioned [query plan](query-plan.md) validates
requests without importing or executing against any dataset.

## Milestone 3A: physical catalog inspection

A database path may now point at an existing DuckDB snapshot. The read-only
adapter and typed inspection service discover catalogs, schemas, table/view names,
column names, ordinal positions, SQL types and nullability from information_schema.
There are no assumed production table or column names and no physical-to-logical
mapping. Inspection does not evaluate view definitions, read transaction rows,
count records, infer foreign keys, normalize entities, or validate metric semantics.
Defaults, comments, SQL definitions and sample values are omitted. Catalog size is
bounded, and overflow fails explicitly rather than silently truncating metadata.

Readiness establishes only that the file can be opened read-only and `SELECT 1`
works. A valid empty database passes; it does not establish evidence sufficient
for analytical answers. Missing/unconfigured files, directories, permissions,
corrupt files, incompatible formats, locking conflicts and resource failures are
reported without creating or repairing a database. Public responses contain
sanitized error codes rather than paths or engine exception details.

No production file or dataset was supplied or imported for this milestone.
Automated fixtures create temporary databases with invented test-only objects and
rows, never real or representative UZEX transactions. A later supplied snapshot
still requires documented provenance, schema validation, row counts and verified
logical mappings before semantic query execution is possible. The semantic
models and registry define logical contracts independently of database access;
catalog inspection does not establish their physical mappings.

## Milestone 3B.1: reproducible source profiling

The nine supplied CSVs are now available in `data/raw/`. Run the standalone
`uv run --project backend python -m backend.profiling` command from the repository
root. Measured findings and unresolved quality issues are in
[profile.md](../data/reports/profile.md); full counts, source headers, hashes,
examples and parsing diagnostics are in [profile.json](../data/reports/profile.json).
These reports supersede earlier provisional counts only for the exact source
hashes recorded in them. Earlier milestone descriptions above are historical.

`backend.profiling.spec` defines **profiling hypotheses using observed physical
CSV headers**, not physical-to-logical runtime mappings. It independently checks
all nine files, requires expected profiling headers, compares yearly deal headers,
and validates row counts with Python and DuckDB. Every input column is loaded
as VARCHAR with empty-string preservation. No integer conversion is used for
identifiers, no whitespace is trimmed from keys, and no name normalization or
source deduplication occurs. Source hashes are checked again after profiling.

Encoding verification uses full strict UTF-8 decoding (BOM supported), or UTF-16
when its BOM is present. Other encodings fail explicitly rather than guessing a
legacy code page or replacing characters. Delimiter detection is followed by
full-file strict CSV validation with doubled-quote escaping. A header-only
fallback permits malformed body rows to be diagnosed when whole-sample delimiter
sniffing fails. Width mismatches, syntax errors and line spans are counted;
malformed sources are excluded as **failed sources**, never silently repaired or
partially imported. Parsed records, physical lines and unresolved syntax-error
groups are distinct measurements, particularly for quoted multiline fields.

Empty fields are reported as empty source strings, not assumed SQL nulls or
zeros. Whitespace-only values and literal NULL/null/N/A/\N markers are counted
separately. Optional product attributes and workflow-dependent payment/delivery
fields can be legitimately empty; those counts are review items, not automatic
proof of corrupt data. In particular, blank delivered quantities do not establish
zero delivery, and delivery counts never prove payment completion.

Date parsing tests DD.MM.YYYY, time parsing tests HH:MM:SS. Numeric diagnostics
accept plain decimal strings or strict three-digit space/NBSP/narrow-NBSP grouping,
and dot/comma decimal separators, at most ten fractional digits, within
DECIMAL(38,10). Exponent notation, malformed grouping, overflow and excess scale
fail rather than being rounded or repaired. Group separator removal and decimal
comma interpretation occur in diagnostic expressions only, never source values;
these are not approved import rules. Reports retain raw failure examples and
parsed ranges. Unclassified fields remain strings; observed integer-like values
do not establish identifier or measurement semantics.

Join diagnostics compare exact source keys and report unmatched rows, target
multiplicity, inner/left join row counts and excess rows. Five independent deal
relationships (contract, seller, buyer, seller broker, buyer broker) are tested,
including their combined multiplication factor. Deliberately unsafe alternate
joins by seller INN or product name are labeled candidate hazards, not proposed
relationships. Broker INN-to-participant INN is exploratory: absence of coverage
does not prove either source invalid or authorize fabricated participant records.
Company registration region remains distinct from the deal warehouse region.

Rate coverage uses observed contract labels Доллар США and Узбекский сум solely
for profiling. It first measures contract and rate-date multiplicity, so duplicate
keys cannot silently inflate the coverage denominator. Only a single contract
record with a known currency and a unique positive rate on the parsed transaction
date is reported rate-ready for USD. Missing/ambiguous contracts, unsupported
currencies, invalid dates, duplicate/invalid rates and date gaps remain explicit.
No conversion is performed, no alternate rate date is selected, and no mixed
currency values are summed. Daily date matching does not settle time-zone or
rounding semantics.

Source category and script statistics preserve exact names. Product attributes,
Latin codes and Cyrillic names may naturally coexist; mixed-script flags do not
identify aliases. Exact name variation within contract keys is measured without
merging variants. The observed metre and square-metre labels require explicit
semantic review; neither belongs to the mass-unit conversion family. Confirm
units, product identity, source grain and approved join roles before any future
import or compiler implementation.

Reports omit wall-clock timestamps for reproducibility, record Python/DuckDB and
profiler-code fingerprints, and include bounded source-value examples (100 values,
5 duplicate/error examples). JSON contains full-data counts, not full value
dictionaries; Markdown displays only the top 15 source values per field. Profiles
are local ignored artifacts, not a committed source manifest or public dataset.
The small profiler tests use invented fixtures and make no UZEX result claims.

## Milestone 3B.2: validated ingestion

The offline builder now materializes the observed dataset using the mappings in
[physical-schema.md](physical-schema.md), without changing the semantic vocabulary
or source files. See the local [build report](../data/reports/build-validation.md)
and [build JSON](../data/reports/build-validation.json) for artifact hashes, table
schemas/counts, reconciliation checks and unresolved exceptions. Run independent
read-only validation with `uv run --project backend python -m backend.ingestion validate`.

A successful build validates immutable sources against the completed profiling
manifest and requires 500,000 unique deal IDs. Raw field strings and original
filename/logical-record references are retained alongside typed data. Every
source field is reconciled, every typed mapping is checked, and exact identifier
joins are checked individually and together for coverage and preserved deal grain.
No records are silently discarded or deduplicated. Business disagreements remain
explicit exceptions rather than overwritten source fields.

USD amounts remain unconverted because FX precision/rounding and timezone rules
are unresolved. The observed same-date positive rate and its source reference are
retained separately from the NULL applied-rate field. Metre/square-metre labels
remain source values outside the semantic unit allowlist. Blank payment/delivery
fields remain NULL, and delivery completion does not establish payment completion.
These limitations do not prevent a lossless source-backed snapshot; they do block
unsupported converted/normalized analytical claims. No broker-INN participant
mapping, fuzzy entity resolution, semantic compiler, or runtime ingestion route
is added. Earlier no-import descriptions above refer to their original milestones.
