"""Baseline notification templates + branding, seeded automatically on startup.

`ensure_notification_defaults()` runs in the app lifespan (always on). It is
idempotent and SAFE FOR ADMIN EDITS:

  * branding singleton — created with defaults only if missing.
  * each baseline template — inserted only if that (code, channel, locale) is
    absent. If it already exists, subject/body are LEFT ALONE (admins may have
    edited them); html_body is filled in ONLY when it is currently null, so
    existing text-only templates gain the branded HTML without clobbering edits.

Templates ship in two locales — French ("fr", the default) and English ("en").
send() uses the requested locale and falls back to "fr" when a locale is missing.

The e-mail templates carry rich, branded HTML in `html_body`. The HTML uses only
inline styles (no <style> blocks, no CSS braces) so it renders in every mail
client AND is safe for the service's str.format_map rendering — the only braces
are the intended {placeholders}: brand values ({brand_name}, {logo_url},
{accent_color}, {support_email}, {footer_note}) plus per-message variables.
"""

from __future__ import annotations

import logging

from app.core.database import AsyncSessionLocal
from app.modules.notifications.constants import NotificationChannel
from app.modules.notifications.models import Branding, NotificationTemplate
from app.modules.notifications.repository import NotificationRepository

logger = logging.getLogger("closet.notifications")

BRAND_DEFAULTS = {
    "brand_name": "ClosET",
    "logo_url": "https://pub-72997f41ec70441cbb83ee9659237363.r2.dev/app-logo/closet-logo.png",
    "accent_color": "#BC9746",
    "footer_note": "L'élégance durable",
}

# --- branded HTML e-mail shell (inline styles only; braces are placeholders) --
_HEADER = (
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f4f4f5;">'
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
    'style="background:#f4f4f5;padding:24px 12px;"><tr><td align="center">'
    '<table role="presentation" width="480" cellpadding="0" cellspacing="0" '
    'style="width:100%;max-width:480px;background:#ffffff;border-radius:12px;'
    'overflow:hidden;font-family:Arial,Helvetica,sans-serif;">'
    '<tr><td style="background:{accent_color};padding:18px 28px;">'
    '<img src="{logo_url}" alt="{brand_name}" height="26" '
    'style="height:26px;vertical-align:middle;border:0;">'
    '<span style="color:#ffffff;font-size:18px;font-weight:bold;'
    'vertical-align:middle;margin-left:8px;">{brand_name}</span></td></tr>'
    '<tr><td style="padding:28px;color:#1a1a1a;font-size:15px;line-height:1.6;">'
)
_FOOTER_FR = (
    '</td></tr>'
    '<tr><td style="padding:18px 28px;background:#faf7f3;color:#9a9a9a;'
    'font-size:12px;line-height:1.5;">{brand_name} — {footer_note}<br>'
    "Besoin d'aide ? {support_email}</td></tr>"
    '</table></td></tr></table></body></html>'
)
_FOOTER_EN = (
    '</td></tr>'
    '<tr><td style="padding:18px 28px;background:#faf7f3;color:#9a9a9a;'
    'font-size:12px;line-height:1.5;">{brand_name} — {footer_note}<br>'
    "Need help? {support_email}</td></tr>"
    '</table></td></tr></table></body></html>'
)


def _code_box(label: str, placeholder: str) -> str:
    return (
        '<div style="margin:22px 0;padding:16px;border:1px dashed {accent_color};'
        'border-radius:8px;text-align:center;">'
        '<div style="font-size:12px;color:#9a9a9a;margin-bottom:6px;">'
        + label + '</div>'
        '<div style="font-size:30px;font-weight:bold;letter-spacing:6px;'
        'color:{accent_color};">' + placeholder + '</div></div>'
    )


def _email_fr(inner: str) -> str:
    return _HEADER + inner + _FOOTER_FR


def _email_en(inner: str) -> str:
    return _HEADER + inner + _FOOTER_EN


