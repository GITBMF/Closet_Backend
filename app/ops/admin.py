"""Internal operations panel (Starlette-Admin), mounted at /ops.

This is an ENGINEERING tool, not the client deliverable. The customer-facing
administrator back office is the Next.js application specified in the
requirements. Use this to seed data, inspect rows and unstick records while
the real back office is being built.

Disabled unless OPS_ENABLED=true, and it refuses to start in production
unless OPS_ALLOW_IN_PROD is also set — see mount_ops().
"""

from __future__ import annotations

from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette_admin import PasswordField
from starlette_admin import (
    ColorField,
    EmailField,
    StringField,
    TextAreaField,
    URLField,
)
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette_admin import row_action
from starlette_admin.contrib.sqla import Admin, ModelView
from starlette_admin.views import DropDown
from starlette_admin.exceptions import FormValidationError

from app.core.config import settings
from app.core.database import engine
from app.core.security import hash_password
from app.modules.identity.models import (
    AuditLog,
    DeviceToken,
    PasswordResetToken,
    RefreshToken,
    User,
)
from app.ops import actions as A
from app.ops.home import DashboardHome
from app.modules.catalogue.models import House, Piece, Universe
from app.modules.delivery.models import Courier, Delivery, DeliveryEvent
from app.modules.delivery_pricing.models import DeliveryRate
from app.modules.privileges.models import PrivilegeCode
from app.modules.geo.models import (
    Division,
    FixedRateCity,
    Neighbourhood,
    Region,
    Subdivision,
)
from app.modules.notifications.models import Branding, Notification, NotificationTemplate
from app.modules.ops.models import AppSetting
from app.modules.orders.models import Purchase
from app.modules.payments.models import Payment, Refund
from app.modules.returns.models import ReturnTicket
from app.modules.showcasing.models import FeaturedSlot, Sponsor
from app.modules.sourcing.models import Payout, SourcerProfile, Submission
from app.ops.auth import OpsAuthProvider
from app.ops.onboarding import onboarding_routes


class UserView(ModelView):
    identity = "user"
    name = "Utilisateur"
    label = "Utilisateurs"
    icon = "fa fa-users"

    # A write-only "password" input appears on the create/edit forms. It is
    # never read back from the database (password_hash is never exposed); on
    # save it is hashed into password_hash by before_create / before_edit.
    fields = [
        "id", "email", "full_name", "phone", "city", "role",
        PasswordField(
            "password",
            label="Mot de passe",
            help_text="Laisser vide pour ne pas changer (à la modification).",
            exclude_from_list=True,
            exclude_from_detail=True,
        ),
        "avatar_url", "is_active", "must_change_password", "email_verified_at", "totp_enabled_at",
        "failed_login_count", "locked_until", "last_login_at",
        "created_at", "deleted_at",
    ]
    exclude_fields_from_list = ["id", "city", "totp_enabled_at", "deleted_at"]
    exclude_fields_from_create = [
        "failed_login_count", "locked_until", "last_login_at", "deleted_at",
        "totp_enabled_at", "created_at",
        "email_verified_at", "avatar_url",
        # is_active is forced True in before_create; hide it here so an
        # unchecked checkbox can't create an inactive account
        "is_active",
    ]
    exclude_fields_from_edit = [
        "failed_login_count", "locked_until", "last_login_at", "deleted_at",
        "totp_enabled_at", "created_at",
        # role is not editable on the form: changes go through the guarded
        # change-role action, and sourcer must come via the application flow.
        "role",
    ]
    searchable_fields = ["email", "full_name", "phone"]
    sortable_fields = ["email", "full_name", "role", "created_at", "last_login_at"]
    fields_default_sort = [("created_at", True)]

    # ------------------------------------------------------------------ hooks
    async def before_create(self, request, data, obj) -> None:
        """Hash the typed password into password_hash; require one on create.

        An admin created here must be able to log in, so a password is
        mandatory. New admins are flagged must_change_password so the person
        sets their own on first login, and they enrol their own 2FA via
        /api/v1/me/mfa/setup afterwards.
        """
        _role = getattr(data.get("role"), "value", data.get("role"))
        if _role == "sourcer":
            raise FormValidationError(
                {"role": "Un nouveau sourceur doit passer par la phase de "
                         "candidature (demande d'adhésion puis approbation). "
                         "Le rôle sourceur ne peut pas être attribué "
                         "directement."}
            )
        raw = (data.get("password") or "").strip()
        if not raw:
            raise FormValidationError({"password": "Mot de passe requis."})
        self._validate_password(raw)
        obj.password_hash = hash_password(raw)
        # a freshly created account must rotate the password it was handed
        obj.must_change_password = True
        # new accounts are active by default (the create form no longer shows
        # is_active, so it can't be left unchecked into an inactive account)
        obj.is_active = True

    async def before_edit(self, request, data, obj) -> None:
        """Hash a new password only if one was typed; blank = leave unchanged."""
        raw = (data.get("password") or "").strip()
        if raw:
            self._validate_password(raw)
            obj.password_hash = hash_password(raw)
            obj.must_change_password = True

    @staticmethod
    def _validate_password(raw: str) -> None:
        if len(raw) < 8:
            raise FormValidationError(
                {"password": "Au moins 8 caractères."}
            )
        if raw.encode("utf-8").__len__() > 72:
            raise FormValidationError(
                {"password": "Trop long (72 octets maximum)."}
            )
        if not (any(c.isalpha() for c in raw) and any(c.isdigit() for c in raw)):
            raise FormValidationError(
                {"password": "Doit contenir des lettres et des chiffres."}
            )

    # password_hash and totp_secret are still absent from `fields`: the panel
    # never displays or edits a stored credential — only accepts a new one.

