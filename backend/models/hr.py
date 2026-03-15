from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Basis

ERNST_NIVEAUS = ("INFO", "WARNING", "CRITICAL")


class HRRegel(Basis):
    """Configureerbare HR-validatieregel per planningsgroep."""

    __tablename__ = "hr_regels"

    id = Column(Integer, primary_key=True, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # bijv. "MAX_DAGEN_RIJ"
    naam = Column(String(100), nullable=False)
    waarde = Column(Integer, nullable=True)                          # bijv. 7
    waarde_extra = Column(String(50), nullable=True)
    eenheid = Column(String(20), nullable=True)                      # 'dagen', 'uren', 'aantal'
    ernst_niveau = Column(String(20), default="WARNING", nullable=False)
    is_actief = Column(Boolean, default=True, nullable=False)
    beschrijving = Column(Text, nullable=True)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gewijzigd_op = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class RodeLijn(Basis):
    """Configuratie voor de rode lijn cyclus per planningsgroep."""

    __tablename__ = "rode_lijnen"

    id = Column(Integer, primary_key=True, index=True)
    groep_id = Column(Integer, ForeignKey("groepen.id"), nullable=False, index=True)
    start_datum = Column(Date, nullable=False, index=True)
    interval_dagen = Column(Integer, default=28, nullable=False)
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
