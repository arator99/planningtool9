from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum as SAEnum,
    ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from database import Basis


class Werkpost(Basis):
    """Werkpost/functie binnen een planningsgroep."""

    __tablename__ = "werkposten"

    id = Column(Integer, primary_key=True, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=False, index=True)
    naam = Column(String(100), nullable=False)
    beschrijving = Column(Text, nullable=True)
    telt_als_werkdag = Column(Boolean, default=True, nullable=False)
    reset_12u_rust = Column(Boolean, default=False, nullable=False)
    breekt_werk_reeks = Column(Boolean, default=False, nullable=False)
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gedeactiveerd_op = Column(DateTime, nullable=True)

    # Relaties
    shiftcodes = relationship("Shiftcode", back_populates="werkpost")


class Shiftcode(Basis):
    """Shiftcode gekoppeld aan een werkpost."""

    __tablename__ = "shiftcodes"

    id = Column(Integer, primary_key=True, index=True)
    werkpost_id = Column(Integer, ForeignKey("werkposten.id"), nullable=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=False, index=True)
    dag_type = Column(String(20), nullable=True)   # 'werkdag', 'weekend', 'feestdag'
    shift_type = Column(String(20), nullable=True)  # 'early', 'late', 'night'
    code = Column(String(20), nullable=False)
    start_uur = Column(String(5), nullable=True)    # HH:MM formaat, bijv. "06:00"
    eind_uur = Column(String(5), nullable=True)
    is_kritisch = Column(Boolean, default=False, nullable=False)

    # Relaties
    werkpost = relationship("Werkpost", back_populates="shiftcodes")


class ShiftTijd(Basis):
    """Tijdsmapping voor HR-validatie — koppelt shiftcode aan uren en type."""

    __tablename__ = "shift_tijden"

    id = Column(Integer, primary_key=True, index=True)
    shiftcode = Column(String(10), unique=True, nullable=False, index=True)
    start_tijd = Column(String(8), nullable=True)   # HH:MM:SS, NULL voor rustdagen
    eind_tijd = Column(String(8), nullable=True)
    is_nachtshift = Column(Boolean, default=False, nullable=False)
    is_rustdag = Column(Boolean, default=False, nullable=False)
    rustdag_type = Column(String(10), nullable=True)    # 'RXW', 'RXF', 'CXW', 'CXA'
    telt_als_werkdag = Column(Boolean, default=True, nullable=False)
    uren_per_shift = Column(String(5), nullable=True)   # bijv. "8.00"


class SpecialCode(Basis):
    """Speciale codes voor verlof en rustdagen."""

    __tablename__ = "special_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)
    naam = Column(String(100), nullable=False)
    term = Column(String(50), nullable=True)
    telt_als_werkdag = Column(Boolean, default=False, nullable=False)
    reset_12u_rust = Column(Boolean, default=False, nullable=False)
    breekt_werk_reeks = Column(Boolean, default=False, nullable=False)


class Planning(Basis):
    """Planningshift — één shift per gebruiker per dag."""

    __tablename__ = "planning"
    __table_args__ = (
        UniqueConstraint("gebruiker_id", "datum", name="uq_planning_gebruiker_datum"),
    )

    id = Column(Integer, primary_key=True, index=True)
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=False, index=True)
    datum = Column(Date, nullable=False, index=True)
    shift_code = Column(String(20), nullable=True)       # NULL = vrije dag
    notitie = Column(Text, nullable=True)
    notitie_gelezen = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="concept", nullable=False)   # 'concept', 'gepubliceerd'
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Relaties
    gebruiker = relationship("Gebruiker", back_populates="planning_shifts")
    overrides = relationship("PlanningOverride", back_populates="planning_shift", cascade="all, delete-orphan")


class PlanningOverride(Basis):
    """Audit trail voor goedgekeurde CRITICAL HR-overtredingen."""

    __tablename__ = "planning_overrides"

    id = Column(Integer, primary_key=True, index=True)
    planning_shift_id = Column(Integer, ForeignKey("planning.id", ondelete="CASCADE"), nullable=False, index=True)
    regel_code = Column(String(50), ForeignKey("hr_regels.code"), nullable=False, index=True)
    ernst_niveau = Column(String(20), nullable=False)           # altijd 'CRITICAL'
    overtreding_bericht = Column(Text, nullable=False)
    reden_afwijking = Column(Text, nullable=True)               # verplicht in te vullen door planner
    goedgekeurd_door = Column(Integer, ForeignKey("gebruikers.id"), nullable=True, index=True)
    goedgekeurd_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Relaties
    planning_shift = relationship("Planning", back_populates="overrides")
