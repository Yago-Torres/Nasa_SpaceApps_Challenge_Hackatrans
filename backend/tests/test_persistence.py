"""ABB-03 integration tests. They run only against an explicit disposable PostgreSQL DB."""
from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from agroblackbox.db.models import CasePermission, Field, Observation, SourceManifest
from agroblackbox.db.repositories import CaseRepository, ConcurrentUpdateError
from agroblackbox.db.seed import add_synthetic_development_case
from agroblackbox.db.session import create_database_engine, session_factory

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")


def alembic_config() -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_URL or "")
    return config


@pytest.fixture(scope="session")
def pg_engine():
    engine = create_database_engine(TEST_URL)
    command.downgrade(alembic_config(), "base")
    command.upgrade(alembic_config(), "head")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(pg_engine):
    tables = [t for t in inspect(pg_engine).get_table_names() if t != "alembic_version"]
    if tables:
        quoted = ", ".join(f'"{table}"' for table in tables)
        with pg_engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {quoted} CASCADE"))
    yield


def create_case(factory):
    with factory.begin() as session:
        repo = CaseRepository(session)
        user = repo.create_user(email="owner@example.test", display_name="Synthetic owner")
        case = repo.create_case(
            owner_id=user.id,
            title="Synthetic persistence fixture",
            incident_start=date(2022, 5, 1),
            crop_history=["wheat"],
        )
        return user.id, case.id


def test_empty_database_upgrade_and_downgrade_are_reproducible(pg_engine):
    expected = {"users", "cases", "fields", "source_manifests", "observations", "hypotheses",
                "papers", "evidence_claims", "rotations", "reviews", "reports", "case_permissions"}
    assert expected <= set(inspect(pg_engine).get_table_names())
    command.downgrade(alembic_config(), "base")
    assert not expected & set(inspect(pg_engine).get_table_names())
    command.upgrade(alembic_config(), "head")
    assert expected <= set(inspect(pg_engine).get_table_names())


def test_case_and_owner_permission_survive_new_session(pg_engine):
    factory = session_factory(pg_engine)
    user_id, case_id = create_case(factory)
    with factory() as restarted_session:
        case = CaseRepository(restarted_session).get(case_id)
        permission = restarted_session.scalar(
            select(CasePermission).where(CasePermission.case_id == case_id)
        )
        assert case and case.title == "Synthetic persistence fixture" and case.visibility == "PRIVATE"
        assert permission and permission.user_id == user_id and permission.role == "OWNER"


def test_optimistic_update_rejects_stale_writer(pg_engine):
    factory = session_factory(pg_engine)
    _, case_id = create_case(factory)
    first, stale = factory(), factory()
    try:
        assert CaseRepository(first).get(case_id).version == 1
        assert CaseRepository(stale).get(case_id).version == 1
        CaseRepository(first).update_title(case_id, title="First writer", expected_version=1)
        first.commit()
        with pytest.raises(ConcurrentUpdateError):
            CaseRepository(stale).update_title(case_id, title="Stale writer", expected_version=1)
        stale.rollback()
    finally:
        first.close()
        stale.close()
    with factory() as check:
        case = CaseRepository(check).get(case_id)
        assert case and case.title == "First writer" and case.version == 2


def test_referential_integrity_and_private_coordinate_constraint(pg_engine):
    factory = session_factory(pg_engine)
    with factory() as session:
        session.add(Field(
            case_id=uuid4(), label="Invalid fixture", privacy_tier="WITHHELD",
            latitude=41.6, longitude=-0.9, region_label="Synthetic region",
            precise_location_consent=False, limitations=["Synthetic"],
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_observation_provenance_survives_restart(pg_engine):
    factory = session_factory(pg_engine)
    _, case_id = create_case(factory)
    with factory.begin() as session:
        manifest = SourceManifest(
            case_id=case_id, provider="NASA POWER", dataset="Synthetic-shaped fixture",
            source_uri="https://power.larc.nasa.gov/", query_parameters={"fixture": True},
            retrieved_at=datetime(2026, 11, 14, tzinfo=UTC), checksum_sha256="a" * 64,
            dataset_version=None, processing_version="test", license="NASA policy",
            spatial_resolution={"value": 0.5, "unit": "degree"},
            temporal_resolution={"value": 1, "unit": "day"},
            limitations=["Synthetic fixture; not a NASA observation"],
        )
        session.add(manifest)
        session.flush()
        session.add(Observation(
            case_id=case_id, source_manifest_id=manifest.id, variable="PRECTOTCORR",
            value=None, units="mm/day", observed_at=datetime(2022, 5, 1, tzinfo=UTC),
            spatial_resolution={"value": 0.5, "unit": "degree"},
            temporal_resolution={"value": 1, "unit": "day"},
            quality_flags=["MISSING_UPSTREAM_VALUE"],
            limitations=["Synthetic fixture; no field measurement"],
        ))
    with factory() as restarted_session:
        observation = restarted_session.scalar(select(Observation))
        assert observation and observation.value is None
        assert observation.quality_flags == ["MISSING_UPSTREAM_VALUE"]
        assert restarted_session.get(SourceManifest, observation.source_manifest_id).provider == "NASA POWER"


def test_opt_in_seed_is_unambiguously_synthetic(pg_engine):
    factory = session_factory(pg_engine)
    with factory.begin() as session:
        case = add_synthetic_development_case(session)
        assert case.title.startswith("SYNTHETIC FIXTURE")
        assert "no NASA observation" in case.incident_notes
