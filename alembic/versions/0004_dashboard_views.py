"""dashboard read-only views

Revision ID: 0004_dashboard_views
Revises: 0003_full_schema
Create Date: 2026-08-03

Read-only SQL views the admin dashboard selects from. No tables are touched;
downgrade drops the views. Keeping the aggregation here (not in Python) means
the dashboard module stays a thin reader, and these can be turned into
MATERIALIZED views later if they get slow, without touching app code.
"""

from alembic import op

revision = "0004_dashboard_views"
down_revision = "0003_full_schema"
branch_labels = None
depends_on = None

# a sale counts as "realized revenue" once the order is paid and not cancelled
_REALIZED = "('paid','preparing','ready','delivering','completed')"


def upgrade() -> None:
    # ---- headline KPIs (single row) --------------------------------------
    op.execute(
        f"""
        CREATE VIEW v_dashboard_overview AS
        SELECT
            (SELECT COUNT(*) FROM purchase
                WHERE status IN {_REALIZED})                     AS orders_realized,
            (SELECT COUNT(*) FROM purchase
                WHERE status = 'pending')                        AS orders_pending,
            (SELECT COUNT(*) FROM purchase
                WHERE status = 'completed')                      AS orders_completed,
            (SELECT COALESCE(SUM(total), 0) FROM purchase
                WHERE status IN {_REALIZED})                     AS revenue_realized,
            (SELECT COALESCE(SUM(total), 0) FROM purchase
                WHERE status = 'completed')                      AS revenue_completed,
            (SELECT COUNT(*) FROM piece
                WHERE status = 'published')                      AS pieces_for_sale,
            (SELECT COUNT(*) FROM piece
                WHERE status = 'sold')                           AS pieces_sold,
            (SELECT COUNT(*) FROM sourcer_profile
                WHERE status = 'approved')                       AS sourcers_active,
            (SELECT COUNT(*) FROM sourcer_profile
                WHERE status = 'pending')                        AS sourcer_applications_pending,
            (SELECT COALESCE(SUM(amount), 0) FROM payout
                WHERE status IN ('pending','approved'))          AS payouts_outstanding
        ;
        """
    )

    # ---- daily sales series ---------------------------------------------
    op.execute(
        f"""
        CREATE VIEW v_dashboard_sales_daily AS
        SELECT
            (placed_at AT TIME ZONE 'UTC')::date AS day,
            COUNT(*)                             AS orders,
            COALESCE(SUM(total), 0)              AS revenue
        FROM purchase
        WHERE status IN {_REALIZED}
          AND placed_at IS NOT NULL
        GROUP BY 1
        ORDER BY 1;
        """
    )

    # ---- sourcer balances (owed vs paid) --------------------------------
    op.execute(
        """
        CREATE VIEW v_dashboard_sourcer_balances AS
        SELECT
            sp.id                                                   AS sourcer_id,
            sp.display_name,
            sp.status,
            COALESCE(SUM(p.amount) FILTER (
                WHERE p.status IN ('pending','approved')), 0)       AS amount_outstanding,
            COALESCE(SUM(p.amount) FILTER (
                WHERE p.status = 'paid'), 0)                        AS amount_paid,
            COUNT(p.id) FILTER (
                WHERE p.status IN ('pending','approved'))           AS payouts_open
        FROM sourcer_profile sp
        LEFT JOIN payout p ON p.sourcer_id = sp.id
        GROUP BY sp.id, sp.display_name, sp.status;
        """
    )

    # ---- alert feeds (each row is one thing needing attention) ----------
    # unsold: published pieces aging on the shelf
    op.execute(
        """
        CREATE VIEW v_dashboard_unsold_pieces AS
        SELECT
            id            AS piece_id,
            title,
            price,
            created_at,
            (now() - created_at)                                   AS age
        FROM piece
        WHERE status = 'published'
        ORDER BY created_at ASC;
        """
    )

    # overdue: orders stuck mid-fulfilment (paid but not completed/cancelled)
    op.execute(
        """
        CREATE VIEW v_dashboard_overdue_orders AS
        SELECT
            id            AS purchase_id,
            order_number,
            status,
            total,
            placed_at,
            (now() - placed_at)                                    AS age
        FROM purchase
        WHERE status IN ('paid','preparing','ready','delivering')
        ORDER BY placed_at ASC;
        """
    )


def downgrade() -> None:
    for view in (
        "v_dashboard_overdue_orders",
        "v_dashboard_unsold_pieces",
        "v_dashboard_sourcer_balances",
        "v_dashboard_sales_daily",
        "v_dashboard_overview",
    ):
        op.execute(f"DROP VIEW IF EXISTS {view};")
