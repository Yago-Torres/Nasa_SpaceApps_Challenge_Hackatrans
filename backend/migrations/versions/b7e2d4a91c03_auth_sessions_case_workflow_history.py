"""auth sessions, case workflow and audit history (ABB-05, ABB-06)

Revision ID: b7e2d4a91c03
Revises: 5dac25ea03d7
Create Date: 2026-11-14 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b7e2d4a91c03'
down_revision: Union[str, None] = '5dac25ea03d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users: credentials and brute-force lockout state
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint('ck_user_failed_logins', 'users', 'failed_login_count >= 0')

    # opaque bearer sessions (token digest only)
    op.create_table('sessions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_sha256', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('expires_at > created_at', name='ck_session_expiry'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_sha256')
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)

    # case workflow status and archive flag
    op.add_column('cases', sa.Column('status', sa.String(length=24), server_default=sa.text("'DRAFT'"), nullable=False))
    op.add_column('cases', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        'ck_case_status', 'cases', "status IN ('DRAFT','INVESTIGATING','REVIEWED','PUBLISHED')"
    )

    # approximate-location rounding step for collaborators
    op.add_column('fields', sa.Column('rounding_deg', sa.Float(), nullable=True))
    op.execute("UPDATE fields SET rounding_deg = 0.1 WHERE privacy_tier = 'APPROXIMATE'")
    op.create_check_constraint('ck_field_rounding', 'fields', 'rounding_deg IS NULL OR rounding_deg IN (0.1, 0.5, 1.0)')
    op.create_check_constraint(
        'ck_field_approximate_rounding', 'fields', "privacy_tier != 'APPROXIMATE' OR rounding_deg IS NOT NULL"
    )

    # append-only case audit history
    op.create_table('case_history',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('version >= 1', name='ck_case_history_version'),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_history_actor_id'), 'case_history', ['actor_id'], unique=False)
    op.create_index(op.f('ix_case_history_case_id'), 'case_history', ['case_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_case_history_case_id'), table_name='case_history')
    op.drop_index(op.f('ix_case_history_actor_id'), table_name='case_history')
    op.drop_table('case_history')
    op.drop_constraint('ck_field_approximate_rounding', 'fields', type_='check')
    op.drop_constraint('ck_field_rounding', 'fields', type_='check')
    op.drop_column('fields', 'rounding_deg')
    op.drop_constraint('ck_case_status', 'cases', type_='check')
    op.drop_column('cases', 'archived_at')
    op.drop_column('cases', 'status')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_constraint('ck_user_failed_logins', 'users', type_='check')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_count')
    op.drop_column('users', 'password_hash')