# ---- French HTML ----
_VERIFY_HTML_FR = _email_fr(
    "Bonjour {full_name},<br><br>"
    "Bienvenue sur {brand_name} ! Utilisez le code ci-dessous pour vérifier "
    "votre adresse e-mail&nbsp;:"
    + _code_box("Code de vérification", "{code}")
    + "Ce code expire dans {ttl_minutes} minutes. Si vous n'êtes pas à l'origine "
    "de cette inscription, ignorez cet e-mail."
)
_RESET_HTML_FR = _email_fr(
    "Bonjour,<br><br>"
    "Vous avez demandé la réinitialisation de votre mot de passe {brand_name}. "
    "Voici votre code&nbsp;:"
    + _code_box("Code de réinitialisation", "{token}")
    + "Ce code expire bientôt. Si vous n'êtes pas à l'origine de cette demande, "
    "ignorez cet e-mail — votre mot de passe reste inchangé."
)
_APPLICATION_HTML_FR = _email_fr(
    "Bonjour,<br><br>"
    "<strong>{applicant_name}</strong> vient de soumettre une demande d'adhésion "
    "au cercle des sourceurs {brand_name}.<br><br>"
    "Connectez-vous à l'espace admin pour l'examiner, puis l'approuver ou la refuser."
)

# ---- English HTML ----
_VERIFY_HTML_EN = _email_en(
    "Hi {full_name},<br><br>"
    "Welcome to {brand_name}! Use the code below to verify your email address:"
    + _code_box("Verification code", "{code}")
    + "This code expires in {ttl_minutes} minutes. If you didn't sign up, "
    "please ignore this email."
)
_RESET_HTML_EN = _email_en(
    "Hi,<br><br>"
    "You asked to reset your {brand_name} password. Here is your code:"
    + _code_box("Reset code", "{token}")
    + "This code expires soon. If you didn't request this, ignore this email — "
    "your password stays unchanged."
)
_APPLICATION_HTML_EN = _email_en(
    "Hi,<br><br>"
    "<strong>{applicant_name}</strong> just submitted a sourcer application on "
    "{brand_name}.<br><br>"
    "Log in to the admin area to review it, then approve or reject."
)

