"""uncertainty hunter answers and question events (ABB-19)

Revision ID: a19f3b7c2d64
Revises: c4d82e1f9a37
Create Date: 2026-11-14 23:30:00.000000

Additive only: two new tables. ``uncertainty_answers`` holds local answers (FARMER_REPORTED
evidence; content immutable, corrections supersede) and ``uncertainty_question_events`` is the
append-only history of each question's resolution (answered, reviewed, rejected, dismissed,
reopened). No existing table changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a19f3b7c2d64'
down_revision: Union[str, None] = 'c4d82e1f9a37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORIGINS = ('FARMER_REPORTED', 'LOCAL_MEASUREMENT', 'FIELD_RECORD', 'ADVISOR_REPORT')
ANSWER_STATUSES = ('ANSWERED', 'REVIEWED', 'REJECTED', 'SUPERSEDED')
ACTIONS = ('ANSWERED', 'REVIEWED', 'REJECTED', 'DISMISSED', 'REOPENED')
QUESTION_STATUSES = ('OPEN', 'ANSWERED', 'REVIEWED', 'DISMISSED')


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table('uncertainty_answers',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('question_id', sa.String(length=40), nullable=False),
    sa.Column('question_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('value_text', sa.Text(), nullable=True),
    sa.Column('value_number', sa.Float(), nullable=True),
    sa.Column('unit', sa.String(length=40), nullable=True),
    sa.Column('observed_from', sa.Date(), nullable=True),
    sa.Column('observed_to', sa.Date(), nullable=True),
    sa.Column('origin', sa.String(length=32), nullable=False),
    sa.Column('method', sa.Text(), nullable=True),
    sa.Column('source_reference', sa.Text(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('answered_by', sa.Uuid(), nullable=False),
    sa.Column('answered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('superseded_by_id', sa.Uuid(), nullable=True),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint(_in('origin', ORIGINS), name='ck_uncertainty_answer_origin'),
    sa.CheckConstraint(_in('status', ANSWER_STATUSES), name='ck_uncertainty_answer_status'),
    sa.CheckConstraint('value_text IS NOT NULL OR value_number IS NOT NULL', name='ck_uncertainty_answer_value'),
    sa.CheckConstraint('value_number IS NULL OR unit IS NOT NULL', name='ck_uncertainty_answer_unit'),
    sa.CheckConstraint('observed_from IS NULL OR observed_to IS NULL OR observed_to >= observed_from',
                       name='ck_uncertainty_answer_period'),
    sa.CheckConstraint('reviewed_by IS NULL OR reviewed_by != answered_by',
                       name='ck_uncertainty_answer_no_self_review'),
    sa.CheckConstraint("status NOT IN ('REVIEWED','REJECTED') OR "
                       "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND review_note IS NOT NULL)",
                       name='ck_uncertainty_answer_review_complete'),
    sa.CheckConstraint("status != 'SUPERSEDED' OR superseded_at IS NOT NULL",
                       name='ck_uncertainty_answer_superseded'),
    sa.CheckConstraint('version >= 1', name='ck_uncertainty_answer_version'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['answered_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    for column in ('case_id', 'question_id', 'answered_by'):
        op.create_index(op.f(f'ix_uncertainty_answers_{column}'), 'uncertainty_answers', [column], unique=False)
    op.create_index('uq_uncertainty_answer_current', 'uncertainty_answers', ['case_id', 'question_id'], unique=True,
                    postgresql_where=sa.text("status IN ('ANSWERED','REVIEWED')"))

    op.create_table('uncertainty_question_events',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('question_id', sa.String(length=40), nullable=False),
    sa.Column('action', sa.String(length=16), nullable=False),
    sa.Column('answer_id', sa.Uuid(), nullable=True),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('from_status', sa.String(length=16), nullable=False),
    sa.Column('to_status', sa.String(length=16), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('question_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint(_in('action', ACTIONS), name='ck_uncertainty_event_action'),
    sa.CheckConstraint(_in('from_status', QUESTION_STATUSES), name='ck_uncertainty_event_from_status'),
    sa.CheckConstraint(_in('to_status', QUESTION_STATUSES), name='ck_uncertainty_event_to_status'),
    sa.CheckConstraint("action = 'ANSWERED' OR note IS NOT NULL", name='ck_uncertainty_event_note'),
    sa.CheckConstraint("action NOT IN ('ANSWERED','REVIEWED','REJECTED') OR answer_id IS NOT NULL",
                       name='ck_uncertainty_event_answer'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['answer_id'], ['uncertainty_answers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    for column in ('case_id', 'question_id', 'answer_id', 'actor_id'):
        op.create_index(op.f(f'ix_uncertainty_question_events_{column}'), 'uncertainty_question_events', [column],
                        unique=False)


def downgrade() -> None:
    for column in ('actor_id', 'answer_id', 'question_id', 'case_id'):
        op.drop_index(op.f(f'ix_uncertainty_question_events_{column}'), table_name='uncertainty_question_events')
    op.drop_table('uncertainty_question_events')
    op.drop_index('uq_uncertainty_answer_current', table_name='uncertainty_answers',
                  postgresql_where=sa.text("status IN ('ANSWERED','REVIEWED')"))
    for column in ('answered_by', 'question_id', 'case_id'):
        op.drop_index(op.f(f'ix_uncertainty_answers_{column}'), table_name='uncertainty_answers')
    op.drop_table('uncertainty_answers')