class RefreshTokenView(ModelView):
    identity = "refresh-token"
    name = "Session"
    label = "Sessions"
    icon = "fa fa-key"

    fields = [
        "id", "user_id", "user_agent", "ip_address",
        "expires_at", "rotated_at", "revoked_at", "created_at",
    ]
    exclude_fields_from_list = ["id"]
    sortable_fields = ["created_at", "expires_at"]
    fields_default_sort = [("created_at", True)]

    # read-only: revoking must go through the API so the audit trail records it
    def can_create(self, request) -> bool:  # noqa: ANN001
        return False

    def can_edit(self, request) -> bool:  # noqa: ANN001
        return False


class DeviceTokenView(ModelView):
    identity = "device-token"
    name = "Appareil"
    label = "Appareils (push)"
    icon = "fa fa-mobile-screen"

    fields = ["id", "user_id", "platform", "marketing_opt_in", "created_at", "last_seen_at"]
    sortable_fields = ["created_at", "last_seen_at"]


class PasswordResetTokenView(ModelView):
    identity = "password-reset"
    name = "Réinitialisation"
    label = "Réinitialisations"
    icon = "fa fa-unlock"

    fields = ["id", "user_id", "expires_at", "used_at", "created_at"]
    fields_default_sort = [("created_at", True)]

    def can_create(self, request) -> bool:  # noqa: ANN001
        return False

    def can_edit(self, request) -> bool:  # noqa: ANN001
        return False


class AuditLogView(ModelView):
    identity = "audit-log"
    name = "Journal"
    label = "Journal d'audit"
    icon = "fa fa-clipboard-list"

    fields = [
        "id", "created_at", "action", "actor_type", "actor_id",
        "entity_type", "entity_id", "ip_address", "payload",
    ]
    searchable_fields = ["action", "entity_type", "entity_id"]
    sortable_fields = ["created_at", "action"]
    fields_default_sort = [("created_at", True)]

    # append-only: the audit trail is evidence, never editable
    def can_create(self, request) -> bool:  # noqa: ANN001
        return False

    def can_edit(self, request) -> bool:  # noqa: ANN001
        return False

    def can_delete(self, request) -> bool:  # noqa: ANN001
        return False



