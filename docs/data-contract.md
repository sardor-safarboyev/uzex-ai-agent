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
