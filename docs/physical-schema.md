# Ingestion schema 1.0

This schema implements Milestone 3B.2 for the nine hash-verified CSVs in the
profiling manifest. It records actual inspected headers and literal labels; it
does not establish fuzzy entity mappings or authorize semantic query execution.
The generated build-validation JSON/Markdown reports contain the actual catalog
column types, nullability, table counts, source hashes, exceptions and check values.

## Schemas, grain and provenance

| Schema/table | Grain and key |
| --- | --- |
| main.deals | One row per source deal; primary key deal_id |
| main.contracts | One row per supplied contract; primary key contract_id |
| main.participants | One row per supplied participant; primary key inn |
| main.brokers | One row per supplied broker; primary key broker_code |
| main.usd_rates | One row per supplied rate date; primary key rate_date |
| raw.deals | All five deal CSVs; original 22 columns as VARCHAR |
| raw.contracts | All original 28 columns as VARCHAR |
| raw.participants | All original six columns as VARCHAR |
| raw.brokers | All original four columns as VARCHAR |
| raw.usd_rates | Both original columns as VARCHAR |
| audit.source_files | Nine filename/hash/size/count/encoding/delimiter/header records |
| audit.build_info | Schema, builder-code, manifest, tool versions and unresolved policy metadata |
| audit.validation_checks | Persisted build check names, actual/expected JSON values and pass flags |

Every raw and typed row has `source_file VARCHAR` and `source_record BIGINT`.
The reference is **one-based logical CSV record number after the header**, not a
physical line number: quoted multiline fields remain one record. Raw tables have
a composite primary key on this pair. Source order is preserved with a
single-threaded, nonparallel CSV scan and insertion-order preservation. Validation
rereads each source and compares every decoded field and record ordinal using
EXCEPT ALL plus independent row counts. Source SHA-256 identifies the original
CSV bytes, including quoting, newline convention and encoding; raw columns retain
exact decoded field strings, including leading zeros and formatting spaces.

Typed tables expose the same source references. Raw audit copies retain empty
strings; typed fields map exactly empty strings to SQL NULL, without trimming
keys or treating literal NULL/N/A strings as missing. All identifiers stay VARCHAR.
Malformed CSV, unknown/reordered headers, nonempty parsing failures, duplicate
primary identifiers, missing required join keys, and cardinality failures block
publication rather than dropping, repairing or deduplicating source records.

Dates use exact DD.MM.YYYY syntax, validated calendar dates, and DATE storage.
Times use HH:MM:SS and TIME, with no inferred timezone or combined timestamp.
Decimals use DECIMAL(38,10), a dot separator, and optional ASCII-space thousands
groups of exactly three digits. Excess scale, overflow, comma decimals, exponent
notation and malformed grouping fail. These rules are narrower than exploratory
profiler diagnostics and match the observed data. No floating-point monetary
storage or implicit rounding is used.

## Fact enrichment and validated joins

Contract enrichment uses `deals.contract_id = contracts.contract_id`. Participant
coverage uses seller_inn/buyer_inn against participants.inn. Broker coverage uses
seller_broker_code/buyer_broker_code against brokers.broker_code. Contract seller
coverage is also checked. Every target identifier is unique; all five deal joins
are checked individually and together for complete coverage and unchanged grain.
No join uses product names, seller INN against contracts, company region, or
broker INN against participants. Business disagreements between deal and contract
seller/lot/unit values are counted and preserved rather than overwritten.

Additional main.deals columns:

| Column | Type | Meaning |
| --- | --- | --- |
| currency_source | VARCHAR | Exact contract currency label |
| currency | VARCHAR | Узбекский сум → UZS; Доллар США → USD; other labels → NULL with exception count |
| contract_source_file | VARCHAR | Joined contract provenance |
| contract_source_record | BIGINT | Joined contract provenance |
| measurement_unit | VARCHAR | Exact literal unit translations into the existing semantic allowlist; unresolved labels → NULL |
| physical_volume | DECIMAL(38,20) | Exact deal_quantity_lots × lot_size; no family mixing or conversion |
| delivery_completion | VARCHAR | fully_delivered, partially_delivered, not_delivered, or NULL |
| usd_rate_on_deal_date | DECIMAL(38,10) | Observed same-date rate candidate, not an applied rate |
| rate_source_file | VARCHAR | Matched rate provenance |
| rate_source_record | BIGINT | Matched rate provenance |
| fx_rate_used | DECIMAL(38,10) | NULL; no FX conversion policy is approved |
| transaction_amount_uzs | DECIMAL(38,10) | Original amount copied for native UZS only; NULL for USD/unknown currency |
| conversion_status | VARCHAR | native_uzs, unverified_conversion_semantics, or unknown_currency |

