"""password reset via 6-digit code: attempts column + updated e-mail template

Revision ID: 0006_password_reset_code
Revises: 0005_email_verification
Create Date: 2026-08-06

Mobile-friendly password reset. Adds:
  * password_reset_tokens.attempts  — throttles code guessing (like the
    e-mail-verification codes table)
  * updates the auth.password_reset EMAIL template to a 6-digit-code message
    using {ttl_minutes} (the app now e-mails a short code, not a link)

Downgrade drops the column and restores the previous template wording.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_password_reset_code"
down_revision = "0005_email_verification"
branch_labels = None
depends_on = None


# New body: a 6-digit code the user types into the app. Single-line E'...'
# literals with \n escapes (a Postgres escape string cannot span real newlines).
_NEW_BODY = (
    "E'Bonjour,\\n\\n"
    "Vous avez demandé à réinitialiser votre mot de passe ClosET.\\n\\n"
    "Votre code de réinitialisation est : {code}\\n\\n"
    "Saisissez-le dans l''application pour choisir un nouveau mot de passe. "
    "Il expire dans {ttl_minutes} minutes.\\n\\n"
    "Si vous n''êtes pas à l''origine de cette demande, ignorez ce message.\\n\\n"
    "— L''équipe ClosET'"
)

# Previous body (from 0005) — restored on downgrade.
_OLD_BODY = (
    "E'Bonjour,\\n\\n"
    "Vous avez demandé à réinitialiser votre mot de passe ClosET.\\n"
    "Votre code / jeton est : {code}\\n\\n"
    "Il expire dans {ttl_hours} heures.\\n\\n"
    "Si vous n''êtes pas à l''origine de cette demande, ignorez ce message.\\n\\n"
    "— L''équipe ClosET'"
)


def upgrade() -> None:
    # 1) attempts column (throttle guessing)
    op.add_column(
        "password_reset_tokens",
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    # 2) refresh the e-mail template to the 6-digit-code wording (idempotent)
    op.execute(
        f"""
        UPDATE notification_template
        SET body = {_NEW_BODY}, subject = 'Réinitialisation de votre mot de passe'
        WHERE code = 'auth.password_reset' AND channel = 'email' AND locale = 'fr'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE notification_template
        SET body = {_OLD_BODY}
        WHERE code = 'auth.password_reset' AND channel = 'email' AND locale = 'fr'
        """
    )
    op.drop_column("password_reset_tokens", "attempts")
