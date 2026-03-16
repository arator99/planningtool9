"""Notitie model — berichten tussen gebruikers en planners per team."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Basis

PRIORITEITEN = ("laag", "normaal", "hoog")


class Notitie(Basis):
    """
    Bericht/notitie — kan gericht zijn aan een individuele gebruiker OF aan een team-mailbox.

    Logica:
      naar_gebruiker_id is ingevuld → persoonlijk bericht
      naar_gebruiker_id is NULL     → team-mailbox bericht (zichtbaar voor alle planners van team_id)
    """

    __tablename__ = "notities"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    van_gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False
    )
    naar_gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    planning_datum = Column(Date, nullable=True, index=True)
    bericht = Column(Text, nullable=False)
    is_gelezen = Column(Boolean, default=False, nullable=False)
    prioriteit = Column(
        SAEnum(*PRIORITEITEN, name="notitie_prioriteit"), default="normaal", nullable=False
    )
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    gelezen_op = Column(DateTime, nullable=True)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    van_gebruiker = relationship(
        "Gebruiker", back_populates="verzonden_notities", foreign_keys=[van_gebruiker_id]
    )
    naar_gebruiker = relationship(
        "Gebruiker", back_populates="ontvangen_notities", foreign_keys=[naar_gebruiker_id]
    )
