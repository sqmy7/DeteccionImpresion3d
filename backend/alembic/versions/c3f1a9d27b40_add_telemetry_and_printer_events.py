"""add telemetry samples, printer event log and per-layer telemetry snapshot

Revision ID: c3f1a9d27b40
Revises: 4705e91b6c06
Create Date: 2026-10-07 22:10:00

Written by hand. Only adds tables and a nullable column, so it is safe to apply while the
previous backend version is still running.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c3f1a9d27b40'
down_revision = '4705e91b6c06'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'telemetry_samples',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('print_job_id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('klipper_eventtime', sa.Double(), nullable=True),
        sa.Column('layer_number', sa.Integer(), nullable=True),
        sa.Column('x', sa.REAL(), nullable=True),
        sa.Column('y', sa.REAL(), nullable=True),
        sa.Column('z', sa.REAL(), nullable=True),
        sa.Column('velocity', sa.REAL(), nullable=True),
        sa.Column('extruder_velocity', sa.REAL(), nullable=True),
        sa.Column('extruder_temp', sa.REAL(), nullable=True),
        sa.Column('extruder_target', sa.REAL(), nullable=True),
        sa.Column('extruder_power', sa.REAL(), nullable=True),
        sa.Column('bed_temp', sa.REAL(), nullable=True),
        sa.Column('bed_target', sa.REAL(), nullable=True),
        sa.Column('bed_power', sa.REAL(), nullable=True),
        sa.Column('fan_speed', sa.REAL(), nullable=True),
        sa.Column('speed_factor', sa.REAL(), nullable=True),
        sa.Column('extrude_factor', sa.REAL(), nullable=True),
        sa.Column('z_offset', sa.REAL(), nullable=True),
        sa.Column('progress', sa.REAL(), nullable=True),
        sa.Column('filament_used', sa.REAL(), nullable=True),
        sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['print_job_id'], ['print_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_telemetry_samples_job_ts', 'telemetry_samples', ['print_job_id', 'ts'])

    op.create_table(
        'printer_events',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('printer_id', sa.Integer(), nullable=False),
        sa.Column('print_job_id', sa.Integer(), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('klipper_eventtime', sa.Double(), nullable=True),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('field', sa.String(length=120), nullable=True),
        sa.Column('value_before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('value_after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('origin', sa.String(length=20), nullable=False),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('prev_hash', sa.String(length=64), nullable=True),
        sa.Column('hash', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['printer_id'], ['printers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['print_job_id'], ['print_jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hash'),
    )
    op.create_index('ix_printer_events_printer_id_id', 'printer_events', ['printer_id', 'id'])
    op.create_index('ix_printer_events_print_job_id', 'printer_events', ['print_job_id'])

    op.add_column('layers', sa.Column('telemetry', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('layers', 'telemetry')
    op.drop_index('ix_printer_events_print_job_id', table_name='printer_events')
    op.drop_index('ix_printer_events_printer_id_id', table_name='printer_events')
    op.drop_table('printer_events')
    op.drop_index('ix_telemetry_samples_job_ts', table_name='telemetry_samples')
    op.drop_table('telemetry_samples')
