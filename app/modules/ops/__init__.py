"""Ops models — operational key/value settings.

A tiny table for runtime-tunable settings the admin can change without a
deploy (e.g. reservation-hold minutes, default currency). Keyed by a text
key; value is JSON so any shape fits.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"),
        onupdate=text("now()"), nullable=False,
    )