# ============================================================ business views
#
# Reference/config data is fully editable. Everything with business rules is
# read-only in the grid and changed ONLY through the service-backed row actions
# below — so the state machines and cross-module effects (grant role, refund,
# restock, create piece) built into the services are always honoured. Nobody
# hand-edits a status column and skips the logic.


class _ReadOnly(ModelView):
    """View + search only; state changes go through row actions."""

    def can_create(self, request) -> bool:  # noqa: ANN001
        return False

    def can_edit(self, request) -> bool:  # noqa: ANN001
        return False

    def can_delete(self, request) -> bool:  # noqa: ANN001
        return False


class _Reference(ModelView):
    """Full CRUD — safe reference/config data."""


# --------------------------------------------------------------- commerce
class OrderView(_ReadOnly):
    identity = "order"
    name = "Commande"
    label = "Commandes"
    icon = "fa fa-receipt"
    fields = ["order_number", "status", "customer_name", "customer_phone", "total", "currency", "placed_at"]
    searchable_fields = ["order_number", "customer_name", "customer_phone"]
    sortable_fields = ["placed_at", "total", "status"]
    fields_default_sort = [("placed_at", True)]

    @row_action(
        name="advance_status", text="Faire avancer",
        confirmation="Déplacer cette commande vers le statut choisi ?",
        icon_class="fa fa-forward",
        form='''<form onsubmit="return false;"><div class="mb-3"><label class="form-label">Nouveau statut</label>
          <select class="form-control" name="status">
            <option value="preparing">preparing</option>
            <option value="ready">ready</option>
            <option value="delivering">delivering</option>
            <option value="completed">completed</option>
          </select></div>
          <div class="mb-3"><label class="form-label">Raison (optionnel)</label>
          <input class="form-control" name="reason"/></div></form>''',
    )
    async def advance_status(self, request: Request, pk) -> str:
        data = await request.form()
        return await A.order_update_status(request, pk, data.get("status"), data.get("reason"))

    @row_action(
        name="cancel_order", text="Annuler", action_btn_class="btn-outline-danger",
        confirmation="Annuler cette commande ?", icon_class="fa fa-ban",
        form='''<form onsubmit="return false;"><div class="mb-3"><label class="form-label">Raison</label>
                <input class="form-control" name="reason" required/></div></form>''',
    )
    async def cancel_order(self, request: Request, pk) -> str:
        data = await request.form()
        return await A.order_cancel(request, pk, data.get("reason", ""))


class PaymentView(_ReadOnly):
    identity = "payment"
    name = "Paiement"
    label = "Paiements"
    icon = "fa fa-credit-card"
    fields = ["provider_reference", "operator", "status", "amount", "currency", "payer_phone", "created_at"]
    searchable_fields = ["provider_reference", "payer_phone"]
    sortable_fields = ["created_at", "amount", "status"]
    fields_default_sort = [("created_at", True)]

    @row_action(
        name="reconcile", text="Réconcilier",
        confirmation="Fixer manuellement le statut après vérification ?",
        icon_class="fa fa-scale-balanced",
        form='''<form onsubmit="return false;"><div class="mb-3"><label class="form-label">Statut</label>
          <select class="form-control" name="status">
            <option value="succeeded">succeeded</option>
            <option value="failed">failed</option>
          </select></div>
          <div class="mb-3"><label class="form-label">Note (optionnel)</label>
          <input class="form-control" name="note"/></div></form>''',
    )
    async def reconcile(self, request: Request, pk) -> str:
        data = await request.form()
        return await A.payment_reconcile(request, pk, data.get("status"), data.get("note"))

    @row_action(
        name="refund", text="Rembourser", action_btn_class="btn-outline-danger",
        confirmation="Émettre un remboursement ?", icon_class="fa fa-rotate-left",
        form='''<form onsubmit="return false;"><div class="mb-3"><label class="form-label">Montant</label>
          <input class="form-control" name="amount" type="number" step="0.01" required/></div>
          <div class="mb-3"><label class="form-label">Raison (optionnel)</label>
          <input class="form-control" name="reason"/></div></form>''',
    )
    async def refund(self, request: Request, pk) -> str:
        data = await request.form()
        return await A.payment_refund(request, pk, data.get("amount"), data.get("reason"))


