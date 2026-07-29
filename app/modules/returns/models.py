"""Returns models — return tickets against a purchased piece."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.modules.returns.constants import ReturnStatus

return_status_enum = PGEnum(
    ReturnStatus, name="return_status",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class ReturnTicket(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "return_ticket"

    purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("purchase.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    piece_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("piece.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReturnStatus] = mapped_column(
        return_status_enum, nullable=False,
        server_default=ReturnStatus.REQUESTED.value, index=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    restocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )