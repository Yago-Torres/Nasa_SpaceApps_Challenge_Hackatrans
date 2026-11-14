"""PDF representation of stored case reports (ABB-26 follow-up, ADR-0007)

Revision ID: e8a4c1d7f905
Revises: d5f3a8b21c64 (ABB-26 report snapshots)
Create Date: 2026-11-14 23:30:00.000000

A version created after this migration stores its PDF bytes once, with their SHA-256; versions created before
have no PDF (the API answers 404 for them rather than rendering a different document later). The write-once
trigger now also protects the two new columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e8a4c1d7f905'
down_revision: Union[str, None] = 'd5f3a8b21c64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = ("snapshot", "snapshot_sha256", "content_markdown", "content_html", "html_sha256", "sources_sha256",
       "checksum_sha256", "case_version", "changes", "version", "generated_at", "case_id", "format",
       "source_manifest_ids", "limitations")


def _function(columns: tuple[str, ...]) -> str:
    comparisons = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in columns)
    return f"""
        CREATE OR REPLACE FUNCTION reports_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF {comparisons} THEN
                RAISE EXCEPTION 'report versions are immutable (report %)', OLD.id USING ERRCODE = '23000';
            END IF;
            RETURN NEW;
        END $$;
    """


def upgrade() -> None:
    op.add_column('reports', sa.Column('content_pdf', sa.LargeBinary(), nullable=True))
    op.add_column('reports', sa.Column('pdf_sha256', sa.String(length=64), nullable=True))
    op.execute(_function(OLD + ("content_pdf", "pdf_sha256")))


def downgrade() -> None:
    op.execute(_function(OLD))
    op.drop_column('reports', 'pdf_sha256')
    op.drop_column('reports', 'content_pdf')
