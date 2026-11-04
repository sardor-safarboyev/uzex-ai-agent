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
