"""SchermRecht model — DB overrides voor schermtoegang per locatie."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func

from database import Basis


class SchermRecht(Basis):
    """Toegangsoverride voor één route × rol × locatie-combinatie.

    Hybridregel: DB-override heeft prioriteit boven hardcoded default.
    Geen record aanwezig → default uit SCHERM_DEFAULTS geldt.
    """

    __tablename__ = "scherm_rechten"

    id = Column(Integer, primary_key=True, index=True)
    route_naam = Column(String(100), nullable=False, index=True)
    rol = Column(String(50), nullable=False)
    locatie_id = Column(Integer, ForeignKey("locaties.id"), nullable=True, index=True)
    toegestaan = Column(Boolean, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("route_naam", "rol", "locatie_id", name="uq_schermrecht_route_rol_locatie"),
    )
