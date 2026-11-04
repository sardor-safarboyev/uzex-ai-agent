"""Invented temporary fixtures only; none of these rows are real UZEX data."""

import hashlib
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import Settings
from backend.database.adapter import DuckDBAdapter
from backend.database.errors import DatabaseAccessError, DatabaseErrorCode
from backend.database.service import DatabaseService
from backend.main import create_app


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "test_only.duckdb"
    connection = duckdb.connect(str(path))
    try:
        connection.execute("CREATE SCHEMA fixture_schema")
        connection.execute("""
            CREATE TABLE fixture_schema.fixture_items (
                fixture_id INTEGER NOT NULL,
                fixture_label VARCHAR DEFAULT 'DO_NOT_EXPOSE_DEFAULT',
                fixture_value DECIMAL(12, 2)
            )
        """)
        connection.execute("""
            INSERT INTO fixture_schema.fixture_items VALUES
            (1, 'TEST_ONLY_ROW_A', 1.25), (2, 'TEST_ONLY_ROW_B', 2.50)
        """)
        connection.execute("""
            CREATE VIEW fixture_schema.fixture_view AS
            SELECT fixture_id FROM fixture_schema.fixture_items
        """)
        connection.execute('CREATE TABLE "odd\'table" ("quoted column" INTEGER)')
    finally:
        connection.close()
    return path


def settings(path=None, **overrides):
    return Settings(database_path=path, _env_file=None, **overrides)


def service(path=None, **overrides):
    config = settings(path, **overrides)
    return DatabaseService(DuckDBAdapter(config), config.database_metadata_max_columns)


def test_existing_database_is_read_only_and_unchanged(database_path):
    before = hashlib.sha256(database_path.read_bytes()).digest()
    with DuckDBAdapter(settings(database_path)).connection() as connection:
        assert connection.execute(
            "SELECT count(*) FROM fixture_schema.fixture_items"
        ).fetchone() == (2,)
    assert hashlib.sha256(database_path.read_bytes()).digest() == before
    assert not database_path.with_suffix(".duckdb.wal").exists()


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE forbidden (id INTEGER)",
        "INSERT INTO fixture_schema.fixture_items VALUES (3, 'TEST_ONLY', 3)",
        "UPDATE fixture_schema.fixture_items SET fixture_value = 0",
        "DELETE FROM fixture_schema.fixture_items",
        "DROP TABLE fixture_schema.fixture_items",
    ],
)
def test_persistent_writes_rejected(database_path, statement):
    before = database_path.read_bytes()
    with pytest.raises(DatabaseAccessError) as raised:
        with DuckDBAdapter(settings(database_path)).connection() as connection:
            connection.execute(statement)
    assert raised.value.code == DatabaseErrorCode.READ_ONLY
    assert database_path.read_bytes() == before


def test_connection_closes_on_success_and_consumer_failure(database_path):
    adapter = DuckDBAdapter(settings(database_path, database_max_connections=1))
    with adapter.connection() as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)
    with pytest.raises(duckdb.ConnectionException):
        connection.execute("SELECT 1")
    with pytest.raises(ValueError, match="consumer failure"):
        with adapter.connection() as failed_connection:
            raise ValueError("consumer failure")
    with pytest.raises(duckdb.ConnectionException):
        failed_connection.execute("SELECT 1")
    with adapter.connection() as replacement:
        assert replacement.execute("SELECT 1").fetchone() == (1,)


