"""ABB-30 operations: health/readiness, request ids, privacy of logs, metrics, external-source error
visibility and recovery from a failed migration. Offline; the PostgreSQL tests need TEST_DATABASE_URL.
All data here is SYNTHETIC.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from agroblackbox import observability
from agroblackbox.app import app
from agroblackbox.db.session import create_database_engine
from agroblackbox.observability import JsonFormatter
from agroblackbox.services import power

TEST_URL = os.getenv("TEST_DATABASE_URL")
needs_pg = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")
TOKEN = "synthetic-metrics-token-0123456789"
SECRET_LAT = "41.61234"
CLIMATE = f"/api/climate?latitude={SECRET_LAT}&longitude=-0.87654&event_year=2022&reference_start=2019&reference_end=2021"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    observability.reset_for_tests()
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    monkeypatch.delenv("APP_VERSION", raising=False)
    yield
    observability.reset_for_tests()


async def get(path: str, **kw) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        return await c.get(path, **kw)


def as_json_lines(caplog) -> str:
    formatter = JsonFormatter()
    return "\n".join(formatter.format(r) for r in caplog.records)


@pytest.mark.asyncio
async def test_health_reports_the_release_version(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "v1.0.0-synthetic")
    r = await get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "version": "v1.0.0-synthetic"}


@pytest.mark.asyncio
async def test_ready_is_503_without_a_database_and_says_nothing_about_connections(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    r = await get("/api/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"database": "not_configured"}


@pytest.mark.asyncio
async def test_unreachable_database_is_reported_without_the_dsn(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://synthetic:secret-pass@127.0.0.1:1/nowhere")
    r = await get("/api/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"database": "unreachable_or_not_migrated"}
    assert "secret-pass" not in r.text and "127.0.0.1" not in r.text


@pytest.mark.asyncio
async def test_request_id_is_returned_and_a_safe_incoming_one_is_kept():
    r = await get("/api/health", headers={"X-Request-ID": "synthetic-req-0001"})
    assert r.headers["X-Request-ID"] == "synthetic-req-0001"
    r = await get("/api/health", headers={"X-Request-ID": "bad id\n<script>"})
    assert r.headers["X-Request-ID"] != "bad id\n<script>" and len(r.headers["X-Request-ID"]) == 32


@pytest.mark.asyncio
async def test_metrics_are_disabled_without_token_and_need_the_bearer_token(monkeypatch):
    assert (await get("/api/metrics")).status_code == 404
    monkeypatch.setenv("METRICS_TOKEN", TOKEN)
    assert (await get("/api/metrics")).status_code == 401
    assert (await get("/api/metrics", headers={"Authorization": "Bearer wrong-token-0000000000"})).status_code == 401
    ok = await get("/api/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200 and "cropstory_build_info" in ok.text
    assert "/api/metrics" not in (await get("/openapi.json")).text


@pytest.mark.asyncio
async def test_external_source_failure_is_visible_in_metrics_and_logs_without_coordinates(monkeypatch, caplog, tmp_path):
    async def failing_download(client, params):
        raise power.PowerSourceError("NASA POWER did not answer in time.", reason="timeout")

    monkeypatch.setattr(power, "CACHE", tmp_path / "power")
    monkeypatch.setattr(power, "_download", failing_download)
    monkeypatch.setenv("METRICS_TOKEN", TOKEN)
    caplog.set_level(logging.INFO)
    r = await get(CLIMATE)
    assert r.status_code == 502
    metrics = (await get("/api/metrics", headers={"Authorization": f"Bearer {TOKEN}"})).text
    assert 'cropstory_upstream_calls_total{source="nasa_power",outcome="error:timeout"} 1' in metrics
    assert 'cropstory_upstream_last_error_timestamp_seconds{source="nasa_power",outcome="error:timeout"}' in metrics
    assert 'route="/api/climate",status="5xx"' in metrics
    logs = as_json_lines(caplog)
    assert '"event": "upstream_error"' in logs and '"source": "nasa_power"' in logs
    assert '"route": "/api/climate"' in logs
    # Coordinates travel in the query string: they must never reach logs or metrics.
    assert SECRET_LAT not in logs and SECRET_LAT not in metrics and "latitude" not in logs


@pytest.mark.asyncio
async def test_routes_are_counted_by_template_not_by_identifier(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", TOKEN)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    await get("/api/v1/cases/11111111-1111-4111-8111-111111111111", headers={"Authorization": "Bearer synthetic"})
    metrics = (await get("/api/metrics", headers={"Authorization": f"Bearer {TOKEN}"})).text
    assert 'route="/api/v1/cases/{case_id}"' in metrics
    assert "11111111-1111-4111-8111-111111111111" not in metrics


@pytest.mark.asyncio
async def test_unhandled_error_answers_500_with_request_id_and_logs_only_type_and_location(monkeypatch, caplog):
    async def boom():
        raise RuntimeError("synthetic secret detail farmer@example.test")

    app.add_api_route("/api/_synthetic_boom", boom)
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("METRICS_TOKEN", TOKEN)
    try:
        r = await get("/api/_synthetic_boom")
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/api/_synthetic_boom"]
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error.", "request_id": r.headers["X-Request-ID"]}
    logs = as_json_lines(caplog)
    assert '"error_type": "RuntimeError"' in logs and "farmer@example.test" not in logs and "secret detail" not in logs
    metrics = (await get("/api/metrics", headers={"Authorization": f"Bearer {TOKEN}"})).text
    assert 'cropstory_unhandled_errors_total{type="RuntimeError"} 1' in metrics


def test_json_log_lines_carry_the_request_id():
    token = observability.request_id_var.set("synthetic-req-0002")
    try:
        record = logging.LogRecord("cropstory", logging.INFO, __file__, 1, "hello", None, None)
        record.event = {"event": "request", "route": "/api/health"}
        line = JsonFormatter().format(record)
    finally:
        observability.request_id_var.reset(token)
    assert '"request_id": "synthetic-req-0002"' in line and '"route": "/api/health"' in line


# ── PostgreSQL: readiness against the real schema and a failed migration ─────

def alembic_config(script_location: Path | None = None) -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_URL or "")
    if script_location is not None:
        config.set_main_option("script_location", str(script_location))
    return config


@needs_pg
@pytest.mark.asyncio
async def test_ready_only_when_the_database_is_at_this_builds_migration_head(monkeypatch):
    from agroblackbox.api.deps import _factory_for

    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    _factory_for.cache_clear()
    command.upgrade(alembic_config(), "head")
    r = await get("/api/ready")
    assert r.status_code == 200 and r.json()["checks"] == {"database": "ok", "migrations": "at_head"}
    command.downgrade(alembic_config(), "-1")
    try:
        r = await get("/api/ready")
        assert r.status_code == 503 and r.json()["checks"]["migrations"] == "not_at_head"
    finally:
        command.upgrade(alembic_config(), "head")
        _factory_for.cache_clear()


FAILING_REVISION = '''"""SYNTHETIC failing migration used only by the ABB-30 recovery rehearsal."""
import sqlalchemy as sa
from alembic import op

revision = "ffff0000dead"
down_revision = "{down}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("synthetic_half_applied", sa.Column("id", sa.Integer, primary_key=True))
    op.add_column("cases", sa.Column("synthetic_half_applied_flag", sa.Boolean(), nullable=True))
    op.execute("SELECT 1 / 0")  # fails after two DDL statements


def downgrade() -> None:
    pass
'''


@needs_pg
def test_a_failed_migration_rolls_back_completely_and_the_previous_head_stays_usable(tmp_path):
    """Recovery rehearsal: PostgreSQL DDL is transactional, so a migration that fails half way leaves
    neither its table nor its column behind and alembic_version unchanged; the release can roll back."""
    command.upgrade(alembic_config(), "head")
    engine = create_database_engine(TEST_URL)
    try:
        with engine.connect() as conn:
            head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        scripts = tmp_path / "migrations"
        shutil.copytree(Path(__file__).parents[1] / "migrations", scripts)
        (scripts / "versions" / "ffff0000dead_synthetic_failing.py").write_text(FAILING_REVISION.format(down=head), encoding="utf-8")
        with pytest.raises(Exception):
            command.upgrade(alembic_config(scripts), "head")
        inspector = inspect(engine)
        assert "synthetic_half_applied" not in inspector.get_table_names()
        assert "synthetic_half_applied_flag" not in {c["name"] for c in inspector.get_columns("cases")}
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == head
        command.check(alembic_config())  # the shipped schema still matches the models
    finally:
        engine.dispose()


def test_external_source_functions_are_monitored_once():
    """The wrappers are installed at app start without decorating the services (ABB-27 owns them)."""
    from agroblackbox import upstream_monitoring
    from agroblackbox.services import literature

    before = (power.fetch_power, literature.search_literature, literature.lookup_paper, literature.verify_doi)
    upstream_monitoring.install()  # idempotent
    after = (power.fetch_power, literature.search_literature, literature.lookup_paper, literature.verify_doi)
    assert before == after
    assert all(getattr(fn, "_cropstory_monitored", False) for fn in after)
