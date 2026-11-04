"""Small invented fixtures only; never substitute for the supplied source dataset."""

import csv
import json

import duckdb
import pytest

from backend.profiling.__main__ import main
from backend.profiling.csv_scan import scan_csv
from backend.profiling.relationships import rate_coverage
from backend.profiling.runner import profile_dataset, profile_source, write_reports
from backend.profiling.spec import SPECS, SourceSpec
from backend.profiling.statistics import join_profile, number


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    try:
        yield connection
    finally:
        connection.close()


def write_csv(path, headers, rows, *, encoding="utf-8", delimiter=","):
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream, delimiter=delimiter)
        writer.writerow(headers)
        writer.writerows(rows)


def test_csv_quotes_bom_delimiter_and_multiline(tmp_path):
    path = tmp_path / "fixture.csv"
    write_csv(
        path,
        ["id", "name"],
        [["001", 'A "quoted", name\nnext line']],
        encoding="utf-8-sig",
        delimiter=";",
    )
    before = path.read_bytes()
    scan = scan_csv(path)
    assert scan["encoding"] == "utf-8-sig"
    assert scan["delimiter"] == ";"
    assert scan["records_parsed"] == 1
    assert scan["physical_lines"] == 3
    assert scan["csv_valid"] is True
    assert path.read_bytes() == before


def test_varchar_nulls_leading_zeros_and_parse_failures(connection, tmp_path):
    path = tmp_path / "fixture.csv"
    spec = SourceSpec(
        identifier="id",
        identifiers=("id",),
        dates=("date",),
        decimals=("amount",),
        categories=("status",),
        names=("name",),
    )
    write_csv(
        path,
        ["id", "date", "amount", "status", "name"],
        [
            ["001", "01.01.2022", "1 234.50", "open", 'ООО "Test", завод'],
            ["002", "31.02.2022", "12 34", "", "Тест"],
            ["003", "", "", "NULL", "Test"],
        ],
    )
    result = profile_source(connection, path, "fixture", spec)
    assert result["row_count"] == 3
    assert result["columns"]["id"]["leading_zero_digit_strings"] == 3
    assert result["columns"]["date"]["parsing"]["failures"] == 1
    assert result["columns"]["amount"]["parsing"]["failures"] == 1
    assert result["columns"]["amount"]["parsing"]["minimum"] == "1234.5000000000"
    assert result["columns"]["status"]["empty"] == 1
    assert result["columns"]["status"]["null_marker_candidates"] == 1
    assert result["columns"]["name"]["scripts"]["mixed_script_rows"] == 1
    assert connection.execute(
        "SELECT id, status FROM fixture ORDER BY id"
    ).fetchall() == [
        ("001", "open"),
        ("002", ""),
        ("003", "NULL"),
    ]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1 234.50", "1234.5000000000"),
        ("1\u00a0234.50", "1234.5000000000"),
        ("1\u202f234,50", "1234.5000000000"),
        ("-0.25", "-0.2500000000"),
        ("12 34", None),
        ("1.23456789012", None),
        ("NaN", None),
        ("1e4", None),
    ],
)
def test_decimal_diagnostics_are_explicit(connection, raw, expected):
    value = connection.execute(
        f"SELECT ({number('?')})::VARCHAR", [raw, raw]
    ).fetchone()[0]
    assert value == expected


