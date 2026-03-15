from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database import Basis


class Groep(Basis):
    """Planningsgroep — de multi-tenant scheiding in v0.8."""

    __tablename__ = "groepen"

    id = Column(Integer, primary_key=True, index=True)
    naam = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)  # bijv. "GRP1", "GRP2"
    beschrijving = Column(String(255), nullable=True)
    is_actief = Column(Boolean, default=True, nullable=False)

    # Relaties
    config = relationship("GroepConfig", back_populates="groep", uselist=False, cascade="all, delete-orphan")
    gebruikers = relationship("Gebruiker", back_populates="groep")
    leden = relationship("GebruikerGroep", back_populates="groep", cascade="all, delete-orphan")


class GroepConfig(Basis):
    """Configuratie per planningsgroep — HR drempelwaarden en standaardinstellingen."""

    __tablename__ = "groep_configs"

    id = Column(Integer, primary_key=True, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id", ondelete="CASCADE"), unique=True, nullable=False)

    # HR drempelwaarden (overschrijven de globale hr_regels)
    max_uren_week = Column(Integer, default=50, nullable=False)
    max_dagen_rij = Column(Integer, default=7, nullable=False)
    max_werkdagen_cyclus = Column(Integer, default=19, nullable=False)
    cyclus_lengte_dagen = Column(Integer, default=28, nullable=False)
    min_rust_uren = Column(Integer, default=11, nullable=False)
    max_weekends_rij = Column(Integer, default=6, nullable=False)

    # Standaardinstellingen
    standaard_taal = Column(String(5), default="nl", nullable=False)

    # Relatie
    groep = relationship("Groep", back_populates="config")


class GebruikerGroep(Basis):
    """Many-to-many koppeling tussen gebruiker en planningsgroep, met reserve-rol."""

    __tablename__ = "gebruiker_groepen"
    __table_args__ = (UniqueConstraint("gebruiker_id", "groep_id", name="uq_gebruiker_groep"),)

    id = Column(Integer, primary_key=True, index=True)
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id", ondelete="CASCADE"), nullable=False, index=True)
    is_reserve = Column(Boolean, default=False, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Relaties
    gebruiker = relationship("Gebruiker", back_populates="groepen")
    groep = relationship("Groep", back_populates="leden")