def test_connection_limit_is_nonblocking_and_recovers(database_path):
    adapter = DuckDBAdapter(settings(database_path, database_max_connections=1))
    with adapter.connection():
        with pytest.raises(DatabaseAccessError) as raised, adapter.connection():
            pytest.fail("connection limit was not applied")
        assert raised.value.code == DatabaseErrorCode.BUSY
    with adapter.connection() as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("missing", "not_found"),
        ("directory", "not_a_file"),
        ("corrupt", "invalid_database"),
        ("not_configured", "not_configured"),
    ],
)
def test_readiness_failures_never_create_database(tmp_path, kind, reason):
    path = tmp_path / "database.duckdb"
    if kind == "directory":
        path.mkdir()
    elif kind == "corrupt":
        path.write_bytes(b"THIS IS NOT A DATABASE")
    elif kind == "not_configured":
        path = None
    adapter = DuckDBAdapter(settings(path, database_max_connections=1))
    database = DatabaseService(adapter, 100)
    for _ in range(2):
        result = database.readiness()
        assert result.status == "not_ready"
        assert result.reason == reason
    if kind == "missing":
        assert not path.exists()


def test_permission_error_is_sanitized(database_path, monkeypatch):
    original = Path.open

    def denied(path, *args, **kwargs):
        if path == database_path:
            raise PermissionError(f"private path: {path}")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    result = service(database_path).readiness()
    assert result.reason == DatabaseErrorCode.PERMISSION_DENIED
    assert str(database_path) not in result.model_dump_json()


def test_engine_open_failure_is_sanitized_and_releases_slot(database_path, monkeypatch):
    def fail(*args, **kwargs):
        raise duckdb.IOException("private database path and engine details")

    adapter = DuckDBAdapter(settings(database_path, database_max_connections=1))
    with monkeypatch.context() as patch:
        patch.setattr(duckdb, "connect", fail)
        for _ in range(2):
            result = DatabaseService(adapter, 100).readiness()
            assert result.reason == DatabaseErrorCode.UNAVAILABLE
            assert "private" not in result.model_dump_json()
    assert DatabaseService(adapter, 100).readiness().status == "ready"


def test_inspection_is_catalog_only_and_schema_independent(database_path):
    result = service(database_path).inspect()
    assert result.read_only is True
    assert result.engine_version == duckdb.__version__
    tables = {(t.schema_name, t.name): t for t in result.tables}
    assert set(tables) == {
        ("fixture_schema", "fixture_items"),
        ("fixture_schema", "fixture_view"),
        ("main", "odd'table"),
    }
    table = tables["fixture_schema", "fixture_items"]
    assert table.kind == "BASE TABLE"
    assert [
        (c.name, c.data_type, c.ordinal_position, c.nullable) for c in table.columns
    ] == [
        ("fixture_id", "INTEGER", 1, False),
        ("fixture_label", "VARCHAR", 2, True),
        ("fixture_value", "DECIMAL(12,2)", 3, True),
    ]
    assert tables["fixture_schema", "fixture_view"].kind == "VIEW"
    serialized = result.model_dump_json()
    assert "TEST_ONLY_ROW" not in serialized
    assert "DO_NOT_EXPOSE_DEFAULT" not in serialized
    assert "SELECT" not in serialized
    assert str(database_path) not in serialized


def test_empty_database_is_available_without_assumed_tables(tmp_path):
    path = tmp_path / "empty.duckdb"
    duckdb.connect(str(path)).close()
    database = service(path)
    assert database.readiness().status == "ready"
    assert database.inspect().tables == []


def test_oversized_catalog_fails_explicitly(database_path):
    with pytest.raises(DatabaseAccessError) as raised:
        service(database_path, database_metadata_max_columns=1).inspect()
    assert raised.value.code == DatabaseErrorCode.RESOURCE_LIMIT


def test_engine_limits_and_configuration_lock(database_path):
    with DuckDBAdapter(settings(database_path)).connection() as connection:
        for key, expected in [
            ("threads", 2),
            ("max_execution_time", 5000),
            ("enable_external_access", False),
            ("lock_configuration", True),
            ("max_temp_directory_size", "0 bytes"),
        ]:
            assert connection.execute(
                "SELECT current_setting(?)", [key]
            ).fetchone() == (expected,)
        assert connection.execute("SELECT current_setting('memory_limit')").fetchone()[
            0
        ]
        with pytest.raises(duckdb.InvalidInputException):
            connection.execute("SET threads = 8")


