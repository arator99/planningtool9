"""Planning modellen — shifts, shiftcodes, werkposten en rode lijn configuratie."""
import uuid as uuid_module

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from database import Basis


class Werkpost(Basis):
    """Werkpost/functie binnen een locatie."""

    __tablename__ = "werkposten"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=False, index=True)
    naam = Column(String(100), nullable=False)
    beschrijving = Column(Text, nullable=True)
    telt_als_werkdag = Column(Boolean, default=True, nullable=False)
    reset_12u_rust = Column(Boolean, default=False, nullable=False)
    breekt_werk_reeks = Column(Boolean, default=False, nullable=False)
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gedeactiveerd_op = Column(DateTime, nullable=True)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    shiftcodes = relationship("Shiftcode", back_populates="werkpost")


class Shiftcode(Basis):
    """
    Shiftcode — beschrijft één type dienst met HR-semantiek.

    locatie_id is nullable: NULL = nationaal beschikbaar voor alle locaties.
    Flags (port vanuit v0.7 shiftcode_domein.py):
      telt_als_werkdag    — telt mee voor de 19-dagenregel
      is_nachtprestatie   — activeert nacht-vervolgingsbeperking (12u rust vereist)
      reset_nacht         — heft nacht-vervolgingsbeperking op (bv. lichte dagdienst)
    """

    __tablename__ = "shiftcodes"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    werkpost_id = Column(Integer, ForeignKey("werkposten.id"), nullable=True)
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=True, index=True)  # NULL = nationaal
    dag_type = Column(String(20), nullable=True)    # 'werkdag', 'weekend', 'feestdag'
    shift_type = Column(String(20), nullable=True)  # 'vroeg', 'laat', 'nacht' (ook gebruikt voor HUD-kleur)
    code = Column(String(20), nullable=False, index=True)
    beschrijving = Column(Text, nullable=True)       # label in HUD / tooltip
    start_uur = Column(String(5), nullable=True)    # HH:MM, bijv. "06:00"
    eind_uur = Column(String(5), nullable=True)
    is_kritisch = Column(Boolean, default=False, nullable=False)

    # HR-flags (port vanuit v0.7)
    telt_als_werkdag = Column(Boolean, default=True, nullable=False)
    is_nachtprestatie = Column(Boolean, default=False, nullable=False)
    # reset_nacht=True: code heft nacht-vervolgingsbeperking op (VV, KD, Z — NIET de nachtshift zelf)
    reset_nacht = Column(Boolean, default=False, nullable=False)

    # Relaties
    werkpost = relationship("Werkpost", back_populates="shiftcodes")


class ShiftTijd(Basis):
    """Tijdsmapping voor HR-validatie — legacy tabel, zal vervallen zodra Shiftcode.flags volledig zijn."""

    __tablename__ = "shift_tijden"

    id = Column(Integer, primary_key=True, index=True)
    shiftcode = Column(String(10), unique=True, nullable=False, index=True)
    start_tijd = Column(String(8), nullable=True)
    eind_tijd = Column(String(8), nullable=True)
    is_nachtshift = Column(Boolean, default=False, nullable=False)
    is_rustdag = Column(Boolean, default=False, nullable=False)
    rustdag_type = Column(String(10), nullable=True)    # 'RXW', 'RXF', 'CXW', 'CXA'
    telt_als_werkdag = Column(Boolean, default=True, nullable=False)
    uren_per_shift = Column(String(5), nullable=True)


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
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    datum = Column(Date, nullable=False, index=True)
    shift_code = Column(String(20), nullable=True)       # NULL = vrije dag
    notitie = Column(Text, nullable=True)
    notitie_gelezen = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="concept", nullable=False)   # 'concept', 'gepubliceerd'
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    gebruiker = relationship("Gebruiker", back_populates="planning_shifts")
    overrides = relationship("PlanningOverride", back_populates="planning_shift", cascade="all, delete-orphan")


class PlanningOverride(Basis):
    """Audit trail voor goedgekeurde CRITICAL HR-overtredingen."""

    __tablename__ = "planning_overrides"

    id = Column(Integer, primary_key=True, index=True)
    planning_shift_id = Column(
        Integer, ForeignKey("planning.id", ondelete="CASCADE"), nullable=False, index=True
    )
    regel_code = Column(String(50), nullable=False, index=True)
    ernst_niveau = Column(String(20), nullable=False)
    overtreding_bericht = Column(Text, nullable=False)
    reden_afwijking = Column(Text, nullable=True)
    goedgekeurd_door = Column(Integer, ForeignKey("gebruikers.id"), nullable=True, index=True)
    goedgekeurd_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Relaties
    planning_shift = relationship("Planning", back_populates="overrides")


class PlanningWijziging(Basis):
    """
    Wijzigingenlog voor planning — gedenormaliseerd locatie_id voor snelle tenant-filtering.
    Wordt aangemaakt bij elke mutatie op een Planning-record.
    """

    __tablename__ = "planning_wijzigingen"

    id = Column(Integer, primary_key=True, index=True)
    planning_id = Column(Integer, ForeignKey("planning.id", ondelete="CASCADE"), nullable=False, index=True)
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=False, index=True)  # gedenormaliseerd
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id"), nullable=True, index=True)
    actie = Column(String(50), nullable=False)          # 'aanmaken', 'wijzigen', 'verwijderen'
    oude_shift_code = Column(String(20), nullable=True)
    nieuwe_shift_code = Column(String(20), nullable=True)
    tijdstip = Column(DateTime, server_default=func.now(), nullable=False, index=True)


class RodeLijnConfig(Basis):
    """
    Rode lijn configuratie — exact één record per installatie.

    Rode lijn datums worden NOOIT opgeslagen, altijd berekend:
        datum_n = referentie_datum + n × 28
    De blokgrootte (hoeveel 28-daagse periodes per cyclus) staat in NationaleHRRegel(code='RODE_LIJN_BLOK_GROOTTE').
    """

    __tablename__ = "rode_lijn_config"

    id = Column(Integer, primary_key=True, index=True)
    referentie_datum = Column(Date, nullable=False)    # startpunt van de eerste cyclus
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gewijzigd_op = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
