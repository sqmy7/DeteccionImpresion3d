"""add integration_type to printers

Revision ID: 4705e91b6c06
Revises: 5180cfee0eab
Create Date: 2026-09-22 14:46:39.370617

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '4705e91b6c06'
down_revision = '5180cfee0eab'
branch_labels = None
depends_on = None

integration_type = postgresql.ENUM('octoprint', 'moonraker', name='integration_type')


def upgrade() -> None:
    integration_type.create(op.get_bind(), checkfirst=True)
    # server_default: printers predating this column were all OctoPrint-style connections.
    op.add_column(
        'printers',
        sa.Column('integration_type', integration_type, nullable=False, server_default='octoprint'),
    )


def downgrade() -> None:
    op.drop_column('printers', 'integration_type')
    integration_type.drop(op.get_bind(), checkfirst=True)
