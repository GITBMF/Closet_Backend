"""Seed the baseline notification templates (idempotent).

Run once after deploy (and safe to re-run):
    python -m scripts.seed_notification_templates

Creates the French templates the wired callers reference. Without these rows,
send() records FAILED("no template ...") — the messages won't go out. Add locale
variants (e.g. en) later through the admin template endpoint or by extending
TEMPLATES below.
"""

from __future__ import annotations

import asyncio

from app.core.database import AsyncSessionLocal
from app.modules.notifications.constants import NotificationChannel
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import TemplateIn
from app.modules.notifications.service import NotificationService

TEMPLATES: list[TemplateIn] = [
    TemplateIn(
        code="order.paid", channel=NotificationChannel.WHATSAPP, locale="fr",
        subject=None,
        body="Bonjour {customer_name}, votre commande {order_number} est confirmée et payée. Merci d'avoir choisi ClosET !",
    ),
    TemplateIn(
        code="order.cancelled", channel=NotificationChannel.WHATSAPP, locale="fr",
        subject=None,
        body="Bonjour {customer_name}, le paiement de la commande {order_number} n'a pas abouti et la commande a été annulée. Vous pouvez réessayer.",
    ),
    TemplateIn(
        code="order.delivering", channel=NotificationChannel.WHATSAPP, locale="fr",
        subject=None,
        body="Bonjour {customer_name}, votre commande {order_number} est en cours de livraison.",
    ),
    TemplateIn(
        code="order.delivered", channel=NotificationChannel.WHATSAPP, locale="fr",
        subject=None,
        body="Bonjour {customer_name}, votre commande {order_number} a été livrée. Merci et à bientôt sur ClosET !",
    ),
    TemplateIn(
        code="courier.link", channel=NotificationChannel.SMS, locale="fr",
        subject=None,
        body="ClosET livraison : ouvrez ce lien pour voir et mettre à jour la livraison : {url}",
    ),
    TemplateIn(
        code="auth.reset", channel=NotificationChannel.EMAIL, locale="fr",
        subject="Réinitialisation de votre mot de passe ClosET",
        body="Bonjour, votre code de réinitialisation est : {token}. Il expire bientôt. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.",
    ),
    TemplateIn(
        code="sourcing.application_received", channel=NotificationChannel.EMAIL, locale="fr",
        subject="Nouvelle demande de sourceur — ClosET",
        body="Bonjour, {applicant_name} vient de soumettre une demande d'adhésion au cercle des sourceurs sur ClosET. Connectez-vous à l'espace admin pour l'examiner, puis l'approuver ou la refuser.",
    ),
]


async def main() -> None:
    created, skipped = 0, 0
    async with AsyncSessionLocal() as db:
        service = NotificationService(NotificationRepository(db))
        for tpl in TEMPLATES:
            existing = await service.repo.get_template(tpl.code, tpl.channel, tpl.locale)
            if existing is not None:
                skipped += 1
                continue
            await service.create_template(tpl)
            created += 1
    print(f"templates: {created} created, {skipped} already present")


if __name__ == "__main__":
    asyncio.run(main())
