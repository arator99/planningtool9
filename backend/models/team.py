"""Team model — planningseenheid binnen een locatie (was 'Groep' in v0.8)."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from database import Basis


class Team(Basis):
    """Planningsteam — de eenheid waarop planningen, shiftcodes en HR-regels betrekking hebben."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    naam = Column(String(100), nullable=False)
    code = Column(String(20), nullable=False)                 # bijv. "PAT", "TO"
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=False, index=True)
    beschrijving = Column(String(255), nullable=True)
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    locatie = relationship("Locatie")
    config = relationship("TeamConfig", back_populates="team", uselist=False, cascade="all, delete-orphan")


class TeamConfig(Basis):
    """Configuratie per team — standaardinstellingen."""

    __tablename__ = "team_configs"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False)
    standaard_taal = Column(String(5), default="nl", nullable=False)

    # Relatie
    team = relationship("Team", back_populates="config")
