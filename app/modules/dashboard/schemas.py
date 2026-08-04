"""Dashboard API contracts — shapes of the read-only KPI responses."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class Overview(BaseModel):
    orders_realized: int
    orders_pending: int
    orders_completed: int
    revenue_realized: Decimal
    revenue_completed: Decimal
    pieces_for_sale: int
    pieces_sold: int
    sourcers_active: int
    sourcer_applications_pending: int
    payouts_outstanding: Decimal


class SalesPoint(BaseModel):
    day: date
    orders: int
    revenue: Decimal


class SalesSeries(BaseModel):
    points: list[SalesPoint]
    total_orders: int
    total_revenue: Decimal


class SourcerBalance(BaseModel):
    sourcer_id: uuid.UUID
    display_name: str | None
    status: str
    amount_outstanding: Decimal
    amount_paid: Decimal
    payouts_open: int


class UnsoldPiece(BaseModel):
    piece_id: uuid.UUID
    title: str
    price: Decimal | None
    created_at: datetime
    age_days: int


class OverdueOrder(BaseModel):
    purchase_id: uuid.UUID
    order_number: str
    status: str
    total: Decimal
    placed_at: datetime | None
    age_days: int


class Alerts(BaseModel):
    unsold_pieces: list[UnsoldPiece]
    overdue_orders: list[OverdueOrder]
    unsold_count: int
    overdue_count: int