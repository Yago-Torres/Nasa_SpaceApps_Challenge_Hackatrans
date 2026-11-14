"""evidence graph: human-authored conclusions and manual edges (ABB-16)

Revision ID: f4b81d2c6e93
Revises: c4d82e1f9a37 (ABB-15 claim comparability; chained after it to keep a single head)
Create Date: 2026-11-14 23:00:00.000000

Derived edges (anomaly → observation → source manifest, claim → paper, hypothesis evidence
links) are computed on read and are not stored.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f4b81d2c6e93'
down_revision: Union[str, None] = 'c4d82e1f9a37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REVIEW_STATUSES = "('PENDING','ACCEPTED','CHANGES_REQUESTED','REJECTED')"
RELATIONS = "('SUPPORTS','CONTRADICTS','LIMITS','ADDRESSES')"
STORABLE_NODE = (
    r"^(observation|anomaly|claim|hypothesis|conclusion|field):"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    r"|^farmer:(incident|crop-history)$|^missing:no-local-measurements$"
)
NO_SELF_REVIEW = "reviewed_by IS NULL OR NOT (contributor_ids @> jsonb_build_array(reviewed_by::text))"
PENDING_UNREVIEWED = "review_status != 'PENDING' OR (reviewed_by IS NULL AND reviewed_at IS NULL)"


def upgrade() -> None:
    op.create_table('evidence_conclusions',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('limitations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('review_status', sa.String(length=24), server_default=sa.text("'PENDING'"), nullable=False),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('contributor_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"),
              nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('version >= 1', name='ck_conclusion_version'),
    sa.CheckConstraint(f'review_status IN {REVIEW_STATUSES}', name='ck_conclusion_review_status'),
    sa.CheckConstraint('jsonb_array_length(limitations) >= 1', name='ck_conclusion_limitations'),
    sa.CheckConstraint(PENDING_UNREVIEWED, name='ck_conclusion_pending_unreviewed'),
    sa.CheckConstraint("review_status = 'PENDING' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL "
                       "AND review_note IS NOT NULL)", name='ck_conclusion_decision_complete'),
    sa.CheckConstraint(NO_SELF_REVIEW, name='ck_conclusion_no_self_review'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'case_id', name='uq_conclusion_case')
    )
    op.create_index(op.f('ix_evidence_conclusions_case_id'), 'evidence_conclusions', ['case_id'], unique=False)

    op.create_table('evidence_graph_edges',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('source_node', sa.String(length=160), nullable=False),
    sa.Column('target_node', sa.String(length=160), nullable=False),
    sa.Column('relation', sa.String(length=24), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('conclusion_id', sa.Uuid(), nullable=True),
    sa.Column('review_status', sa.String(length=24), server_default=sa.text("'PENDING'"), nullable=False),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('contributor_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"),
              nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('version >= 1', name='ck_graph_edge_version'),
    sa.CheckConstraint('source_node != target_node', name='ck_graph_edge_not_self'),
    sa.CheckConstraint(f'relation IN {RELATIONS}', name='ck_graph_edge_relation'),
    sa.CheckConstraint(f'review_status IN {REVIEW_STATUSES}', name='ck_graph_edge_review_status'),
    sa.CheckConstraint(f"source_node ~ '{STORABLE_NODE}'", name='ck_graph_edge_source_node'),
    sa.CheckConstraint(f"target_node ~ '{STORABLE_NODE}'", name='ck_graph_edge_target_node'),
    sa.CheckConstraint("(conclusion_id IS NULL) = (source_node NOT LIKE 'conclusion:%' "
                       "AND target_node NOT LIKE 'conclusion:%')", name='ck_graph_edge_conclusion_flag'),
    sa.CheckConstraint("conclusion_id IS NULL OR source_node = 'conclusion:' || conclusion_id::text "
                       "OR target_node = 'conclusion:' || conclusion_id::text",
                       name='ck_graph_edge_conclusion_endpoint'),
    sa.CheckConstraint(PENDING_UNREVIEWED, name='ck_graph_edge_pending_unreviewed'),
    sa.CheckConstraint("review_status = 'PENDING' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
                       name='ck_graph_edge_decision_complete'),
    sa.CheckConstraint(NO_SELF_REVIEW, name='ck_graph_edge_no_self_review'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['conclusion_id', 'case_id'], ['evidence_conclusions.id', 'evidence_conclusions.case_id'],
                            name='fk_graph_edge_conclusion_same_case', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'source_node', 'target_node', 'relation', name='uq_graph_edge')
    )
    op.create_index(op.f('ix_evidence_graph_edges_case_id'), 'evidence_graph_edges', ['case_id'], unique=False)
    op.create_index(op.f('ix_evidence_graph_edges_conclusion_id'), 'evidence_graph_edges', ['conclusion_id'],
                    unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_evidence_graph_edges_conclusion_id'), table_name='evidence_graph_edges')
    op.drop_index(op.f('ix_evidence_graph_edges_case_id'), table_name='evidence_graph_edges')
    op.drop_table('evidence_graph_edges')
    op.drop_index(op.f('ix_evidence_conclusions_case_id'), table_name='evidence_conclusions')
    op.drop_table('evidence_conclusions')
