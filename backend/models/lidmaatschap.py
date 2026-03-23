"""Lidmaatschap model — koppelt een gebruiker aan een team."""
import enum
import uuid as uuid_module

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Index, Integer, String, func, text,
)
from sqlalchemy.orm import relationship

from database import Basis


class LidmaatschapType(str, enum.Enum):
    """Aard van het teamlidmaatschap."""
    vast = "Vast"
    reserve = "Reserve"
    detachering = "Detachering"


class Lidmaatschap(Basis):
    """
    Teamlidmaatschap — vervangt de 'teamlid' en 'planner' rollen in GebruikerRol.

    is_planner=True geeft schrijfrechten op de planning van dit team.
    Enkel de beheerder mag is_planner op True zetten.

    Invariant: elke gebruiker heeft altijd minstens 1 actief lidmaatschap.
    """

    __tablename__ = "lidmaatschappen"
    __table_args__ = (
        # Partial unique index: staat re-activatie toe na soft-delete.
        # Een verwijderd record blokkeert niet het opnieuw toevoegen van dezelfde persoon.
        Index(
            "uq_lidmaatschap_actief",
            "gebruiker_id", "team_id",
            unique=True,
            postgresql_where=text("verwijderd_op IS NULL"),
        ),
        # Ledenlijst per team — hot path voor planningsgrid en teamoverzicht
        Index(
            "ix_lidmaatschappen_team_id",
            "team_id",
            postgresql_where=text("is_actief = TRUE AND verwijderd_op IS NULL"),
        ),
        # Alle actieve teams voor gebruiker X — dekt ook Rode Lijn (index-only scan)
        Index(
            "ix_lidmaatschappen_gebruiker_actief",
            "gebruiker_id", "team_id",
            postgresql_where=text("is_actief = TRUE AND verwijderd_op IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(
        String(36), unique=True, nullable=False,
        default=lambda: str(uuid_module.uuid4()),
    )
    gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_planner = Column(Boolean, default=False, nullable=False)
    type = Column(String(20), nullable=False, default=LidmaatschapType.vast.value)
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    gebruiker = relationship("Gebruiker", back_populates="lidmaatschappen")
    team = relationship("Team", back_populates="lidmaatschappen")