def test_long_query_is_interrupted(database_path):
    with pytest.raises(DatabaseAccessError) as raised:
        with DuckDBAdapter(
            settings(database_path, database_query_timeout_ms=10)
        ).connection() as connection:
            connection.execute(
                "SELECT sum(sqrt(i)) FROM range(1000000000000) AS r(i)"
            ).fetchone()
    assert raised.value.code == DatabaseErrorCode.QUERY_TIMEOUT


def test_external_file_export_is_disabled(database_path, tmp_path):
    target = tmp_path / "must_not_exist.csv"
    with pytest.raises(DatabaseAccessError):
        with DuckDBAdapter(settings(database_path)).connection() as connection:
            connection.execute("COPY (SELECT 1) TO ?", [str(target)])
    assert not target.exists()


@pytest.mark.parametrize("value", ["", ":memory:", ":memory:alias", ":default:"])
def test_special_database_paths_rejected(value):
    with pytest.raises(ValidationError, match="must be a file path"):
        settings(value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("database_threads", 0),
        ("database_memory_mb", 0),
        ("database_max_connections", 0),
        ("database_query_timeout_ms", 0),
        ("database_metadata_max_columns", 0),
    ],
)
def test_invalid_resource_settings(name, value):
    with pytest.raises(ValidationError):
        settings(**{name: value})


def test_settings_from_environment(database_path, monkeypatch):
    monkeypatch.setenv("UZEX_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("UZEX_DATABASE_METADATA_ENABLED", "true")
    config = Settings()
    assert config.database_path == database_path
    assert config.database_metadata_enabled is True


def test_http_liveness_and_readiness_without_database(tmp_path):
    path = tmp_path / "missing.duckdb"
    with TestClient(create_app(settings(path))) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "reason": "not_found"}
        assert client.get("/dev/database").status_code == 404
    assert not path.exists()


def test_http_ready_and_opt_in_metadata(database_path):
    with TestClient(
        create_app(settings(database_path, database_metadata_enabled=True))
    ) as client:
        assert client.get("/ready").json() == {"status": "ready", "reason": None}
        response = client.get("/dev/database")
        assert response.status_code == 200
        assert len(response.json()["tables"]) == 3
        assert "TEST_ONLY_ROW" not in response.text
        assert client.post("/dev/database", json={"sql": "SELECT 1"}).status_code == 405


def test_http_missing_metadata_is_sanitized(tmp_path):
    with TestClient(
        create_app(
            settings(tmp_path / "private.duckdb", database_metadata_enabled=True)
        )
    ) as client:
        response = client.get("/dev/database")
        assert response.status_code == 503
        assert response.json() == {"detail": {"reason": "not_found"}}
        assert "private" not in response.text


def test_two_connections_can_share_read_only_configuration(database_path):
    adapter = DuckDBAdapter(settings(database_path, database_max_connections=2))
    with adapter.connection() as first, adapter.connection() as second:
        assert first.execute("SELECT 1").fetchone() == (1,)
        assert second.execute("SELECT 1").fetchone() == (1,)
        assert second.execute(
            "SELECT current_setting('enable_external_access')"
        ).fetchone() == (False,)


def test_actual_unreadable_file_is_not_ready(database_path):
    import os

    database_path.chmod(0)
    try:
        if os.access(database_path, os.R_OK):
            pytest.skip("privileged process can read files without mode permission")
        assert (
            service(database_path).readiness().reason
            == DatabaseErrorCode.PERMISSION_DENIED
        )
    finally:
        database_path.chmod(0o600)


def test_read_only_file_and_directory_can_be_inspected(database_path):
    parent = database_path.parent
    database_path.chmod(0o444)
    parent.chmod(0o555)
    try:
        assert service(database_path).readiness().status == "ready"
        assert len(service(database_path).inspect().tables) == 3
    finally:
        parent.chmod(0o700)
        database_path.chmod(0o600)
