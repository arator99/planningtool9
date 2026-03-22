"""GebruikerRol model — meervoudige, scopegebonden rollen per gebruiker."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database import Basis

# Alle geldige rollen in volgorde van toenemende rechten
ROLLEN = ("teamlid", "planner", "hr", "beheerder", "super_beheerder")

# scope_id interpretatie per rol:
#   teamlid / planner  → scope_id = team_id
#   hr / beheerder     → scope_id = locatie_id
#   super_beheerder    → scope_id = id van Locatie(code='NAT')


class GebruikerRol(Basis):
    """
    Rolkoppeling — één record per gebruiker per rol per scope.

    Uniekheidsconstraint: (gebruiker_id, rol, scope_id) mag niet herhaald worden.
    Een gebruiker kan wél meerdere rollen hebben: bijv. planner(PAT) + teamlid(TO).
    """

    __tablename__ = "gebruiker_rollen"
    __table_args__ = (
        UniqueConstraint("gebruiker_id", "rol", "scope_id", name="uq_gebruiker_rol_scope"),
    )

    id = Column(Integer, primary_key=True, index=True)
    gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rol = Column(String(20), nullable=False, index=True)

    # Polymorfische FK — geen DB-constraint, interpretatie hangt af van `rol`:
    #   teamlid/planner      → team_id
    #   beheerder/hr         → locatie_id
    #   super_beheerder      → locatie_id van Locatie(code='NAT')
    scope_id = Column(Integer, nullable=False, index=True)

    # is_reserve enkel relevant bij rol=teamlid
    is_reserve = Column(Boolean, default=False, nullable=False)
    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relatie
    gebruiker = relationship("Gebruiker", back_populates="rollen")
