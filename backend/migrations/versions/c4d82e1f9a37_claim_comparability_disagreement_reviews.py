"""claim comparability fields and disagreement reviews (ABB-15)

Revision ID: c4d82e1f9a37
Revises: e3a9c71f5b20
Create Date: 2026-11-14 22:00:00.000000

Additive only: four columns on ``evidence_claims`` (nullable text, or NOT NULL with a default)
and a new append-only ``claim_disagreement_reviews`` table. Existing claims become
``effect_direction = 'NOT_STATED'`` and therefore take no part in disagreement detection
until a person records the comparability fields.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c4d82e1f9a37'
down_revision: Union[str, None] = 'e3a9c71f5b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EFFECT_DIRECTIONS = ('INCREASE', 'DECREASE', 'NO_CLEAR_EFFECT', 'MIXED', 'NOT_STATED')
DECISIONS = ('CONFIRMED_CONTRADICTION', 'NOT_COMPARABLE', 'INCONCLUSIVE')


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


CLAIM_CHECKS = {
    'ck_claim_effect_direction': _in('effect_direction', EFFECT_DIRECTIONS),
    'ck_claim_direction_needs_source_text': "effect_direction = 'NOT_STATED' OR evidence_basis != 'METADATA_ONLY'",
    'ck_claim_direction_needs_terms': (
        "effect_direction = 'NOT_STATED' OR (intervention IS NOT NULL AND outcome_variable IS NOT NULL)"
    ),
}


def upgrade() -> None:
    for name in ('intervention', 'comparator', 'outcome_variable'):
        op.add_column('evidence_claims', sa.Column(name, sa.String(length=300), nullable=True))
    op.add_column('evidence_claims', sa.Column('effect_direction', sa.String(length=24),
                                               server_default=sa.text("'NOT_STATED'"), nullable=False))
    for name, condition in CLAIM_CHECKS.items():
        op.create_check_constraint(name, 'evidence_claims', condition)

    op.create_table('claim_disagreement_reviews',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('pair_id', sa.Uuid(), nullable=False),
    sa.Column('claim_a_id', sa.Uuid(), nullable=False),
    sa.Column('claim_b_id', sa.Uuid(), nullable=False),
    sa.Column('claim_a_version', sa.Integer(), nullable=False),
    sa.Column('claim_b_version', sa.Integer(), nullable=False),
    sa.Column('decision', sa.String(length=32), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('reviewer_id', sa.Uuid(), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('claim_a_id < claim_b_id', name='ck_disagreement_pair_order'),
    sa.CheckConstraint('claim_a_version >= 1 AND claim_b_version >= 1', name='ck_disagreement_versions'),
    sa.CheckConstraint(_in('decision', DECISIONS), name='ck_disagreement_decision'),
    sa.CheckConstraint('char_length(note) > 0', name='ck_disagreement_note'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['claim_a_id'], ['evidence_claims.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['claim_b_id'], ['evidence_claims.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    for column in ('case_id', 'pair_id', 'claim_a_id', 'claim_b_id', 'reviewer_id'):
        op.create_index(op.f(f'ix_claim_disagreement_reviews_{column}'), 'claim_disagreement_reviews', [column],
                        unique=False)


def downgrade() -> None:
    for column in ('reviewer_id', 'claim_b_id', 'claim_a_id', 'pair_id', 'case_id'):
        op.drop_index(op.f(f'ix_claim_disagreement_reviews_{column}'), table_name='claim_disagreement_reviews')
    op.drop_table('claim_disagreement_reviews')
    for name in reversed(list(CLAIM_CHECKS)):
        op.drop_constraint(name, 'evidence_claims', type_='check')
    for name in ('effect_direction', 'outcome_variable', 'comparator', 'intervention'):
        op.drop_column('evidence_claims', name)