class RefundView(_ReadOnly):
    identity = "refund"
    name = "Remboursement"
    label = "Remboursements"
    icon = "fa fa-rotate-left"
    fields = ["payment_id", "amount", "reason", "provider_reference", "created_at"]
    fields_default_sort = [("created_at", True)]


class DeliveryView(_ReadOnly):
    identity = "delivery"
    name = "Livraison"
    label = "Livraisons"
    icon = "fa fa-truck"
    fields = ["purchase_id", "status", "courier_id", "created_at"]
    sortable_fields = ["created_at", "status"]


class DeliveryEventView(_ReadOnly):
    identity = "delivery-event"
    name = "Événement"
    label = "Événements de livraison"
    icon = "fa fa-route"
    fields = ["delivery_id", "status", "reason", "source", "created_at"]
    sortable_fields = ["created_at", "status"]


class ReturnView(_ReadOnly):
    identity = "return"
    name = "Retour"
    label = "Retours"
    icon = "fa fa-box-open"
    fields = ["purchase_id", "piece_id", "reason", "status", "resolution_note", "restocked", "created_at"]
    sortable_fields = ["created_at", "status"]
    # NOTE: the returns SERVICE is not part of this codebase yet (only
    # constants + models). Returns are view-only here. When the returns module
    # (service + dependencies) is merged, add approve/reject/resolve row actions
    # calling A.return_approve / A.return_reject / A.return_resolve — those
    # helpers are ready in app/ops/actions.py.


# --------------------------------------------------------------- catalogue
class PieceView(_ReadOnly):
    identity = "piece"
    name = "Pièce"
    label = "Pièces"
    icon = "fa fa-tags"
    fields = ["sku", "title", "price", "currency", "condition", "status", "created_at"]
    searchable_fields = ["sku", "title"]
    sortable_fields = ["created_at", "price", "status"]

    @row_action(
        name="publish", text="Publier",
        confirmation="Publier cette pièce dans la boutique ?", icon_class="fa fa-bullhorn",
    )
    async def publish(self, request: Request, pk) -> str:
        return await A.piece_publish(request, pk)


class HouseView(_Reference):
    identity = "house"
    name = "Maison"
    label = "Maisons"
    icon = "fa fa-building"
    fields = ["name"]


class UniverseView(_Reference):
    identity = "universe"
    name = "Univers"
    label = "Univers"
    icon = "fa fa-layer-group"
    fields = ["name"]


class SponsorView(_Reference):
    identity = "sponsor"
    name = "Sponsor"
    label = "Sponsors"
    icon = "fa fa-handshake"


class FeaturedSlotView(_Reference):
    identity = "featured"
    name = "Mise en avant"
    label = "Mises en avant"
    icon = "fa fa-star"


# --------------------------------------------------------------- sourcing
class SourcerProfileView(_ReadOnly):
    identity = "sourcer"
    name = "Sourceur"
    label = "Sourceurs"
    icon = "fa fa-user-tie"
    fields = [
        "id", "user_id", "display_name", "phone", "status", "collaboration_type",
        "payout_method", "payout_phone", "is_featured", "rejection_reason",
        "approved_at", "created_at", "updated_at",
    ]
    searchable_fields = ["display_name", "phone"]
    sortable_fields = ["created_at", "status"]

    @row_action(
        name="approve", text="Approuver",
        confirmation="Approuver ce sourceur et accorder le rôle ?", icon_class="fa fa-check",
    )
    async def approve(self, request: Request, pk) -> str:
        return await A.sourcer_approve(request, pk)

    @row_action(
        name="reject", text="Rejeter", action_btn_class="btn-outline-danger",
        icon_class="fa fa-xmark",
        form='''<form onsubmit="return false;"><div class="mb-3"><label class="form-label">Raison</label>
                <input class="form-control" name="reason" required/></div></form>''',
    )
    async def reject(self, request: Request, pk) -> str:
        data = await request.form()
        return await A.sourcer_reject(request, pk, data.get("reason", ""))


