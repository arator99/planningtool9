"""HR modellen — twee-laagse validatieregels (Fase 2)."""
import uuid as uuid_module

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from database import Basis

ERNST_NIVEAUS = ("INFO", "WARNING", "CRITICAL")
RICHTINGEN = ("max", "min")


class NationaleHRRegel(Basis):
    """
    Nationale HR-validatieregel, beheerd door super_beheerder.

    richting="max": lagere waarde = strenger (bv. MAX_DAGEN_OP_RIJ: 5 is strenger dan 7).
    richting="min": hogere waarde = strenger (bv. MIN_RUSTTIJD: 12 is strenger dan 11).

    Een lokale override mag ALLEEN strenger zijn dan de nationale waarde.
    """

    __tablename__ = "nationale_hr_regels"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_module.uuid4()))
    code = Column(String(50), unique=True, nullable=False, index=True)
    naam = Column(String(100), nullable=False)
    waarde = Column(Integer, nullable=False)
    eenheid = Column(String(20), nullable=True)          # 'dagen', 'uren', 'aantal'
    ernst_niveau = Column(String(20), default="WARNING", nullable=False)
    richting = Column(String(3), default="max", nullable=False)  # 'max' | 'min'
    beschrijving = Column(Text, nullable=True)
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gewijzigd_op = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class LocatieHROverride(Basis):
    """
    Locatie-specifieke override op een nationale HR-regel.

    Constraint (afgedwongen in service):
    - richting="max" → override.waarde <= nationale.waarde
    - richting="min" → override.waarde >= nationale.waarde
    """

    __tablename__ = "locatie_hr_overrides"

    id = Column(Integer, primary_key=True, index=True)
    nationale_regel_id = Column(Integer, ForeignKey("nationale_hr_regels.id"), nullable=False, index=True)
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=False, index=True)
    waarde = Column(Integer, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gewijzigd_op = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("nationale_regel_id", "locatie_id", name="uq_override_regel_locatie"),
    )
