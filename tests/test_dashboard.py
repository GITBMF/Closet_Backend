"""Integration tests for the dashboard module.

Reads the v_dashboard_* views (migration 0004) with seeded data and checks the
KPI aggregations and response shapes: overview totals, the daily sales series and
its date filter, sourcer balances (owed vs paid), and the alert feeds (unsold
pieces, overdue orders).

Requires the dashboard views to exist. The autouse fixture creates them if the
test DB was built from model metadata rather than the migration, so the suite is
self-contained.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta

import pytest_asyncio
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.service import DashboardService

_REALIZED = "('paid','preparing','ready','delivering','completed')"

_VIEWS_SQL = [
    f"""CREATE OR REPLACE VIEW v_dashboard_overview AS SELECT
        (SELECT COUNT(*) FROM purchase WHERE status IN {_REALIZED}) AS orders_realized,
        (SELECT COUNT(*) FROM purchase WHERE status='pending') AS orders_pending,
        (SELECT COUNT(*) FROM purchase WHERE status='completed') AS orders_completed,
        (SELECT COALESCE(SUM(total),0) FROM purchase WHERE status IN {_REALIZED}) AS revenue_realized,
        (SELECT COALESCE(SUM(total),0) FROM purchase WHERE status='completed') AS revenue_completed,
        (SELECT COUNT(*) FROM piece WHERE status='published') AS pieces_for_sale,
        (SELECT COUNT(*) FROM piece WHERE status='sold') AS pieces_sold,
        (SELECT COUNT(*) FROM sourcer_profile WHERE status='approved') AS sourcers_active,
        (SELECT COUNT(*) FROM sourcer_profile WHERE status='pending') AS sourcer_applications_pending,
        (SELECT COALESCE(SUM(amount),0) FROM payout WHERE status IN ('pending','approved')) AS payouts_outstanding""",
    f"""CREATE OR REPLACE VIEW v_dashboard_sales_daily AS SELECT
        (placed_at AT TIME ZONE 'UTC')::date AS day, COUNT(*) AS orders, COALESCE(SUM(total),0) AS revenue
        FROM purchase WHERE status IN {_REALIZED} AND placed_at IS NOT NULL GROUP BY 1 ORDER BY 1""",
    """CREATE OR REPLACE VIEW v_dashboard_sourcer_balances AS SELECT
        sp.id AS sourcer_id, sp.display_name, sp.status,
        COALESCE(SUM(p.amount) FILTER (WHERE p.status IN ('pending','approved')),0) AS amount_outstanding,
        COALESCE(SUM(p.amount) FILTER (WHERE p.status='paid'),0) AS amount_paid,
        COUNT(p.id) FILTER (WHERE p.status IN ('pending','approved')) AS payouts_open
        FROM sourcer_profile sp LEFT JOIN payout p ON p.sourcer_id=sp.id
        GROUP BY sp.id, sp.display_name, sp.status""",
    """CREATE OR REPLACE VIEW v_dashboard_unsold_pieces AS SELECT
        id AS piece_id, title, price, created_at, (now()-created_at) AS age
        FROM piece WHERE status='published' ORDER BY created_at ASC""",
    """CREATE OR REPLACE VIEW v_dashboard_overdue_orders AS SELECT
        id AS purchase_id, order_number, status, total, placed_at, (now()-placed_at) AS age
        FROM purchase WHERE status IN ('paid','preparing','ready','delivering') ORDER BY placed_at ASC""",
]


def _svc(db) -> DashboardService:
    return DashboardService(DashboardRepository(db))


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _views() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        for sql in _VIEWS_SQL:
            await conn.execute(text(sql))
    yield


@pytest_asyncio.fixture(autouse=True)
async def _seed() -> AsyncGenerator[None, None]:
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("TRUNCATE payout, sourcer_profile, piece, purchase, users RESTART IDENTITY CASCADE")
        )
        u = uuid.uuid4()
        await s.execute(
            text("INSERT INTO users (id,email,full_name,role,is_active) VALUES (:i,'a@c.cm','A','customer',true)"),
            {"i": u},
        )
        for i, (st, tot) in enumerate(
            [("completed", 52000), ("delivering", 30000), ("pending", 15000), ("completed", 20000)]
        ):
            await s.execute(
                text(
                    "INSERT INTO purchase (id,user_id,order_number,customer_name,customer_phone,"
                    "status,subtotal,delivery_fee,total,currency,placed_at) "
                    "VALUES (:i,:u,:n,'A','+237600',:st,:t,0,:t,'XAF',now())"
                ),
                {"i": uuid.uuid4(), "u": u, "n": f"CLO-{i}", "st": st, "t": tot},
            )
        for st in ["published", "published", "published", "sold"]:
            await s.execute(
                text(
                    "INSERT INTO piece (id,title,slug,price,status,sku,condition,currency) "
                    "VALUES (:i,'P',:sl,10000,:st,:sk,'good','XAF')"
                ),
                {"i": uuid.uuid4(), "sl": uuid.uuid4().hex[:8], "st": st, "sk": uuid.uuid4().hex[:8]},
            )
        sp = uuid.uuid4()
        await s.execute(
            text("INSERT INTO sourcer_profile (id,user_id,display_name,status) VALUES (:i,:u,'Ada Store','approved')"),
            {"i": sp, "u": u},
        )
        await s.execute(
            text("INSERT INTO payout (id,sourcer_id,amount,currency,status) VALUES (:i,:s,25000,'XAF','pending')"),
            {"i": uuid.uuid4(), "s": sp},
        )
        await s.execute(
            text("INSERT INTO payout (id,sourcer_id,amount,currency,status) VALUES (:i,:s,12000,'XAF','paid')"),
            {"i": uuid.uuid4(), "s": sp},
        )
        await s.commit()
    yield


class TestOverview:
    async def test_overview_totals(self):
        async with AsyncSessionLocal() as db:
            o = await _svc(db).overview()
        assert o.orders_realized == 3           # completed + delivering + completed
        assert o.orders_completed == 2
        assert int(o.revenue_realized) == 102000  # pending excluded
        assert int(o.revenue_completed) == 72000
        assert o.pieces_for_sale == 3
        assert o.pieces_sold == 1
        assert o.sourcers_active == 1
        assert int(o.payouts_outstanding) == 25000


class TestSales:
    async def test_series_and_totals(self):
        async with AsyncSessionLocal() as db:
            s = await _svc(db).sales(start=None, end=None)
        assert s.total_orders == 3
        assert int(s.total_revenue) == 102000

    async def test_date_filter_excludes_today(self):
        async with AsyncSessionLocal() as db:
            s = await _svc(db).sales(
                start=date.today() - timedelta(days=10), end=date.today() - timedelta(days=1)
            )
        assert s.points == []


class TestSourcers:
    async def test_balances(self):
        async with AsyncSessionLocal() as db:
            bals = await _svc(db).sourcer_balances(limit=50, offset=0)
        assert len(bals) == 1
        b = bals[0]
        assert int(b.amount_outstanding) == 25000
        assert int(b.amount_paid) == 12000
        assert b.payouts_open == 1


class TestAlerts:
    async def test_alert_feeds(self):
        async with AsyncSessionLocal() as db:
            a = await _svc(db).alerts(limit=50)
        assert a.unsold_count == 3
        assert a.overdue_count == 1
        assert len(a.unsold_pieces) == 3
        assert len(a.overdue_orders) == 1
        assert a.overdue_orders[0].status == "delivering"
