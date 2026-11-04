"""Invented small fixtures for ingestion failure modes, never real UZEX answers."""

import csv
import json
from pathlib import Path

import duckdb
import pytest

from backend.config import Settings
from backend.database.adapter import DuckDBAdapter
from backend.ingestion.builder import build_database, inspect_existing
from backend.ingestion.mappings import MAPPINGS
from backend.ingestion.sources import BuildError
from backend.profiling.csv_scan import fingerprint, scan_csv
from backend.profiling.spec import SPECS


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def refresh_manifest(raw, manifest):
    files = {}
    total = 0
    for name in SPECS:
        scan = scan_csv(raw / name)
        files[name] = {
            **scan,
            "status": "profiled",
            "row_count": scan["records_parsed"],
            "unchanged_after_profiling": True,
        }
        if name.startswith("deals_"):
            total += scan["records_parsed"]
    manifest.write_text(
        json.dumps(
            {
                "profile_version": "1.0",
                "status": "completed",
                "deal_total": total,
                "files": files,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def sources(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    manifest = tmp_path / "profile.json"
    for name in SPECS:
        table = "deals" if name.startswith("deals_") else name.removesuffix(".csv")
        fields = MAPPINGS[table]
        year = int(name[6:10]) if table == "deals" else 2022
        row = {
            field.source: (
                f"01.01.{year}"
                if field.kind == "date"
                else "10:00:00"
                if field.kind == "time"
                else "2"
                if field.kind == "decimal"
                else "TEST_ONLY"
            )
            for field in fields
        }
        for field in ("ИНН продавца", "ИНН"):
            if field in row:
                row[field] = "001"
        for field in ("Брокер продавца", "Код брокера"):
            if field in row:
                row[field] = "BK001"
        if "Номер контракта" in row:
            row["Номер контракта"] = "0007"
        if "Единица измерения" in row:
            row["Единица измерения"] = "килограмм"
            row["Лот"] = "0.50"
        rows = [row]
        if table == "deals":
            row.update(
                {
                    "Номер сделки": f"000{year}",
                    "Сумма сделки": "1 234.50",
                    "Стартовая цена": "1 000",
                    "ИНН покупателя": "002",
                    "Брокер покупателя": "BK002",
                    "Дата оплаты": "",
                    "Дата поставки": "",
                    "Поставлено": {2022: "1", 2023: "2", 2025: "0"}.get(year, ""),
                    "Состояние сделки": "Оплачен",
                }
            )
            if year == 2023:
                row.update({"Номер контракта": "0008", "Единица измерения": "метр"})
        elif table == "contracts":
            row.update(
                {
                    "Валюта": "Доллар США",
                    "Сумма залога": "10 %",
                    "Сорт товара": "TEST_ONLY_GRADE",
                    "Класс товара": "TEST_ONLY_CLASS",
                }
            )
            rows.append(
                {
                    **row,
                    "Номер контракта": "0008",
                    "Валюта": "Узбекский сум",
                    "Единица измерения": "метр",
                }
            )
        elif table == "participants":
            row["Наименование"] = 'TEST_ONLY "Name", quoted\nmultiline'
            rows.append({**row, "ИНН": "002"})
        elif table == "brokers":
            row["ИНН"] = "009"
            rows.append({**row, "Код брокера": "BK002", "ИНН": "008"})
        elif table == "usd_rates":
            rows = [
                {"Дата": f"01.01.{year}", "Курс": "10 000.25"}
                for year in range(2022, 2027)
            ]
        headers = [field.source for field in fields]
        write_csv(raw / name, headers, [[entry[h] for h in headers] for entry in rows])
    refresh_manifest(raw, manifest)
    return raw, manifest, tmp_path / "processed" / "test.duckdb", tmp_path / "reports"


def build(sources):
    return build_database(*sources, expected_deals=5)


def test_typed_values_provenance_nulls_and_unresolved_rules(sources):
    report = build(sources)
    assert report["status"] == "passed", report.get("failure")
    assert report["published"] is True
    assert report["validation"]["table_counts"] == {
        "deals": 5,
        "contracts": 2,
        "participants": 2,
        "brokers": 2,
        "usd_rates": 5,
    }
    with duckdb.connect(str(sources[2]), read_only=True) as connection:
        row = connection.execute("""
            SELECT deal_id, source_file, source_record, transaction_amount::VARCHAR,
                   deal_quantity_lots::VARCHAR, lot_size::VARCHAR,
                   physical_volume::VARCHAR,
                   currency, transaction_amount_uzs, fx_rate_used,
                   usd_rate_on_deal_date::VARCHAR,
                   payment_date, delivery_date, official_status, delivery_completion
            FROM main.deals WHERE deal_id = '0002022'
        """).fetchone()
        assert row[:7] == (
            "0002022",
            "deals_2022.csv",
            1,
            "1234.5000000000",
            "2.0000000000",
            "0.5000000000",
            "1.00000000000000000000",
        )
        assert row[7:10] == ("USD", None, None)
        assert row[10:] == (
            "10000.2500000000",
            None,
            None,
            "Оплачен",
            "partially_delivered",
        )
        assert connection.execute(
            "SELECT transaction_amount_uzs = transaction_amount "
            "FROM deals WHERE currency = 'UZS'"
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT measurement_unit, measurement_unit_source "
            "FROM deals WHERE deal_id = '0002023'"
        ).fetchone() == (None, "метр")
        assert connection.execute(
            "SELECT delivery_completion FROM deals WHERE deal_id = '0002024'"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT delivery_completion FROM deals WHERE deal_id = '0002025'"
        ).fetchone() == ("not_delivered",)
        assert connection.execute(
            'SELECT "Сумма сделки" FROM raw.deals WHERE "Номер сделки" = \'0002022\''
        ).fetchone() == ("1 234.50",)
        assert connection.execute(
            "SELECT company_name, source_record FROM participants WHERE inn = '001'"
        ).fetchone() == ('TEST_ONLY "Name", quoted\nmultiline', 1)
        assert connection.execute(
            "SELECT product_grade, product_class, "
            "deposit_terms_source FROM contracts WHERE "
            "contract_id = '0007'"
        ).fetchone() == ("TEST_ONLY_GRADE", "TEST_ONLY_CLASS", "10 %")
    validated = inspect_existing(sources[0], sources[1], sources[2], expected_deals=5)
    assert validated["status"] == "passed"
    assert all(check["passed"] for check in validated["checks"])
    assert fingerprint(sources[2])["size_bytes"] == report["database_size_bytes"]


def test_hash_failure_keeps_previous_database(sources):
    assert build(sources)["status"] == "passed"
    before = fingerprint(sources[2])
    with (sources[0] / "deals_2022.csv").open("a") as stream:
        stream.write("\n")
    failure = build(sources)
    assert failure["status"] == "failed"
    assert "hash/size differs" in failure["failure"]
    assert fingerprint(sources[2]) == before
    assert not list(sources[2].parent.glob(".uzex-build-*"))


@pytest.mark.parametrize(
    "column,value",
    [
        ("Дата сделки", "31.02.2022"),
        ("Сумма сделки", "12 34"),
        ("Сумма сделки", "1,25"),
        ("Сумма сделки", "1.12345678901"),
    ],
)
def test_nonempty_parse_failures_block_publish(sources, column, value):
    path = sources[0] / "deals_2022.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    rows[1][rows[0].index(column)] = value
    write_csv(path, rows[0], rows[1:])
    refresh_manifest(sources[0], sources[1])
    report = build(sources)
    assert report["status"] == "failed"
    assert "nonempty parsing failures" in report["failure"]
    assert not sources[2].exists()
    assert not sources[2].with_name(sources[2].name + ".build.lock").exists()


def test_duplicate_deal_ids_are_not_deduplicated(sources):
    path = sources[0] / "deals_2023.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    rows[1][0] = "0002022"
    write_csv(path, rows[0], rows[1:])
    refresh_manifest(sources[0], sources[1])
    report = build(sources)
    assert report["status"] == "failed"
    assert not sources[2].exists()


def test_missing_foreign_key_is_validation_failure_and_old_output_survives(sources):
    assert build(sources)["status"] == "passed"
    before = fingerprint(sources[2])
    path = sources[0] / "deals_2022.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    rows[1][rows[0].index("ИНН покупателя")] = "UNMATCHED"
    write_csv(path, rows[0], rows[1:])
    refresh_manifest(sources[0], sources[1])
    report = build(sources)
    assert report["status"] == "failed"
    assert any(
        c["name"] == "deal_buyer:coverage" and not c["passed"]
        for c in report["validation"]["checks"]
    )
    assert fingerprint(sources[2]) == before


def test_independent_validator_detects_tampered_values(sources):
    assert build(sources)["status"] == "passed"
    with duckdb.connect(str(sources[2])) as connection:
        connection.execute(
            "UPDATE deals SET transaction_amount = "
            "transaction_amount + 1 WHERE deal_id = '0002022'"
        )
    report = inspect_existing(sources[0], sources[1], sources[2], expected_deals=5)
    assert report["status"] == "failed"
    assert any(
        c["name"] == "deals:typed_source_reconciliation" and not c["passed"]
        for c in report["checks"]
    )


def test_expected_count_manifest_and_output_path_guards(sources):
    assert (
        build_database(*sources)["status"] == "failed"
    )  # Production default is 500,000.
    with pytest.raises(BuildError, match="outside raw"):
        build_database(
            sources[0], sources[1], sources[0] / "forbidden.duckdb", sources[3]
        )


def test_concurrent_build_lock_is_preserved(sources):
    sources[2].parent.mkdir()
    lock = sources[2].with_name(sources[2].name + ".build.lock")
    lock.write_text("OTHER_BUILDER")
    report = build(sources)
    assert report["status"] == "failed"
    assert lock.read_text() == "OTHER_BUILDER"
    assert not sources[2].exists()


def test_repeat_build_has_identical_logical_values(sources):
    first = build(sources)
    second = build(sources)
    assert first["status"] == second["status"] == "passed"
    assert first["validation"] == second["validation"]
    assert first["build_info"] == second["build_info"]


REPOSITORY = Path(__file__).resolve().parents[2]
REAL_RAW = REPOSITORY / "data" / "raw"
REAL_MANIFEST = REPOSITORY / "data" / "reports" / "profile.json"
REAL_AVAILABLE = REAL_MANIFEST.is_file() and all(
    (REAL_RAW / name).is_file() for name in SPECS
)


@pytest.mark.skipif(
    not REAL_AVAILABLE, reason="Supplied dataset and profiling manifest are local-only"
)
def test_full_supplied_dataset_build_and_read_only_validation(tmp_path):
    output = tmp_path / "full-dataset.duckdb"
    report = build_database(REAL_RAW, REAL_MANIFEST, output, tmp_path / "reports")
    assert report["status"] == "passed", report.get("failure")
    assert report["validation"]["table_counts"] == {
        "deals": 500000,
        "contracts": 6616,
        "participants": 14392,
        "brokers": 120,
        "usd_rates": 1765,
    }
    assert report["validation"]["exceptions"]["usd_conversion_deferred"] == 6590
    assert report["validation"]["exceptions"]["blank_delivered_lots"] == 46291
    assert all(c["passed"] for c in report["validation"]["checks"])
    before = fingerprint(output)
    validation = inspect_existing(REAL_RAW, REAL_MANIFEST, output)
    assert validation["status"] == "passed"
    assert fingerprint(output) == before
    with DuckDBAdapter(Settings(database_path=output)).connection() as connection:
        assert connection.execute("SELECT count(*) FROM main.deals").fetchone() == (
            500000,
        )


@pytest.mark.parametrize("kind", ["duplicate", "missing"])
def test_rate_coverage_or_uniqueness_failure_blocks_build(sources, kind):
    path = sources[0] / "usd_rates.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    body = rows[1:] + [rows[1]] if kind == "duplicate" else rows[2:]
    write_csv(path, rows[0], body)
    refresh_manifest(sources[0], sources[1])
    report = build(sources)
    assert report["status"] == "failed"
    assert not sources[2].exists()


def test_unknown_currency_is_preserved_and_reported_without_conversion(sources):
    path = sources[0] / "contracts.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    rows[1][rows[0].index("Валюта")] = "UNVERIFIED_TEST_CURRENCY"
    write_csv(path, rows[0], rows[1:])
    refresh_manifest(sources[0], sources[1])
    report = build(sources)
    assert report["status"] == "passed", report.get("failure")
    assert report["validation"]["exceptions"]["unknown_currency"] == 4
    with duckdb.connect(str(sources[2]), read_only=True) as connection:
        assert connection.execute(
            "SELECT DISTINCT currency, currency_source, "
            "transaction_amount_uzs FROM deals WHERE contract_id "
            "= '0007'"
        ).fetchone() == (None, "UNVERIFIED_TEST_CURRENCY", None)


def test_atomic_publication_failure_preserves_previous_output(sources, monkeypatch):
    import os

    assert build(sources)["status"] == "passed"
    before = fingerprint(sources[2])
    original = os.replace

    def reject_publish(source, target):
        if Path(target) == sources[2]:
            raise OSError("TEST_ONLY publication failure")
        return original(source, target)

    monkeypatch.setattr("backend.ingestion.builder.os.replace", reject_publish)
    report = build(sources)
    assert report["status"] == "failed"
    assert report["published"] is False
    assert fingerprint(sources[2]) == before
    assert not list(sources[2].parent.glob(".uzex-build-*"))


def test_manifest_change_during_build_blocks_publish(sources, monkeypatch):
    from backend.ingestion.tables import create_typed_tables

    def change_manifest(connection):
        create_typed_tables(connection)
        with sources[1].open("a") as stream:
            stream.write("\n")

    monkeypatch.setattr(
        "backend.ingestion.builder.create_typed_tables", change_manifest
    )
    report = build(sources)
    assert report["status"] == "failed"
    assert not sources[2].exists()


def test_report_paths_cannot_replace_database_or_manifest(sources):
    with pytest.raises(BuildError, match="overlap"):
        build_database(
            sources[0], sources[1], sources[3] / "build-validation.json", sources[3]
        )
