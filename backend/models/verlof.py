"""Verlof modellen — aanvragen en team-statusbeheer."""
import uuid as uuid_module

from sqlalchemy import Column, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Basis

VERLOF_STATUSSEN = ("pending", "goedgekeurd", "geweigerd")


class VerlofAanvraag(Basis):
    """Verlofaanvraag van een medewerker."""

    __tablename__ = "verlof_aanvragen"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # groep_id verwijderd — gebruik VerlofTeamStatus voor team-context

    # Periode
    start_datum = Column(Date, nullable=False)
    eind_datum = Column(Date, nullable=False)
    aantal_dagen = Column(Integer, nullable=False)

    # Status (gedenormaliseerd voor snelle queries; authoriteit ligt bij VerlofTeamStatus)
    status = Column(SAEnum(*VERLOF_STATUSSEN, name="verlof_status"), default="pending", nullable=False)
    toegekende_code_term = Column(Text, nullable=True)   # VV, KD, VP
    opmerking = Column(Text, nullable=True)

    # Tijdstempels
    aangevraagd_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Behandeling (voor enkelvoudige goedkeuring; multi-team via VerlofTeamStatus)
    behandeld_door = Column(Integer, ForeignKey("gebruikers.id"), nullable=True)
    behandeld_op = Column(DateTime, nullable=True)
    reden_weigering = Column(Text, nullable=True)

    # Namens-aanvraag (beheerder dient in voor teamlid)
    ingediend_door = Column(Integer, ForeignKey("gebruikers.id"), nullable=True, index=True)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    gebruiker = relationship("Gebruiker", back_populates="verlof_aanvragen", foreign_keys=[gebruiker_id])
    behandelaar = relationship("Gebruiker", foreign_keys=[behandeld_door])
    indiener = relationship("Gebruiker", foreign_keys=[ingediend_door])
    team_statussen = relationship(
        "VerlofTeamStatus", back_populates="aanvraag", cascade="all, delete-orphan"
    )


class VerlofTeamStatus(Basis):
    """
    Status van een verlofaanvraag per team — voor multi-team goedkeuringsflow.

    Elke aanvraag krijgt één VerlofTeamStatus per betrokken team.
    Bij enkelvoudige goedkeuring (één team) is er precies één record.
    """

    __tablename__ = "verlof_team_statussen"

    id = Column(Integer, primary_key=True, index=True)
    verlof_id = Column(
        Integer, ForeignKey("verlof_aanvragen.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    status = Column(
        SAEnum(*VERLOF_STATUSSEN, name="verlof_team_status"), default="pending", nullable=False
    )
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    behandeld_door_id = Column(Integer, ForeignKey("gebruikers.id"), nullable=True)
    behandeld_op = Column(DateTime, nullable=True)
    reden_weigering = Column(Text, nullable=True)

    # Relaties
    aanvraag = relationship("VerlofAanvraag", back_populates="team_statussen")
    behandelaar = relationship("Gebruiker", foreign_keys=[behandeld_door_id])
