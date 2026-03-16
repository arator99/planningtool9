"""Locatie model — het beheerniveau boven teams (één per productielocatie)."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from database import Basis


class Locatie(Basis):
    """Productielocatie — multi-tenant scheiding op het hoogste niveau."""

    __tablename__ = "locaties"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    naam = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)   # bijv. "LOC1", "NAT"
    area_label = Column(String(100), nullable=True)          # puur label, geen apart DB-object
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)
