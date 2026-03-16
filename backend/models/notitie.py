"""Notitie model — berichten tussen gebruikers, per rolmailbox of direct."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Basis

PRIORITEITEN = ("laag", "normaal", "hoog")

# Geldige mailbox-rolwaarden
MAILBOX_ROLLEN = ("planners", "beheerders", "super_beheerders")


class Notitie(Basis):
    """
    Bericht/notitie — kan gericht zijn aan:
      1. Een individuele gebruiker (naar_gebruiker_id ingevuld, naar_rol=None)
      2. Een rolmailbox (naar_rol ingevuld, naar_scope_id ingevuld, naar_gebruiker_id=None)

    Mailboxhiërarchie:
      teamlid      → naar_rol='planners',         naar_scope_id=team_id
      planner      → naar_rol='beheerders',        naar_scope_id=locatie_id
      beheerder    → naar_rol='super_beheerders',  naar_scope_id=nat_locatie_id

    Validatie van de 1-van-2 constraint gebeurt in de service, niet in de DB.
    """

    __tablename__ = "notities"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))

    # Tenant-isolatie — gedenormaliseerd voor directe filtering
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=True, index=True)

    van_gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False
    )

    # Bestemming: direct naar persoon
    naar_gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Bestemming: naar gedeelde rolmailbox
    # naar_rol: 'planners' | 'beheerders' | 'super_beheerders'
    naar_rol = Column(String(30), nullable=True, index=True)
    # naar_scope_id: team_id (planners) | locatie_id (beheerders/super_beheerders)
    naar_scope_id = Column(Integer, nullable=True, index=True)

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