# code, channel, locale, subject, body (plain-text fallback), html_body
TEMPLATES: list[dict] = [
    # ============================ FRENCH (default) ============================
    dict(code="order.paid", channel=NotificationChannel.WHATSAPP, locale="fr",
         subject=None,
         body="Bonjour {customer_name}, votre commande {order_number} est confirmée et payée. Merci d'avoir choisi ClosET !",
         html_body=None),
    dict(code="order.cancelled", channel=NotificationChannel.WHATSAPP, locale="fr",
         subject=None,
         body="Bonjour {customer_name}, le paiement de la commande {order_number} n'a pas abouti et la commande a été annulée. Vous pouvez réessayer.",
         html_body=None),
    dict(code="order.delivering", channel=NotificationChannel.WHATSAPP, locale="fr",
         subject=None,
         body="Bonjour {customer_name}, votre commande {order_number} est en cours de livraison.",
         html_body=None),
    dict(code="order.delivered", channel=NotificationChannel.WHATSAPP, locale="fr",
         subject=None,
         body="Bonjour {customer_name}, votre commande {order_number} a été livrée. Merci et à bientôt sur ClosET !",
         html_body=None),
    dict(code="courier.link", channel=NotificationChannel.SMS, locale="fr",
         subject=None,
         body="ClosET livraison : ouvrez ce lien pour voir et mettre à jour la livraison : {url}",
         html_body=None),
    dict(code="auth.email_verification", channel=NotificationChannel.EMAIL, locale="fr",
         subject="Votre code de vérification {brand_name}",
         body="Bonjour {full_name}, votre code de vérification {brand_name} est : {code}. Il expire dans {ttl_minutes} minutes.",
         html_body=_VERIFY_HTML_FR),
    dict(code="auth.reset", channel=NotificationChannel.EMAIL, locale="fr",
         subject="Réinitialisation de votre mot de passe {brand_name}",
         body="Bonjour, votre code de réinitialisation {brand_name} est : {token}. Il expire bientôt. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.",
         html_body=_RESET_HTML_FR),
    dict(code="sourcing.application_received", channel=NotificationChannel.EMAIL, locale="fr",
         subject="Nouvelle demande de sourceur — {brand_name}",
         body="Bonjour, {applicant_name} vient de soumettre une demande d'adhésion au cercle des sourceurs sur {brand_name}. Connectez-vous à l'espace admin pour l'examiner, puis l'approuver ou la refuser.",
         html_body=_APPLICATION_HTML_FR),

    # ================================ ENGLISH ================================
    dict(code="order.paid", channel=NotificationChannel.WHATSAPP, locale="en",
         subject=None,
         body="Hi {customer_name}, your order {order_number} is confirmed and paid. Thank you for choosing ClosET!",
         html_body=None),
    dict(code="order.cancelled", channel=NotificationChannel.WHATSAPP, locale="en",
         subject=None,
         body="Hi {customer_name}, payment for order {order_number} didn't go through and the order was cancelled. You can try again.",
         html_body=None),
    dict(code="order.delivering", channel=NotificationChannel.WHATSAPP, locale="en",
         subject=None,
         body="Hi {customer_name}, your order {order_number} is out for delivery.",
         html_body=None),
    dict(code="order.delivered", channel=NotificationChannel.WHATSAPP, locale="en",
         subject=None,
         body="Hi {customer_name}, your order {order_number} has been delivered. Thank you — see you soon on ClosET!",
         html_body=None),
    dict(code="courier.link", channel=NotificationChannel.SMS, locale="en",
         subject=None,
         body="ClosET delivery: open this link to view and update the delivery: {url}",
         html_body=None),
    dict(code="auth.email_verification", channel=NotificationChannel.EMAIL, locale="en",
         subject="Your {brand_name} verification code",
         body="Hi {full_name}, your {brand_name} verification code is: {code}. It expires in {ttl_minutes} minutes.",
         html_body=_VERIFY_HTML_EN),
    dict(code="auth.reset", channel=NotificationChannel.EMAIL, locale="en",
         subject="Reset your {brand_name} password",
         body="Hi, your {brand_name} password reset code is: {token}. It expires soon. If you didn't request this, ignore this message.",
         html_body=_RESET_HTML_EN),
    dict(code="sourcing.application_received", channel=NotificationChannel.EMAIL, locale="en",
         subject="New sourcer application — {brand_name}",
         body="Hi, {applicant_name} just submitted a sourcer application on {brand_name}. Log in to the admin area to review it, then approve or reject.",
         html_body=_APPLICATION_HTML_EN),
]


async def ensure_notification_defaults() -> None:
    """Seed branding + baseline templates (fr + en) on startup. Never crashes."""
    try:
        async with AsyncSessionLocal() as db:
            repo = NotificationRepository(db)
            created = filled = 0

            if await repo.get_branding() is None:
                repo.add_branding(Branding(
                    id=1,
                    brand_name=BRAND_DEFAULTS["brand_name"],
                    logo_url=BRAND_DEFAULTS["logo_url"],
                    accent_color=BRAND_DEFAULTS["accent_color"],
                    footer_note=BRAND_DEFAULTS["footer_note"],
                ))

            for tpl in TEMPLATES:
                existing = await repo.get_template(
                    tpl["code"], tpl["channel"], tpl["locale"]
                )
                if existing is None:
                    db.add(NotificationTemplate(
                        code=tpl["code"], channel=tpl["channel"], locale=tpl["locale"],
                        subject=tpl.get("subject"), body=tpl["body"],
                        html_body=tpl.get("html_body"),
                    ))
                    created += 1
                elif tpl.get("html_body") and existing.html_body is None:
                    existing.html_body = tpl["html_body"]
                    filled += 1

            await db.commit()
    except Exception:  # never let seeding break startup
        logger.exception("notification defaults seed failed; skipping")
        return
    logger.info(
        "notification defaults: %d template(s) created, %d html backfilled",
        created, filled,
    )