class SubmissionView(_ReadOnly):
    identity = "submission"
    name = "Proposition"
    label = "Propositions"
    icon = "fa fa-inbox"
    fields = ["item_type", "brand", "size_label", "condition_claimed", "desired_price", "status", "created_at"]
    searchable_fields = ["item_type", "brand"]
    sortable_fields = ["created_at", "status"]

    @row_action(name="accept", text="Accepter", confirmation="Accepter cette proposition ?", icon_class="fa fa-check")
    async def accept(self, request: Request, pk) -> str:
        return await A.submission_decide(request, pk, True, None)

    @row_action(
        name="refuse", text="Refuser", action_btn_class="btn-outline-danger", icon_class="fa fa-xmark",
        form='''<form onsubmit="return false;"><div class="mb-3"><label class="form-label">Raison</label>
                <input class="form-control" name="reason" required/></div></form>''',
    )
    async def refuse(self, request: Request, pk) -> str:
        data = await request.form()
        return await A.submission_decide(request, pk, False, data.get("reason"))

    @row_action(
        name="catalogue", text="Cataloguer",
        confirmation="Créer une pièce à partir de cette proposition acceptée ?",
        icon_class="fa fa-tag",
        form='''<form onsubmit="return false;"><div class="mb-3"><label class="form-label">Titre</label>
          <input class="form-control" name="title" required/></div>
          <div class="mb-3"><label class="form-label">Prix</label>
          <input class="form-control" name="price" type="number" step="0.01" required/></div>
          <div class="mb-3"><label class="form-label">État</label>
          <select class="form-control" name="condition">
            <option value="good">good</option>
            <option value="very_good">very good</option>
            <option value="new">new</option>
          </select></div></form>''',
    )
    async def catalogue(self, request: Request, pk) -> str:
        data = await request.form()
        return await A.submission_catalogue(request, pk, data.get("title"), data.get("price"), data.get("condition", "good"))


class PayoutView(_ReadOnly):
    identity = "payout"
    name = "Versement"
    label = "Versements"
    icon = "fa fa-money-bill"
    fields = ["sourcer_id", "amount", "currency", "status", "method", "paid_at", "created_at"]
    sortable_fields = ["created_at", "amount", "status"]


# --------------------------------------------------------------- messages
class NotificationView(_ReadOnly):
    identity = "notification"
    name = "Message"
    label = "Messages envoyés"
    icon = "fa fa-bell"
    fields = ["template_code", "channel", "recipient_phone", "status", "queued_at", "sent_at"]
    sortable_fields = ["queued_at", "sent_at", "status"]
    fields_default_sort = [("queued_at", True)]


# --- e-mail preview helpers (ops panel) --------------------------------------
# Sample values used only to render previews, so admins see a realistic e-mail
# without sending one. Real sends use the message's actual context.
_PREVIEW_SAMPLE = {
    "full_name": "Signe Emmanuel",
    "customer_name": "Signe Emmanuel",
    "applicant_name": "Signe Emmanuel",
    "code": "482915",
    "token": "739204",
    "order_number": "CLO-20260907-8DE3",
    "ttl_minutes": "15",
    "url": "https://apicloset.koungstudio.ca/d/EXEMPLE",
}


class _PreviewDict(dict):
    def __missing__(self, key):  # noqa: ANN001, ANN201
        return "{" + key + "}"


def _preview_html(tpl, brand) -> str:
    """Render a template's HTML (or wrapped plain body) with current branding +
    sample data. Never raises - falls back to the raw string on any error."""
    ctx = {
        "brand_name": getattr(brand, "brand_name", None) or "ClosET",
        "logo_url": getattr(brand, "logo_url", None) or "",
        "accent_color": getattr(brand, "accent_color", None) or "#8A5A2B",
        "support_email": getattr(brand, "support_email", None) or "",
        "footer_note": getattr(brand, "footer_note", None) or "",
        **_PREVIEW_SAMPLE,
    }
    raw = tpl.html_body or (
        '<div style="font-family:Arial,Helvetica,sans-serif;white-space:pre-wrap;'
        'padding:24px;color:#1a1a1a;line-height:1.6;">' + (tpl.body or "") + "</div>"
    )
    try:
        return raw.format_map(_PreviewDict(ctx))
    except Exception:
        return raw


