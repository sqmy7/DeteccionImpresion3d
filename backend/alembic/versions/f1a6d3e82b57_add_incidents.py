"""add incidents (what the model saw, what PrintWatch did, what the user decided)

Revision ID: f1a6d3e82b57
Revises: e7b3c2a91f04
Create Date: 2026-10-09 12:00:00

Written by hand. Only adds a table (plain strings with CHECK constraints, no Postgres enum types), so it is
safe to apply while the previous backend version is still running, and the downgrade drops exactly what the
upgrade created.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f1a6d3e82b57'
down_revision = 'e7b3c2a91f04'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('print_job_id', sa.Integer(), nullable=False),
        sa.Column('printer_id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('mode', sa.String(length=8), nullable=True),
        sa.Column('defect_class', sa.String(length=40), nullable=False),
        sa.Column('streak', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('detection_id', sa.Integer(), nullable=True),
        sa.Column('first_defect_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('announced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pause_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=12), server_default=sa.text("'open'"), nullable=False),
        sa.Column('outcome', sa.String(length=12), nullable=True),
        sa.Column('decided_by', sa.String(length=100), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('label', sa.String(length=14), server_default=sa.text("'unlabeled'"), nullable=False),
        sa.Column('labeled_by', sa.String(length=100), nullable=True),
        sa.Column('labeled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('telemetry_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("reason in ('would_pause', 'auto_pause', 'pause', 'detection')", name='ck_incidents_reason'),
        sa.CheckConstraint("status in ('open', 'paused', 'unconfirmed', 'closed')", name='ck_incidents_status'),
        sa.CheckConstraint("outcome is null or outcome in ('resumed', 'cancelled', 'ignored', 'error')", name='ck_incidents_outcome'),
        sa.CheckConstraint("label in ('unlabeled', 'correct', 'false_positive')", name='ck_incidents_label'),
        sa.CheckConstraint("mode is null or mode in ('on', 'warn')", name='ck_incidents_mode'),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['detection_id'], ['detections.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['print_job_id'], ['print_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['printer_id'], ['printers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_incidents_printer_opened', 'incidents', ['printer_id', 'opened_at'], unique=False)
    op.create_index('ix_incidents_print_job_id', 'incidents', ['print_job_id'], unique=False)
    op.create_index(
        'uq_incidents_open_job_class', 'incidents', ['print_job_id', 'defect_class'], unique=True,
        postgresql_where=sa.text("status <> 'closed'"),
    )


def downgrade() -> None:
    op.drop_index('uq_incidents_open_job_class', table_name='incidents', postgresql_where=sa.text("status <> 'closed'"))
    op.drop_index('ix_incidents_print_job_id', table_name='incidents')
    op.drop_index('ix_incidents_printer_opened', table_name='incidents')
    op.drop_table('incidents')
