"""Locatie model — het beheerniveau boven teams (één per productielocatie)."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, func, text

from database import Basis


class Locatie(Basis):
    """Productielocatie — multi-tenant scheiding op het hoogste niveau."""

    __tablename__ = "locaties"
    __table_args__ = (
        # Index voor HR area-scope resolutie: alle locaties in een area opvragen
        Index(
            "ix_locaties_area_id",
            "area_id",
            postgresql_where=text("is_actief = TRUE AND verwijderd_op IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    naam = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)   # bijv. "LOC1", "NAT"
    area_id = Column(
        Integer, ForeignKey("areas.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)
