from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database import Basis

# Toegestane instellingssleutels (whitelist)
INSTELLING_SLEUTELS = {
    "planning.valideer_bij_opslaan": {"label": "instelling.planning_valideer", "type": "bool", "standaard": "0"},
    "planning.auto_publiceer": {"label": "instelling.planning_auto_publiceer", "type": "bool", "standaard": "0"},
}


class AppInstelling(Basis):
    """Groep-specifieke app-instellingen als key-value paren."""

    __tablename__ = "app_instellingen"
    __table_args__ = (UniqueConstraint("groep_id", "sleutel", name="uq_instelling_groep_sleutel"),)

    id = Column(Integer, primary_key=True, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=False, index=True)
    sleutel = Column(String(100), nullable=False)
    waarde = Column(String(500), nullable=False, default="")
    bijgewerkt_op = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    bijgewerkt_door = Column(Integer, ForeignKey("gebruikers.id"), nullable=True)

    bijgewerkt_door_gebruiker = relationship("Gebruiker", foreign_keys=[bijgewerkt_door])
