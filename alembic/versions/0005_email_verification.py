"""email verification codes + users.email_verified_at + auth e-mail templates

Revision ID: 0005_email_verification
Revises: 0004_dashboard_views
Create Date: 2026-08-04

Adds e-mail verification at registration:
  * users.email_verified_at        — NULL until the user confirms the code
  * email_verification_codes table — hashed 6-digit codes (like reset tokens)
  * two EMAIL notification templates: auth.email_verification, auth.password_reset

Downgrade removes the column, the table, and the two seeded templates.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_email_verification"
down_revision = "0004_dashboard_views"
branch_labels = None
depends_on = None


# Bodies use {placeholders} filled by notifications.send(context=...). Each is a
# single-line Postgres escape string (E'...') with \n for newlines and '' for a
# literal apostrophe — an E'...' literal cannot span real line breaks.
_EMAIL_VERIFICATION_BODY = (
    "E'Bonjour {full_name},\\n\\n"
    "Votre code de vérification ClosET est : {code}\\n\\n"
    "Il expire dans {ttl_minutes} minutes. Saisissez-le dans l''application "
    "pour activer votre compte.\\n\\n"
    "Si vous n''êtes pas à l''origine de cette demande, ignorez ce message.\\n\\n"
    "— L''équipe ClosET'"
)

_PASSWORD_RESET_BODY = (
    "E'Bonjour,\\n\\n"
    "Vous avez demandé à réinitialiser votre mot de passe ClosET.\\n"
    "Votre code / jeton est : {code}\\n\\n"
    "Il expire dans {ttl_hours} heures.\\n\\n"
    "Si vous n''êtes pas à l''origine de cette demande, ignorez ce message.\\n\\n"
    "— L''équipe ClosET'"
)


def upgrade() -> None:
    # 1) users.email_verified_at
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2) email_verification_codes
    op.create_table(
        "email_verification_codes",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True, nullable=False,
        ),
        sa.Column(
            "user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_email_verification_codes_user_id",
        "email_verification_codes", ["user_id"],
    )

    # 3) seed the two EMAIL templates (fr). ON CONFLICT keeps re-runs idempotent.
    op.execute(
        f"""
        INSERT INTO notification_template (code, channel, locale, subject, body)
        VALUES (
            'auth.email_verification', 'email', 'fr',
            'Vérifiez votre adresse e-mail',
            {_EMAIL_VERIFICATION_BODY}
        )
        ON CONFLICT (code, channel, locale) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO notification_template (code, channel, locale, subject, body)
        VALUES (
            'auth.password_reset', 'email', 'fr',
            'Réinitialisation de votre mot de passe',
            {_PASSWORD_RESET_BODY}
        )
        ON CONFLICT (code, channel, locale) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM notification_template "
        "WHERE code IN ('auth.email_verification', 'auth.password_reset') "
        "AND channel = 'email' AND locale = 'fr'"
    )
    op.drop_index(
        "ix_email_verification_codes_user_id",
        table_name="email_verification_codes",
    )
    op.drop_table("email_verification_codes")
    op.drop_column("users", "email_verified_at")