The literal unit translations are килограмм → kg, тонна → tonne, литр → litre,
куб.метр → cubic_metre, штука → piece. Metre and square-metre labels remain intact
in measurement_unit_source with NULL semantic unit. Physical volume still retains
the per-deal source-unit quantity; it must never be totaled across incompatible
units. Ingestion performs no kg/tonne conversion.

Delivery completion depends solely on positive lot quantity and a nonnegative
known delivered quantity within that quantity. Equality means fully_delivered;
zero means not_delivered; a strict intermediate value means partially_delivered.
Missing quantities, invalid bounds or zero deal quantity produce NULL. Official
status remains an independent source string, never a payment-completion flag.

The same-date rate join is validated for uniqueness and positive USD coverage.
However, rate availability does not verify FX rounding/precision or transaction
calendar/timezone rules. **USD conversion is deferred**, its applied rate is NULL,
and its UZS amount is NULL. Native UZS identity copying is not an FX conversion.
A sum of transaction_amount_uzs would omit USD rows: future answers must enforce
coverage and currency policy; they cannot advertise it as a converted grand total.

## Mapping to the semantic contract

| Logical field/metric | Physical source or derivation | Status |
| --- | --- | --- |
| deal_id, deal_date | main.deals.deal_id, deal_date | Direct parsed source |
| seller_inn, buyer_inn | Same-named main.deals columns | Exact source identifiers |
| seller_broker_code, buyer_broker_code | Same-named main.deals columns | Roles remain explicit |
| warehouse_region | main.deals.warehouse_region_source | Source warehouse label per supplied context; aliases unverified |
| product | main.deals.product_name | Exact deal source name, separate from contract product_name |
| product_id | Not materialized | No approved normalized identity mapping |
| contract_type, contract_form | Same-named main.deals columns | Exact source strings |
| status | main.deals.official_status | Official source value |
| delivery_completion | main.deals.delivery_completion | Derived delivery quantities only |
| currency | main.deals.currency plus currency_source | Explicit label translation; unknown labels retained |
| measurement_unit | main.deals.measurement_unit plus measurement_unit_source | Five labels mapped; metre/square metre unresolved |
| deal_count | Count rows at main.deals grain | Never count multiplied join rows |
| deal_value | main.deals.transaction_amount with currency policy | No mixed-currency total or approved USD conversion |
| physical_volume | main.deals.physical_volume with source/semantic unit | Never combine incompatible units |
| delivered_lots | main.deals.delivered_lots | NULL remains unknown |
| average_unit_price / executed_unit_price | Not materialized | Future approved division/currency/unit policy; starting_price is separate |

Company registration regions live in participants/brokers.registration_region_source,
not in the warehouse-region dimension. Grades, classes, brands, sizes, commodity
codes and other contract attributes stay per-contract; repeated product names do
not establish product identity. Contract payment/delivery terms and deposit text
are retained without assigning unverified durations, percentage bases or units.

## Build and validation lifecycle

The builder hashes every source against the completed profile manifest, pins the
manifest bytes, validates structure and loads all rows into a transaction in a
fresh temporary database under the destination directory. It materializes raw,
typed and audit tables, checks source reconciliation, keys, joins, currency/rate
coverage and derivations, commits/checkpoints, then closes the writer. It reopens
the completed snapshot read-only and repeats source reconciliation and integrity
checks, rechecking source/manifest hashes before publication.

Only a fully validated file is fsynced and atomically renamed over the destination.
Failures before publication preserve an existing database; temporary database/WAL
files are cleaned up. An exclusive .build.lock prevents overlapping builders for
the same destination. A stale lock after a killed process requires operator review
and removal only after confirming no builder remains. Close API readers before
rebuilding; an already open reader can retain its old snapshot until it closes.
Report files are individually atomically written and validation evidence is also
stored inside the database. Database and report publication are not one filesystem
transaction: a crash can leave a valid database with an older external report;
rerun offline validation to verify the snapshot.

