"""case-bound observations, anomalies and rival hypotheses (ABB-10)

Revision ID: e3a9c71f5b20
Revises: b7e2d4a91c03
Create Date: 2026-11-14 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e3a9c71f5b20'
down_revision: Union[str, None] = 'b7e2d4a91c03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HYPOTHESIS_STATUSES = "('OPEN','SUPPORTED','CHALLENGED','REJECTED','COMPATIBLE','CONTRADICTED','NOT_EVALUABLE')"


def upgrade() -> None:
    # source manifests: case-bound ingestion identity, revisions and processing details
    op.add_column('source_manifests', sa.Column('field_id', sa.Uuid(), nullable=True))
    op.add_column('source_manifests', sa.Column('created_by_id', sa.Uuid(), nullable=True))
    op.add_column('source_manifests', sa.Column(
        'ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('source_manifests', sa.Column('ingestion_key', sa.String(length=64), nullable=True))
    op.add_column('source_manifests', sa.Column('content_sha256', sa.String(length=64), nullable=True))
    op.add_column('source_manifests', sa.Column('revision', sa.Integer(), server_default=sa.text('1'), nullable=False))
    op.add_column('source_manifests', sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('source_manifests', sa.Column('superseded_by_id', sa.Uuid(), nullable=True))
    op.add_column('source_manifests', sa.Column('event_year', sa.Integer(), nullable=True))
    op.add_column('source_manifests', sa.Column('reference_start', sa.Integer(), nullable=True))
    op.add_column('source_manifests', sa.Column('reference_end', sa.Integer(), nullable=True))
    op.add_column('source_manifests', sa.Column(
        'details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_foreign_key(op.f('source_manifests_field_id_fkey'), 'source_manifests', 'fields',
                          ['field_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('source_manifests_created_by_id_fkey'), 'source_manifests', 'users',
                          ['created_by_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_source_manifests_field_id'), 'source_manifests', ['field_id'], unique=False)
    op.create_index('ix_source_manifests_case_ingestion_key', 'source_manifests', ['case_id', 'ingestion_key'],
                    unique=False)
    op.create_check_constraint('ck_manifest_revision', 'source_manifests', 'revision >= 1')

    # observations: aggregation period and daily coverage
    op.add_column('observations', sa.Column('period_start', sa.Date(), nullable=True))
    op.add_column('observations', sa.Column('period_end', sa.Date(), nullable=True))
    op.add_column('observations', sa.Column(
        'coverage', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_check_constraint('ck_observation_period', 'observations',
                               'period_start IS NULL OR period_end IS NULL OR period_end >= period_start')
    op.create_unique_constraint('uq_observation_case', 'observations', ['id', 'case_id'])

    # anomalies: one descriptive anomaly per observation, same case enforced by a composite FK
    op.create_table('anomalies',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('observation_id', sa.Uuid(), nullable=False),
    sa.Column('value', sa.Float(), nullable=True),
    sa.Column('units', sa.String(length=40), nullable=False),
    sa.Column('method', sa.String(length=300), nullable=False),
    sa.Column('reference_start', sa.Date(), nullable=False),
    sa.Column('reference_end', sa.Date(), nullable=False),
    sa.Column('reference_sample_count', sa.Integer(), nullable=False),
    sa.Column('reference_status', sa.String(length=16), nullable=False),
    sa.Column('reference_value', sa.Float(), nullable=True),
    sa.Column('reference_standard_deviation', sa.Float(), nullable=True),
    sa.Column('reference_minimum', sa.Float(), nullable=True),
    sa.Column('reference_maximum', sa.Float(), nullable=True),
    sa.Column('reference_years_excluded', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('quality_flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('limitations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('reference_end >= reference_start', name='ck_anomaly_reference_dates'),
    sa.CheckConstraint('reference_sample_count >= 0', name='ck_anomaly_sample_count'),
    sa.CheckConstraint("reference_status IN ('complete','reduced','insufficient')",
                       name='ck_anomaly_reference_status'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['observation_id', 'case_id'], ['observations.id', 'observations.case_id'],
                            name='fk_anomaly_observation_same_case', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('observation_id')
    )
    op.create_index(op.f('ix_anomalies_case_id'), 'anomalies', ['case_id'], unique=False)

    # hypotheses: evaluation workflow, templates, authorship and per-hypothesis version
    op.add_column('hypotheses', sa.Column('title', sa.String(length=200), nullable=True))
    op.add_column('hypotheses', sa.Column('origin', sa.String(length=16), server_default=sa.text("'USER'"),
                                          nullable=False))
    op.add_column('hypotheses', sa.Column('template_code', sa.String(length=40), nullable=True))
    op.add_column('hypotheses', sa.Column('verification_questions', postgresql.JSONB(astext_type=sa.Text()),
                                          server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column('hypotheses', sa.Column('evaluation_note', sa.Text(), nullable=True))
    op.add_column('hypotheses', sa.Column('evaluated_by_id', sa.Uuid(), nullable=True))
    op.add_column('hypotheses', sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('hypotheses', sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False))
    op.add_column('hypotheses', sa.Column('created_by_id', sa.Uuid(), nullable=True))
    op.add_column('hypotheses', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                                          nullable=False))
    op.add_column('hypotheses', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                                          nullable=False))
    op.create_foreign_key(op.f('hypotheses_evaluated_by_id_fkey'), 'hypotheses', 'users',
                          ['evaluated_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('hypotheses_created_by_id_fkey'), 'hypotheses', 'users',
                          ['created_by_id'], ['id'], ondelete='SET NULL')
    op.create_unique_constraint('uq_hypothesis_case_template', 'hypotheses', ['case_id', 'template_code'])
    op.create_check_constraint('ck_hypothesis_status', 'hypotheses', f'status IN {HYPOTHESIS_STATUSES}')
    op.create_check_constraint('ck_hypothesis_origin', 'hypotheses', "origin IN ('USER','TEMPLATE')")
    op.create_check_constraint('ck_hypothesis_version', 'hypotheses', 'version >= 1')


def downgrade() -> None:
    op.drop_constraint('ck_hypothesis_version', 'hypotheses', type_='check')
    op.drop_constraint('ck_hypothesis_origin', 'hypotheses', type_='check')
    op.drop_constraint('ck_hypothesis_status', 'hypotheses', type_='check')
    op.drop_constraint('uq_hypothesis_case_template', 'hypotheses', type_='unique')
    op.drop_constraint(op.f('hypotheses_created_by_id_fkey'), 'hypotheses', type_='foreignkey')
    op.drop_constraint(op.f('hypotheses_evaluated_by_id_fkey'), 'hypotheses', type_='foreignkey')
    for column in ('updated_at', 'created_at', 'created_by_id', 'version', 'evaluated_at', 'evaluated_by_id',
                   'evaluation_note', 'verification_questions', 'template_code', 'origin', 'title'):
        op.drop_column('hypotheses', column)

    op.drop_index(op.f('ix_anomalies_case_id'), table_name='anomalies')
    op.drop_table('anomalies')

    op.drop_constraint('uq_observation_case', 'observations', type_='unique')
    op.drop_constraint('ck_observation_period', 'observations', type_='check')
    for column in ('coverage', 'period_end', 'period_start'):
        op.drop_column('observations', column)

    op.drop_constraint('ck_manifest_revision', 'source_manifests', type_='check')
    op.drop_index('ix_source_manifests_case_ingestion_key', table_name='source_manifests')
    op.drop_index(op.f('ix_source_manifests_field_id'), table_name='source_manifests')
    op.drop_constraint(op.f('source_manifests_created_by_id_fkey'), 'source_manifests', type_='foreignkey')
    op.drop_constraint(op.f('source_manifests_field_id_fkey'), 'source_manifests', type_='foreignkey')
    for column in ('details', 'reference_end', 'reference_start', 'event_year', 'superseded_by_id', 'superseded_at',
                   'revision', 'content_sha256', 'ingestion_key', 'ingested_at', 'created_by_id', 'field_id'):
        op.drop_column('source_manifests', column)
