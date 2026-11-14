"""structured evidence claims and review history (ABB-14)

Revision ID: e3c91f5a7d24
Revises: b7e2d4a91c03
Create Date: 2026-11-14 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e3c91f5a7d24'
down_revision: Union[str, None] = 'b7e2d4a91c03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REVIEW_STATUSES = ('PENDING', 'ACCEPTED', 'CHANGES_REQUESTED', 'REJECTED')
STUDY_DESIGNS = (
    'META_ANALYSIS', 'SYSTEMATIC_REVIEW', 'FIELD_EXPERIMENT', 'CONTROLLED_EXPERIMENT',
    'OBSERVATIONAL_STUDY', 'MODELLING_STUDY', 'NARRATIVE_REVIEW', 'OTHER', 'UNKNOWN',
)
EVIDENCE_BASES = ('METADATA_ONLY', 'ABSTRACT', 'FULL_TEXT')
ACCESS_BASES = (
    'NONE', 'PUBLIC_ABSTRACT', 'OPEN_ACCESS_LICENSE', 'PUBLISHER_FREE_TO_READ',
    'INSTITUTIONAL_SUBSCRIPTION', 'AUTHOR_PROVIDED_COPY',
)
ORIGINS = ('MANUAL', 'PILOT_SEED_UNVERIFIED')
EVENT_ACTIONS = ('CREATED', 'UPDATED', 'REVIEWED')

CLAIM_CHECKS = {
    'ck_claim_version': 'version >= 1',
    'ck_claim_review_status': None,
    'ck_claim_study_design': None,
    'ck_claim_evidence_basis': None,
    'ck_claim_access_basis': None,
    'ck_claim_origin': None,
    'ck_claim_pending_unreviewed': "review_status != 'PENDING' OR (reviewed_by IS NULL AND reviewed_at IS NULL)",
    'ck_claim_decision_timestamp': "review_status = 'PENDING' OR reviewed_at IS NOT NULL",
    'ck_claim_accepted_reviewer': "review_status != 'ACCEPTED' OR reviewed_by IS NOT NULL",
    'ck_claim_no_self_review': 'created_by IS NULL OR reviewed_by IS NULL OR created_by != reviewed_by',
    'ck_claim_quote_needs_source_text': "quoted_fragment IS NULL OR evidence_basis != 'METADATA_ONLY'",
    'ck_claim_full_text_access': (
        "evidence_basis != 'FULL_TEXT' OR (access_basis NOT IN ('NONE','PUBLIC_ABSTRACT') "
        "AND content_license IS NOT NULL)"
    ),
}


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.add_column('evidence_claims', sa.Column('created_by', sa.Uuid(), nullable=True))
    op.add_column('evidence_claims', sa.Column('created_at', sa.DateTime(timezone=True),
                                               server_default=sa.text('now()'), nullable=False))
    op.add_column('evidence_claims', sa.Column('updated_at', sa.DateTime(timezone=True),
                                               server_default=sa.text('now()'), nullable=False))
    op.add_column('evidence_claims', sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False))
    op.add_column('evidence_claims', sa.Column('study_design', sa.String(length=32),
                                               server_default=sa.text("'UNKNOWN'"), nullable=False))
    for name in ('context', 'reported_outcome', 'source_locator'):
        op.add_column('evidence_claims', sa.Column(name, postgresql.JSONB(astext_type=sa.Text()),
                                                   server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column('evidence_claims', sa.Column('quoted_fragment', sa.Text(), nullable=True))
    op.add_column('evidence_claims', sa.Column('evidence_basis', sa.String(length=24),
                                               server_default=sa.text("'METADATA_ONLY'"), nullable=False))
    op.add_column('evidence_claims', sa.Column('access_basis', sa.String(length=32),
                                               server_default=sa.text("'NONE'"), nullable=False))
    op.add_column('evidence_claims', sa.Column('content_license', sa.Text(), nullable=True))
    op.add_column('evidence_claims', sa.Column('origin', sa.String(length=32),
                                               server_default=sa.text("'MANUAL'"), nullable=False))
    op.add_column('evidence_claims', sa.Column('origin_ref', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_evidence_claims_created_by'), 'evidence_claims', ['created_by'], unique=False)
    op.create_foreign_key('evidence_claims_created_by_fkey', 'evidence_claims', 'users',
                          ['created_by'], ['id'], ondelete='RESTRICT')
    op.create_unique_constraint('uq_claim_case_origin_ref', 'evidence_claims', ['case_id', 'origin_ref'])
    enum_checks = {
        'ck_claim_review_status': _in('review_status', REVIEW_STATUSES),
        'ck_claim_study_design': _in('study_design', STUDY_DESIGNS),
        'ck_claim_evidence_basis': _in('evidence_basis', EVIDENCE_BASES),
        'ck_claim_access_basis': _in('access_basis', ACCESS_BASES),
        'ck_claim_origin': _in('origin', ORIGINS),
    }
    for name, condition in CLAIM_CHECKS.items():
        op.create_check_constraint(name, 'evidence_claims', condition or enum_checks[name])

    op.create_table('evidence_claim_events',
    sa.Column('claim_id', sa.Uuid(), nullable=False),
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('claim_version', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=24), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('from_status', sa.String(length=32), nullable=True),
    sa.Column('to_status', sa.String(length=32), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('source_consulted', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('paper_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('claim_version >= 1', name='ck_claim_event_version'),
    sa.CheckConstraint(_in('action', EVENT_ACTIONS), name='ck_claim_event_action'),
    sa.CheckConstraint(_in('to_status', REVIEW_STATUSES), name='ck_claim_event_to_status'),
    sa.CheckConstraint(
        "action != 'REVIEWED' OR (note IS NOT NULL AND source_consulted IS NOT NULL "
        "AND from_status IS NOT NULL AND to_status != 'PENDING')",
        name='ck_claim_event_review_complete',
    ),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['claim_id'], ['evidence_claims.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evidence_claim_events_actor_id'), 'evidence_claim_events', ['actor_id'], unique=False)
    op.create_index(op.f('ix_evidence_claim_events_case_id'), 'evidence_claim_events', ['case_id'], unique=False)
    op.create_index(op.f('ix_evidence_claim_events_claim_id'), 'evidence_claim_events', ['claim_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_evidence_claim_events_claim_id'), table_name='evidence_claim_events')
    op.drop_index(op.f('ix_evidence_claim_events_case_id'), table_name='evidence_claim_events')
    op.drop_index(op.f('ix_evidence_claim_events_actor_id'), table_name='evidence_claim_events')
    op.drop_table('evidence_claim_events')
    for name in reversed(list(CLAIM_CHECKS)):
        op.drop_constraint(name, 'evidence_claims', type_='check')
    op.drop_constraint('uq_claim_case_origin_ref', 'evidence_claims', type_='unique')
    op.drop_constraint('evidence_claims_created_by_fkey', 'evidence_claims', type_='foreignkey')
    op.drop_index(op.f('ix_evidence_claims_created_by'), table_name='evidence_claims')
    for name in ('origin_ref', 'origin', 'content_license', 'access_basis', 'evidence_basis', 'quoted_fragment',
                 'source_locator', 'reported_outcome', 'context', 'study_design', 'version', 'updated_at',
                 'created_at', 'created_by'):
        op.drop_column('evidence_claims', name)
