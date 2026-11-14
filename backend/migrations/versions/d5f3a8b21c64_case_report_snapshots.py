"""immutable, versioned case report snapshots (ABB-26)

Revision ID: d5f3a8b21c64
Revises: a7c2e9d4b158 (ABB-25 collaboration)
Create Date: 2026-11-14 22:00:00.000000

Adds the stored content of a report version (JSON snapshot, Markdown, HTML), its hashes, the case version it
was generated from, the change list against the previous version and the author. A trigger makes the content
columns write-once: the API never updates them, and the database refuses any later UPDATE of them (rows
still disappear with their case or account through ``ON DELETE CASCADE``).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd5f3a8b21c64'
down_revision: Union[str, None] = 'a7c2e9d4b158'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMMUTABLE = ("snapshot", "snapshot_sha256", "content_markdown", "content_html", "html_sha256", "sources_sha256",
             "checksum_sha256", "case_version", "changes", "version", "generated_at", "case_id", "format",
             "source_manifest_ids", "limitations")


def upgrade() -> None:
    op.add_column('reports', sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('reports', sa.Column('snapshot_sha256', sa.String(length=64), nullable=True))
    op.add_column('reports', sa.Column('content_markdown', sa.Text(), nullable=True))
    op.add_column('reports', sa.Column('content_html', sa.Text(), nullable=True))
    op.add_column('reports', sa.Column('html_sha256', sa.String(length=64), nullable=True))
    op.add_column('reports', sa.Column('sources_sha256', sa.String(length=64), nullable=True))
    op.add_column('reports', sa.Column('case_version', sa.Integer(), nullable=True))
    op.add_column('reports', sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('reports', sa.Column('generated_by_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_reports_generated_by', 'reports', 'users', ['generated_by_id'], ['id'],
                          ondelete='SET NULL')
    op.create_check_constraint('ck_report_status', 'reports', "status IN ('PRELIMINARY','REVIEWED')")
    op.create_check_constraint('ck_report_version', 'reports', 'version >= 1')
    # IS DISTINCT FROM treats NULLs as values; any change to a content column is rejected.
    comparisons = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in IMMUTABLE)
    op.execute(f"""
        CREATE FUNCTION reports_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF {comparisons} THEN
                RAISE EXCEPTION 'report versions are immutable (report %)', OLD.id USING ERRCODE = '23000';
            END IF;
            RETURN NEW;
        END $$;
    """)
    op.execute("CREATE TRIGGER trg_reports_immutable BEFORE UPDATE ON reports "
               "FOR EACH ROW EXECUTE FUNCTION reports_immutable()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_reports_immutable ON reports")
    op.execute("DROP FUNCTION IF EXISTS reports_immutable()")
    op.drop_constraint('ck_report_version', 'reports', type_='check')
    op.drop_constraint('ck_report_status', 'reports', type_='check')
    op.drop_constraint('fk_reports_generated_by', 'reports', type_='foreignkey')
    for column in ('generated_by_id', 'changes', 'case_version', 'sources_sha256', 'html_sha256',
                   'content_html', 'content_markdown', 'snapshot_sha256', 'snapshot'):
        op.drop_column('reports', column)