def test_malformed_records_are_reported_not_loaded(connection, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("id,value\n001,a\n002,b,extra\n", encoding="utf-8")
    result = profile_source(connection, path, "bad", SourceSpec(identifier="id"))
    assert result["status"] == "failed"
    assert result["width_error_records"] == 1
    assert result["error_examples"][0]["line_start"] == 3
    assert connection.execute(
        "SELECT count(*) FROM information_schema.tables"
    ).fetchone() == (0,)


def test_missing_and_bad_encoding_sources_produce_failure_reports(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "brokers.csv").write_bytes(b"id,name\n1,\xff\xfe\n")
    report = profile_dataset(raw)
    assert report["status"] == "failed"
    assert len(report["files"]) == 9
    assert report["files"]["brokers.csv"]["error_type"] == "UnicodeDecodeError"
    assert report["usd_rate_coverage"]["status"] == "unavailable"
    destination = tmp_path / "reports"
    write_reports(report, destination)
    assert json.loads((destination / "profile.json").read_text())["status"] == "failed"
    assert "failure" in (destination / "profile.md").read_text()


def test_duplicate_targets_measure_join_inflation_without_deduplication(connection):
    connection.execute("CREATE TABLE source (id VARCHAR)")
    connection.executemany(
        "INSERT INTO source VALUES (?)", [["001"], ["002"], ["003"], [""]]
    )
    connection.execute("CREATE TABLE target (id VARCHAR)")
    connection.executemany(
        "INSERT INTO target VALUES (?)", [["001"], ["001"], ["002"], ["2"]]
    )
    result = join_profile(connection, "source", "id", "target", "id")
    assert result["source_rows"] == 4
    assert result["blank_source_keys"] == 1
    assert result["unmatched_source_rows"] == 1
    assert result["source_rows_with_multiple_matches"] == 1
    assert result["left_join_rows"] == 5
    assert result["inner_join_rows"] == 3
    assert result["excess_left_join_rows"] == 1
    assert result["target_key_duplicates"]["duplicate_keys"] == 1


def test_usd_rates_missing_duplicate_invalid_and_ambiguous_keys(connection):
    connection.execute(
        'CREATE TABLE deals ("Номер контракта" VARCHAR, "Дата сделки" VARCHAR)'
    )
    connection.execute(
        'CREATE TABLE contracts ("Номер контракта" VARCHAR, "Валюта" VARCHAR)'
    )
    connection.execute('CREATE TABLE rates ("Дата" VARCHAR, "Курс" VARCHAR)')
    connection.executemany(
        "INSERT INTO contracts VALUES (?, ?)",
        [
            ["001", "Доллар США"],
            ["002", "Доллар США"],
            ["003", "Доллар США"],
        ],
    )
    connection.executemany(
        "INSERT INTO deals VALUES (?, ?)",
        [
            ["001", "01.01.2022"],
            ["001", "02.01.2022"],
            ["001", "03.01.2022"],
            ["001", "04.01.2022"],
            ["001", "bad-date"],
            ["missing", "01.01.2022"],
        ],
    )
    connection.executemany(
        "INSERT INTO rates VALUES (?, ?)",
        [
            ["01.01.2022", "10000.25"],
            ["03.01.2022", "10000"],
            ["03.01.2022", "10001"],
            ["04.01.2022", "bad-rate"],
        ],
    )
    tables = {"deals": "deals", "contracts.csv": "contracts", "usd_rates.csv": "rates"}
    result = rate_coverage(connection, tables)
    assert result["usd_deals"] == 5
    assert result["usd_rate_ready"] == 1
    assert result["usd_missing_rate"] == 1
    assert result["usd_duplicate_rate"] == 1
    assert result["usd_invalid_rate"] == 1
    assert result["usd_invalid_dates"] == 1
    assert result["missing_contract"] == 1
    connection.execute("INSERT INTO contracts VALUES ('001', 'Узбекский сум')")
    result = rate_coverage(connection, tables)
    assert result["ambiguous_contract_rows"] == 5
    assert result["usd_deals"] == 0
    assert result["deal_rows"] == 6


@pytest.fixture
def complete_sources(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, spec in SPECS.items():
        headers = sorted(
            set(
                spec.identifiers
                + spec.dates
                + spec.decimals
                + spec.categories
                + spec.names
                + spec.times
                + (spec.identifier,)
            )
        )
        row = dict.fromkeys(headers, "TEST_ONLY")
        year = int(name[6:10]) if name.startswith("deals_") else 2022
        for field in spec.dates:
            row[field] = f"01.01.{year}"
        for field in spec.decimals:
            row[field] = "1"
        for field in spec.times:
            row[field] = "10:00:00"
        for field in ("ИНН продавца", "ИНН покупателя", "ИНН"):
            if field in row:
                row[field] = "001"
        if "Номер контракта" in row:
            row["Номер контракта"] = "0007"
        if "Номер сделки" in row:
            row["Номер сделки"] = f"000{year}"
        for field in ("Код брокера", "Брокер продавца", "Брокер покупателя"):
            if field in row:
                row[field] = "BK001"
        if "Валюта" in row:
            row["Валюта"] = "Доллар США"
        rows = [row]
        if name == "usd_rates.csv":
            rows = [
                {"Дата": f"01.01.{year}", "Курс": "10000"} for year in range(2022, 2027)
            ]
        write_csv(raw / name, headers, [[r[h] for h in headers] for r in rows])
    return raw


def test_full_profile_is_reproducible_and_keeps_sources_unchanged(
    complete_sources, tmp_path
):
    first = profile_dataset(complete_sources)
    second = profile_dataset(complete_sources)
    assert first == second
    assert first["status"] == "completed"
    assert first["deal_total"] == 5
    assert first["usd_rate_coverage"]["usd_rate_ready"] == 5
    assert first["combined_join_risk"]["excess_rows"] == 0
    assert all(f["unchanged_after_profiling"] for f in first["files"].values())
    assert (
        main(
            [
                "--raw-dir",
                str(complete_sources),
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
        == 0
    )


def test_missing_sources_exit_nonzero_and_write_reports(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    destination = tmp_path / "reports"
    assert main(["--raw-dir", str(raw), "--report-dir", str(destination)]) == 1
    assert (destination / "profile.json").exists()


def test_reports_cannot_overwrite_raw_directory(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    with pytest.raises(SystemExit) as error:
        main(["--raw-dir", str(raw), "--report-dir", str(raw / "reports")])
    assert error.value.code == 2


def test_unterminated_quotes_are_reported(connection, tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text('id,value\n001,"unterminated\n', encoding="utf-8")
    result = profile_source(connection, path, "invalid", SourceSpec(identifier="id"))
    assert result["status"] == "failed"
    assert result["syntax_error_groups"] == 1
    assert "row_count" not in result


def test_combined_multiplicity_and_unsafe_candidates(complete_sources):
    path = complete_sources / "contracts.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    with path.open("a", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerow(rows[1])
    result = profile_dataset(complete_sources)
    assert result["joins"]["deal_contract"]["excess_left_join_rows"] == 5
    assert result["combined_join_risk"]["naive_combined_left_join_rows"] == 10
    assert result["usd_rate_coverage"]["ambiguous_contract_rows"] == 5
    assert result["joins"]["unsafe_seller_to_contract_seller"]["candidate_only"] is True
    assert any(i["check"] == "join_inflation" for i in result["issues"])
