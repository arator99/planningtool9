"""Competentie modellen — vaardigheden per locatie."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database import Basis

NIVEAUS = ("basis", "gevorderd", "expert")


class Competentie(Basis):
    """Competentie/vaardigheid master tabel — per locatie."""

    __tablename__ = "competenties"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=False, index=True)
    naam = Column(String(150), nullable=False, index=True)
    beschrijving = Column(Text, nullable=True)
    categorie = Column(String(100), nullable=True)
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gedeactiveerd_op = Column(DateTime, nullable=True)

    # Relaties
    gebruiker_koppelingen = relationship(
        "GebruikerCompetentie", back_populates="competentie", cascade="all, delete-orphan"
    )


class GebruikerCompetentie(Basis):
    """Koppeltabel gebruikers ↔ competenties met niveau en vervaldatum."""

    __tablename__ = "gebruiker_competenties"
    __table_args__ = (
        UniqueConstraint("gebruiker_id", "competentie_id", name="uq_gebruiker_competentie"),
    )

    id = Column(Integer, primary_key=True, index=True)
    gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competentie_id = Column(
        Integer, ForeignKey("competenties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    niveau = Column(SAEnum(*NIVEAUS, name="competentie_niveau"), nullable=True)
    geldig_tot = Column(Date, nullable=True)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Relaties
    gebruiker = relationship("Gebruiker", back_populates="competenties")
    competentie = relationship("Competentie", back_populates="gebruiker_koppelingen")