class TemplateView(_Reference):
    identity = "template"
    name = "Modele"
    label = "Modeles de message"
    icon = "fa fa-envelope"
    fields = [
        StringField(
            "title", label="Titre", read_only=True,
            exclude_from_create=True, exclude_from_edit=True,
        ),
        "code", "channel", "locale", "subject",
        TextAreaField(
            "body", label="Texte (repli / WhatsApp-SMS)", rows=6,
            help_text="Version texte simple. Sert de repli pour l'e-mail et de "
                      "contenu pour WhatsApp / SMS.",
        ),
        TextAreaField(
            "html_body", label="HTML (e-mail)", rows=18,
            help_text="HTML riche pour l'e-mail (facultatif). Variables : "
                      "{brand_name}, {logo_url}, {accent_color}, {support_email}, "
                      "{footer_note}, plus les variables du message "
                      "({code}, {token}, {full_name}, {order_number}, "
                      "{customer_name}, {applicant_name}, {ttl_minutes}).",
        ),
    ]
    fields_default_sort = ["code"]
    searchable_fields = ["code", "subject"]
    exclude_fields_from_list = ["subject", "body", "html_body"]
    # code / channel / locale are the dispatch keys - set at creation, then
    # read-only so an edit can't silently detach a template from its caller.
    exclude_fields_from_edit = ["code", "channel", "locale"]

    @row_action(
        name="preview",
        text="Apercu",
        icon_class="fa fa-eye",
        custom_response=True,
    )
    async def preview(self, request: Request, pk) -> Response:  # noqa: ANN001
        """Open the rendered e-mail (current branding + sample data) in a new tab."""
        from app.core.database import AsyncSessionLocal
        from app.modules.notifications.repository import NotificationRepository

        async with AsyncSessionLocal() as db:
            repo = NotificationRepository(db)
            tpl = await repo.get_template_by_id(int(pk))
            brand = await repo.get_branding()
        if tpl is None:
            return HTMLResponse("<p>Modele introuvable.</p>", status_code=404)
        return HTMLResponse(_preview_html(tpl, brand))


class BrandingView(_Reference):
    """Single-row brand identity used to render e-mails (logo, colour, name).

    Editable at runtime, so the logo or accent colour changes with no deploy.
    Only one row exists (id = 1); creating or deleting rows is disabled.
    """

    identity = "branding"
    name = "Marque"
    label = "Identite de marque"
    icon = "fa fa-palette"
    fields = [
        StringField("brand_name", label="Nom de la marque"),
        URLField(
            "logo_url", label="Logo (URL)",
            help_text="URL publique du logo, affiche en en-tete des e-mails.",
        ),
        ColorField("accent_color", label="Couleur d'accent"),
        EmailField("support_email", label="E-mail de support"),
        StringField("footer_note", label="Note de pied de page"),
        "updated_at",
    ]
    exclude_fields_from_list = ["support_email", "footer_note", "updated_at"]
    exclude_fields_from_create = ["updated_at"]
    exclude_fields_from_edit = ["updated_at"]

    def can_create(self, request) -> bool:  # noqa: ANN001
        return False

    def can_delete(self, request) -> bool:  # noqa: ANN001
        return False


# ------------------------------------------------------- people (actions)
class PersonView(_ReadOnly):
    """People with role/active actions. Distinct from the credential-managing
    UserView above (which creates admins); this is the operational people list."""

    identity = "person"
    name = "Personne"
    label = "Personnes"
    icon = "fa fa-id-card"
    fields = ["full_name", "email", "phone", "city", "role", "is_active"]
    searchable_fields = ["full_name", "email", "phone"]
    sortable_fields = ["full_name", "role"]

    @row_action(
        name="change_role", text="Changer de rôle",
        confirmation="Changer le rôle de cette personne ?", icon_class="fa fa-user-gear",
        form='''<form onsubmit="return false;"><div class="mb-3"><label class="form-label">Rôle</label>
          <select class="form-control" name="role">
            <option value="customer">customer</option>
            <option value="sourcer">sourcer</option>
            <option value="courier">courier</option>
            <option value="admin">admin</option>
          </select></div>
          <div class="mb-3"><label class="form-label">Raison (optionnel)</label>
          <input class="form-control" name="reason"/></div></form>''',
    )
    async def change_role(self, request: Request, pk) -> str:
        data = await request.form()
        return await A.user_change_role(request, pk, data.get("role"), data.get("reason"))

    @row_action(
        name="deactivate", text="Désactiver", action_btn_class="btn-outline-danger",
        confirmation="Désactiver ce compte ?", icon_class="fa fa-user-slash",
    )
    async def deactivate(self, request: Request, pk) -> str:
        return await A.user_set_active(request, pk, False)

    @row_action(name="activate", text="Réactiver", confirmation="Réactiver ce compte ?", icon_class="fa fa-user-check")
    async def activate(self, request: Request, pk) -> str:
        return await A.user_set_active(request, pk, True)


# --------------------------------------------------------------- reference
class CourierView(_Reference):
    identity = "courier"
    name = "Coursier"
    label = "Coursiers"
    icon = "fa fa-person-biking"


class PrivilegeCodeView(_Reference):
    identity = "privilege-code"
    name = "Code promo"
    label = "Codes promo"
    icon = "fa fa-ticket"
    fields = [
        "code", "type", "value", "min_order_amount", "max_uses", "times_used",
        "valid_from", "valid_until", "is_active", "created_at",
    ]
    exclude_fields_from_list = ["min_order_amount", "valid_from", "valid_until", "created_at"]
    exclude_fields_from_create = ["times_used", "created_at"]
    # code / type are fixed after creation; times_used is a read-only counter
    exclude_fields_from_edit = ["code", "type", "times_used", "created_at"]
    searchable_fields = ["code"]


class DeliveryRateView(_Reference):
    identity = "delivery-rate"
    name = "Tarif"
    label = "Tarifs de livraison"
    icon = "fa fa-money-bill-wave"
    fields = [
        "scope", "region", "city", "amount", "currency",
        "effective_from", "effective_to",
    ]
    exclude_fields_from_list = ["effective_from", "effective_to"]
    # effective dates default in the DB; set them only for a scheduled change
    exclude_fields_from_create = ["effective_from", "effective_to"]
    # change a price by editing its amount; scope/target are fixed once set
    exclude_fields_from_edit = ["scope", "region", "city", "effective_from", "effective_to"]


class RegionView(_Reference):
    identity = "region"
    name = "Région"
    label = "Régions"
    icon = "fa fa-map"
    fields = ["name", "code"]


class DivisionView(_Reference):
    identity = "division"
    name = "Département"
    label = "Départements"
    icon = "fa fa-map-location"


class SubdivisionView(_Reference):
    identity = "subdivision"
    name = "Arrondissement"
    label = "Arrondissements"
    icon = "fa fa-map-pin"


class NeighbourhoodView(_Reference):
    identity = "neighbourhood"
    name = "Quartier"
    label = "Quartiers"
    icon = "fa fa-location-dot"


class FixedRateCityView(_Reference):
    identity = "fixed-rate-city"
    name = "Ville (tarif fixe)"
    label = "Villes tarif fixe"
    icon = "fa fa-city"


class AppSettingView(_Reference):
    identity = "app-setting"
    name = "Paramètre"
    label = "Paramètres"
    icon = "fa fa-sliders"



