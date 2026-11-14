"""collaboration: invitations, plain-text comments with revisions, consented share links (ABB-25)

Revision ID: a7c2e9d4b158
Revises: a19f3b7c2d64 (ABB-19 Uncertainty Hunter)
Create Date: 2026-11-14 23:30:00.000000

Audit stays in the existing ``case_history`` table (invitation and share-link changes are recorded
there without bumping the case version). The activity feed is computed on read from the existing
audit tables and these ones; nothing is copied.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a7c2e9d4b158'
down_revision: Union[str, None] = 'a19f3b7c2d64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TARGET_KINDS = ("('CASE','FIELD','OBSERVATION','ANOMALY','HYPOTHESIS','CLAIM','CONCLUSION','GRAPH_EDGE',"
                "'TIMELINE_EVENT')")


def upgrade() -> None:
    op.create_table('case_invitations',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('role', sa.String(length=24), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'PENDING'"), nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('responded_by_id', sa.Uuid(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_by_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("role IN ('EDITOR','REVIEWER','VIEWER')", name='ck_invitation_role'),
    sa.CheckConstraint("status IN ('PENDING','ACCEPTED','DECLINED','REVOKED','EXPIRED')", name='ck_invitation_status'),
    sa.CheckConstraint('expires_at > created_at', name='ck_invitation_expiry'),
    sa.CheckConstraint('note IS NULL OR char_length(note) <= 500', name='ck_invitation_note'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['responded_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['revoked_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_invitations_case_id'), 'case_invitations', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_invitations_email'), 'case_invitations', ['email'], unique=False)
    op.create_index('uq_invitation_pending_email', 'case_invitations', ['case_id', 'email'], unique=True,
                    postgresql_where=sa.text("status = 'PENDING'"))

    op.create_table('case_comments',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=True),
    sa.Column('target_kind', sa.String(length=24), nullable=False),
    sa.Column('target_id', sa.Uuid(), nullable=True),
    sa.Column('parent_id', sa.Uuid(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint(f'target_kind IN {TARGET_KINDS}', name='ck_comment_target_kind'),
    sa.CheckConstraint("(target_kind = 'CASE') = (target_id IS NULL)", name='ck_comment_target_id'),
    sa.CheckConstraint('char_length(body) BETWEEN 1 AND 4000', name='ck_comment_body_length'),
    sa.CheckConstraint('parent_id IS NULL OR parent_id != id', name='ck_comment_not_own_parent'),
    sa.CheckConstraint('version >= 1', name='ck_comment_version'),
    sa.CheckConstraint('deleted_at IS NOT NULL OR deleted_by_id IS NULL', name='ck_comment_deleted_by'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_id', 'case_id'], ['case_comments.id', 'case_comments.case_id'],
                            name='fk_comment_parent_same_case', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'case_id', name='uq_comment_case')
    )
    op.create_index(op.f('ix_case_comments_case_id'), 'case_comments', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_comments_author_id'), 'case_comments', ['author_id'], unique=False)
    op.create_index(op.f('ix_case_comments_parent_id'), 'case_comments', ['parent_id'], unique=False)
    op.create_index('ix_case_comments_case_target', 'case_comments', ['case_id', 'target_kind', 'target_id'],
                    unique=False)

    op.create_table('case_comment_revisions',
    sa.Column('comment_id', sa.Uuid(), nullable=False),
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('edited_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('revision >= 1', name='ck_comment_revision_number'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['comment_id', 'case_id'], ['case_comments.id', 'case_comments.case_id'],
                            name='fk_comment_revision_same_case', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['edited_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('comment_id', 'revision', name='uq_comment_revision')
    )
    op.create_index(op.f('ix_case_comment_revisions_comment_id'), 'case_comment_revisions', ['comment_id'],
                    unique=False)
    op.create_index(op.f('ix_case_comment_revisions_case_id'), 'case_comment_revisions', ['case_id'], unique=False)

    op.create_table('case_share_links',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('token_sha256', sa.String(length=64), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=True),
    sa.Column('sections', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('consent_statement', sa.Text(), nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_by_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('expires_at > created_at', name='ck_share_link_expiry'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['revoked_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_sha256')
    )
    op.create_index(op.f('ix_case_share_links_case_id'), 'case_share_links', ['case_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_case_share_links_case_id'), table_name='case_share_links')
    op.drop_table('case_share_links')
    op.drop_index(op.f('ix_case_comment_revisions_case_id'), table_name='case_comment_revisions')
    op.drop_index(op.f('ix_case_comment_revisions_comment_id'), table_name='case_comment_revisions')
    op.drop_table('case_comment_revisions')
    op.drop_index('ix_case_comments_case_target', table_name='case_comments')
    op.drop_index(op.f('ix_case_comments_parent_id'), table_name='case_comments')
    op.drop_index(op.f('ix_case_comments_author_id'), table_name='case_comments')
    op.drop_index(op.f('ix_case_comments_case_id'), table_name='case_comments')
    op.drop_table('case_comments')
    op.drop_index('uq_invitation_pending_email', table_name='case_invitations',
                  postgresql_where=sa.text("status = 'PENDING'"))
    op.drop_index(op.f('ix_case_invitations_email'), table_name='case_invitations')
    op.drop_index(op.f('ix_case_invitations_case_id'), table_name='case_invitations')
    op.drop_table('case_invitations')
