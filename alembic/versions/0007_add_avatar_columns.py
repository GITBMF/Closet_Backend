"""add users avatar_url and avatar_key

Revision ID: 0007_add_avatar_columns
Revises: 0006_password_reset_code
Create Date: 2026-08-26 05:13:27.263354
"""
from alembic import op
import sqlalchemy as sa


revision = '0007_add_avatar_columns'
down_revision = '0006_password_reset_code'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar_url', sa.String(length=1024), nullable=True))
    op.add_column('users', sa.Column('avatar_key', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar_key')
    op.drop_column('users', 'avatar_url')