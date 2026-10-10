"""add camera calibrations and per-job bed geometry

Revision ID: d4e8b2c61f05
Revises: c3f1a9d27b40
Create Date: 2026-10-08 00:30:00

Written by hand. Only adds a table and a nullable column, so it is safe to apply while the
previous backend version is still running.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd4e8b2c61f05'
down_revision = 'c3f1a9d27b40'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'camera_calibrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('image_points', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('bed_points', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('image_width', sa.Integer(), nullable=False),
        sa.Column('image_height', sa.Integer(), nullable=False),
        sa.Column('bed_moves_in_image', sa.Boolean(), nullable=False),
        sa.Column('reference_y', sa.REAL(), nullable=True),
        sa.Column('focal_px', sa.REAL(), nullable=True),
        sa.Column('camera_position', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_camera_calibrations_camera_created', 'camera_calibrations', ['camera_id', 'created_at'])

    op.add_column('print_jobs', sa.Column('geometry', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('print_jobs', 'geometry')
    op.drop_index('ix_camera_calibrations_camera_created', table_name='camera_calibrations')
    op.drop_table('camera_calibrations')
