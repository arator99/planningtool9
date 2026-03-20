"""Typetabel modellen — roostersjablonen per locatie (Fase 8)."""
import uuid as uuid_module

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from database import Basis


class Typetabel(Basis):
    """
    Roostersjabloon — cyclisch weekpatroon van N weken per locatie.

    Eén typetabel kan als 'actief' gemarkeerd worden per locatie.
    Medewerkers krijgen een startweek toegewezen die bepaalt welke
    week in de cyclus ze op een gegeven datum volgen.
    """

    __tablename__ = "typetabellen"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=False, index=True)
    naam = Column(String(100), nullable=False)
    beschrijving = Column(Text, nullable=True)
    aantal_weken = Column(Integer, nullable=False)  # 1–52
    is_actief = Column(Boolean, default=False, nullable=False)
    aangemaakt_door_id = Column(Integer, ForeignKey("gebruikers.id"), nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gewijzigd_op = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("locatie_id", "naam", name="uq_typetabel_locatie_naam"),
    )

    # Relaties
    entries = relationship("TypetabelEntry", back_populates="typetabel", cascade="all, delete-orphan")


class TypetabelEntry(Basis):
    """
    Één cel in een typetabel grid: week × dag → shift_code.

    week_nummer: 1-based (1 t/m aantal_weken)
    dag_van_week: 0=maandag, 6=zondag
    shift_code: vrije tekst (bijv. "D", "N", "RXW") — NIET FK naar Shiftcode,
                zodat sjablonen stabiel blijven als shiftcodes worden hernoemd.
    """

    __tablename__ = "typetabel_entries"

    id = Column(Integer, primary_key=True, index=True)
    typetabel_id = Column(Integer, ForeignKey("typetabellen.id", ondelete="CASCADE"), nullable=False, index=True)
    week_nummer = Column(Integer, nullable=False)
    dag_van_week = Column(Integer, nullable=False)   # 0–6
    shift_code = Column(String(20), nullable=True)

    __table_args__ = (
        UniqueConstraint("typetabel_id", "week_nummer", "dag_van_week", name="uq_entry_week_dag"),
    )

    # Relaties
    typetabel = relationship("Typetabel", back_populates="entries")