Reproducibility means identical source-derived records, policies, constraints and
check results for pinned source/manifest/code/tool versions. DuckDB binary file
bytes are not promised identical across builds; the report records the exact
artifact size and SHA-256 for the produced file. There is no timestamp-dependent
transformation or synthetic production data generation. Production CLI builds
require exactly 500,000 deals; small counts are supported only through the Python
builder's explicit expected_deals parameter for fixture testing.

## Exact observed-header mappings

The following tables enumerate every original source field. Both provenance
columns described above are additional to every typed table. Empty source values
remain available verbatim in the corresponding raw table.

### main.deals

| Observed CSV header | Typed column | SQL type |
| --- | --- | --- |
| Номер сделки | deal_id | VARCHAR |
| Дата сделки | deal_date | DATE |
| Время сделки | deal_time | TIME |
| Тип торгов | auction_type | VARCHAR |
| Количество | deal_quantity_lots | DECIMAL(38,10) |
| Сумма сделки | transaction_amount | DECIMAL(38,10) |
| Стартовая цена | starting_price | DECIMAL(38,10) |
| Номер контракта | contract_id | VARCHAR |
| Наименование товара | product_name | VARCHAR |
| Лот | lot_size | DECIMAL(38,10) |
| Единица измерения | measurement_unit_source | VARCHAR |
| Регион | warehouse_region_source | VARCHAR |
| Тип контракта | contract_type | VARCHAR |
| Форма контракта | contract_form | VARCHAR |
| Состояние сделки | official_status | VARCHAR |
| ИНН продавца | seller_inn | VARCHAR |
| ИНН покупателя | buyer_inn | VARCHAR |
| Брокер продавца | seller_broker_code | VARCHAR |
| Брокер покупателя | buyer_broker_code | VARCHAR |
| Дата оплаты | payment_date | DATE |
| Дата поставки | delivery_date | DATE |
| Поставлено | delivered_lots | DECIMAL(38,10) |

### main.contracts

| Observed CSV header | Typed column | SQL type |
| --- | --- | --- |
| Номер контракта | contract_id | VARCHAR |
| Наименование продукта | product_name | VARCHAR |
| Марка товара | product_brand | VARCHAR |
| Размер товара | product_size | VARCHAR |
| Сорт товара | product_grade | VARCHAR |
| Тип товара | product_type | VARCHAR |
| Класс товара | product_class | VARCHAR |
| Код ТН ВЭД | commodity_code | VARCHAR |
| Группа товара | product_group | VARCHAR |
| Категория товара | product_category | VARCHAR |
| Отрасль промышленности | industry | VARCHAR |
| Единица измерения | measurement_unit_source | VARCHAR |
| Лот | lot_size | DECIMAL(38,10) |
| Валюта | currency_source | VARCHAR |
| Базисная цена | base_price | DECIMAL(38,10) |
| Сумма залога | deposit_terms_source | VARCHAR |
| Базис поставки | delivery_basis | VARCHAR |
| Регион | warehouse_region_source | VARCHAR |
| Адрес склада | warehouse_address | VARCHAR |
| Тип торгов | auction_type | VARCHAR |
| Тип контракта | contract_type | VARCHAR |
| Форма контракта | contract_form | VARCHAR |
| Срок оплаты | payment_term_value | DECIMAL(38,10) |
| Срок поставки | delivery_term_value | DECIMAL(38,10) |
| Упаковка | packaging | VARCHAR |
| ИНН продавца | seller_inn | VARCHAR |
| Дата регистрации | registration_date | DATE |
| Действует до | valid_until | DATE |

### main.participants

| Observed CSV header | Typed column | SQL type |
| --- | --- | --- |
| ИНН | inn | VARCHAR |
| Наименование | company_name | VARCHAR |
| Регион | registration_region_source | VARCHAR |
| Вид деятельности | activity_source | VARCHAR |
| Роль | role_source | VARCHAR |
| Плательщик НДС | vat_payer_source | VARCHAR |

### main.brokers

| Observed CSV header | Typed column | SQL type |
| --- | --- | --- |
| Код брокера | broker_code | VARCHAR |
| Наименование | company_name | VARCHAR |
| ИНН | inn_source | VARCHAR |
| Регион | registration_region_source | VARCHAR |

### main.usd_rates

| Observed CSV header | Typed column | SQL type |
| --- | --- | --- |
| Дата | rate_date | DATE |
| Курс | usd_uzs_rate | DECIMAL(38,10) |
