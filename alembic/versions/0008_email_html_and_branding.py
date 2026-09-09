"""email templates get html_body + a branding singleton (logo, accent colour)

Revision ID: 0008_email_html_and_branding
Revises: 0007_add_avatar_columns
Create Date: 2026-09-08

Adds:
  * notification_template.html_body — optional rich HTML for e-mail templates
    (plain `body` stays the text fallback / the WhatsApp & SMS content).
  * branding — a single-row table (id = 1) holding the brand name, logo URL and
    accent colour used to render e-mails. Admin-editable at runtime, so the logo
    can be changed without a deploy. A default row is inserted.

Downgrade drops the branding table and the html_body column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_email_html_and_branding"
down_revision = "0007_add_avatar_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_template",
        sa.Column("html_body", sa.Text(), nullable=True),
    )
    op.create_table(
        "branding",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("brand_name", sa.String(length=120), nullable=False,
                  server_default="ClosET"),
        sa.Column("logo_url", sa.String(length=1024), nullable=True),
        sa.Column("accent_color", sa.String(length=9), nullable=False,
                  server_default="#8A5A2B"),
        sa.Column("support_email", sa.String(length=255), nullable=True),
        sa.Column("footer_note", sa.String(length=300), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    # seed the singleton row (id is fixed at 1)
    op.execute(
        "INSERT INTO branding (id, brand_name, accent_color, footer_note) "
        "VALUES (1, 'ClosET', '#8A5A2B', 'L''élégance durable') "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("branding")
    op.drop_column("notification_template", "html_body")
