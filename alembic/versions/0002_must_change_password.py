"""users.must_change_password

Forces a password change on bootstrap and recovery accounts.

Revision ID: 0002_must_change_password
Revises: 0001_identity
Create Date: 2026-07-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_must_change_password"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")