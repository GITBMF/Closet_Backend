import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Sponsor(Base):
    __tablename__ = "sponsor"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(150), nullable=False)
    logo_url = Column(Text, nullable=False)
    link_url = Column(Text, nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class FeaturedSlot(Base):
    __tablename__ = "featured_slot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slot_type = Column(String(50), nullable=False)
    
    # Clé étrangère pointant vers le module Catalogue
    piece_id = Column(UUID(as_uuid=True), ForeignKey("piece.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, default=0, nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationship vers le modèle Piece du Catalogue (Reads Catalogue)
    piece = relationship("Piece", lazy="joined")