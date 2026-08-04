"""KPI home page for the ops console.

Replaces the empty Starlette-Admin landing page with a live dashboard that reads
the SAME DashboardService the API uses (over the v_dashboard_* SQL views), so the
figures here always match /api/v1/admin/dashboard/*.

It renders THROUGH the admin's own template that extends `layout.html`, so the
page appears inside the normal shell — sidebar, top bar and theme included — and
links are built from the framework's real route names (url_for). It does not
emit standalone HTML.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates
from starlette_admin.views import CustomView

from app.core.database import AsyncSessionLocal
from app.modules.dashboard.dependencies import get_dashboard_service


def _money(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{n:,.0f} XAF".replace(",", "\u00a0")  # thin non-breaking space


def _tone(status: str) -> str:
    """Map a status to a Tabler colour suffix (used as bg-<tone>-lt)."""
    s = (status or "").lower()
    if s in ("paid", "succeeded", "completed", "delivered", "approved", "published", "resolved"):
        return "green"
    if s in ("failed", "cancelled", "refused", "rejected"):
        return "red"
    if s in ("delivering", "in_transit", "reserved", "assigned"):
        return "purple"
    return "yellow"


class DashboardHome(CustomView):
    """Custom index view: KPI cards + things needing attention, rendered inside
    the admin shell via the `dashboard_home.html` template."""

    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        cards: list[dict] = []
        alerts_ctx = {
            "overdue_orders": [], "unsold_pieces": [],
            "overdue_count": 0, "unsold_count": 0,
        }
        error = None

        try:
            async with AsyncSessionLocal() as db:
                svc = get_dashboard_service(db)
                ov = await svc.overview()
                al = await svc.alerts(limit=8)

            cards = [
                {"label": "Chiffre d'affaires (réalisé)", "value": _money(ov.revenue_realized),
                 "hint": f"{ov.orders_realized} commandes en cours"},
                {"label": "Ventes finalisées", "value": _money(ov.revenue_completed),
                 "hint": f"{ov.orders_completed} livrées"},
                {"label": "Pièces en vente", "value": str(ov.pieces_for_sale),
                 "hint": f"{ov.pieces_sold} vendues"},
                {"label": "Versements dus", "value": _money(ov.payouts_outstanding),
                 "hint": f"{ov.sourcers_active} sourceurs actifs"},
                {"label": "Commandes en attente", "value": str(ov.orders_pending),
                 "hint": "à traiter"},
                {"label": "Candidatures sourceurs", "value": str(ov.sourcer_applications_pending),
                 "hint": "à examiner"},
            ]
            alerts_ctx = {
                "overdue_orders": [
                    {"order_number": o.order_number, "status": o.status,
                     "tone": _tone(o.status), "age_days": o.age_days}
                    for o in (al.overdue_orders or [])
                ],
                "unsold_pieces": [
                    {"title": p.title, "price": _money(p.price), "age_days": p.age_days}
                    for p in (al.unsold_pieces or [])
                ],
                "overdue_count": al.overdue_count,
                "unsold_count": al.unsold_count,
            }
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the home page
            error = str(exc)

        return templates.TemplateResponse(
            request=request,
            name="dashboard_home.html",
            context={
                "title": "Tableau de bord",
                "cards": cards,
                "alerts": alerts_ctx,
                "error": error,
            },
        )