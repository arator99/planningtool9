"""ADV-toekenning model — arbeidsduurverkorting patronen per gebruiker (Fase 8)."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from database import Basis

ADV_TYPES = ("dag_per_week", "week_per_5_weken")


class AdvToekenning(Basis):
    """
    ADV-toekenning — definitie van het ADV-patroon voor één medewerker.

    Twee types:
    - 'dag_per_week': Elke week dezelfde dag (ma–vr) ADV.
    - 'week_per_5_weken': Elke 5 weken een volledige werkweek (ma–vr) ADV.

    De individuele ADV-dagen worden runtime berekend via adv_domein.genereer_adv_dagen().
    """

    __tablename__ = "adv_toekenningen"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    gebruiker_id = Column(Integer, ForeignKey("gebruikers.id"), nullable=False, index=True)
    adv_type = Column(String(20), nullable=False)           # 'dag_per_week' | 'week_per_5_weken'
    dag_van_week = Column(Integer, nullable=True)           # 0–4 (alleen bij dag_per_week)
    start_datum = Column(Date, nullable=False)
    eind_datum = Column(Date, nullable=True)                # None = onbeperkt
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_door_id = Column(Integer, ForeignKey("gebruikers.id"), nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gewijzigd_op = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Soft delete
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    gebruiker = relationship("Gebruiker", foreign_keys=[gebruiker_id])
    aangemaakt_door = relationship("Gebruiker", foreign_keys=[aangemaakt_door_id])