def build_admin() -> Admin:
    admin = Admin(
        engine,
        title="ClosET · Ops",
        base_url=settings.OPS_BASE_URL,
        route_name="ops",
        index_view=DashboardHome(label="Tableau de bord", icon="fa fa-gauge-high"),
        templates_dir="app/ops/templates",
        logo_url=settings.OPS_LOGO_URL or None,
        login_logo_url=settings.OPS_LOGO_URL or None,
        auth_provider=OpsAuthProvider(),
        middlewares=[
            Middleware(
                SessionMiddleware,
                secret_key=settings.OPS_SESSION_SECRET,
                session_cookie="closet_ops",
                https_only=settings.ENVIRONMENT == "prod",
                max_age=60 * 60 * 8,          # one working day
                same_site="lax",
            )
        ],
        debug=settings.DEBUG,
    )

    # Views are grouped into collapsible sections in the sidebar via DropDown.
    # Each DropDown is one subgroup; ModelViews inside it keep all their actions.

    # --- Commerce ---
    admin.add_view(DropDown(
        "Commerce", icon="fa fa-cart-shopping",
        views=[
            OrderView(Purchase),
            PaymentView(Payment),
            RefundView(Refund),
            DeliveryView(Delivery),
            DeliveryEventView(DeliveryEvent),
            ReturnView(ReturnTicket),
            PrivilegeCodeView(PrivilegeCode),
        ],
    ))

    # --- Catalogue ---
    admin.add_view(DropDown(
        "Catalogue", icon="fa fa-tags",
        views=[
            PieceView(Piece),
            HouseView(House),
            UniverseView(Universe),
            SponsorView(Sponsor),
            FeaturedSlotView(FeaturedSlot),
        ],
    ))

    # --- Approvisionnement (sourcing) ---
    admin.add_view(DropDown(
        "Approvisionnement", icon="fa fa-user-tie",
        views=[
            SourcerProfileView(SourcerProfile),
            SubmissionView(Submission),
            PayoutView(Payout),
        ],
    ))

    # --- Messagerie ---
    admin.add_view(DropDown(
        "Messagerie", icon="fa fa-bell",
        views=[
            NotificationView(Notification),
            TemplateView(NotificationTemplate),
            BrandingView(Branding),
        ],
    ))

    # --- Personnes & sécurité ---
    admin.add_view(DropDown(
        "Personnes & sécurité", icon="fa fa-users",
        views=[
            PersonView(User),
            UserView(User),
            RefreshTokenView(RefreshToken),
            DeviceTokenView(DeviceToken),
            PasswordResetTokenView(PasswordResetToken),
            AuditLogView(AuditLog),
        ],
    ))

    # --- Paramètres & référentiel ---
    admin.add_view(DropDown(
        "Paramètres & référentiel", icon="fa fa-sliders",
        views=[
            CourierView(Courier),
            DeliveryRateView(DeliveryRate),
            RegionView(Region),
            DivisionView(Division),
            SubdivisionView(Subdivision),
            NeighbourhoodView(Neighbourhood),
            FixedRateCityView(FixedRateCity),
            AppSettingView(AppSetting),
        ],
    ))
    return admin


def mount_ops(app) -> bool:  # noqa: ANN001
    """Attach the panel if it is enabled. Returns True when mounted."""
    if not settings.OPS_ENABLED:
        return False

    if settings.ENVIRONMENT == "prod" and not settings.OPS_ALLOW_IN_PROD:
        # Deliberate: an internal CRUD panel on a public production host is a
        # standing invitation. Set OPS_ALLOW_IN_PROD=true only behind a VPN,
        # an IP allow-list or an SSH tunnel.
        raise RuntimeError(
            "OPS_ENABLED=true in production without OPS_ALLOW_IN_PROD=true. "
            "Restrict access first (VPN / IP allow-list / SSH tunnel)."
        )

    admin = build_admin()
    # Onboarding + 2FA-challenge pages must live INSIDE the admin sub-app so
    # they share its SessionMiddleware and are covered by the provider's
    # allow_routes (otherwise AuthMiddleware bounces them to /ops/login).
    admin.routes.extend(onboarding_routes)
    admin.mount_to(app)
    return True