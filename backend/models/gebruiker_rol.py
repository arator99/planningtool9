"""GebruikerRol model — administratieve rollen per gebruiker (beheerder, hr, super_beheerder)."""
import enum

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Enum,
    ForeignKey, Integer, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from database import Basis


class GebruikerRolType(str, enum.Enum):
    """Geldige administratieve rollen. Teamlidmaatschap zit in het Lidmaatschap model."""
    super_beheerder = "super_beheerder"
    beheerder = "beheerder"
    hr = "hr"


class GebruikerRol(Basis):
    """
    Administratieve rolkoppeling — uitsluitend voor beheerder, hr en super_beheerder.

    Teamlid- en planner-rechten zitten in Lidmaatschap, niet hier.

    Scope-regels:
      beheerder      → scope_locatie_id verplicht, scope_area_id NULL
      hr (area)      → scope_area_id ingevuld, scope_locatie_id NULL
      hr (nationaal) → beide NULL
      super_beheerder → beide NULL
    """

    __tablename__ = "gebruiker_rollen"
    __table_args__ = (
        UniqueConstraint("gebruiker_id", "rol", "scope_locatie_id", "scope_area_id",
                         name="uq_gebruiker_rol_scope"),
        # Voorkomt ongeldige scope-combinaties per rol
        CheckConstraint(
            "(rol = 'super_beheerder' AND scope_locatie_id IS NULL AND scope_area_id IS NULL)"
            " OR (rol = 'beheerder' AND scope_locatie_id IS NOT NULL AND scope_area_id IS NULL)"
            " OR (rol = 'hr' AND scope_locatie_id IS NULL)",
            name="chk_scope_combinatie",
        ),
        # Voorkomt stale rollen na migratie
        CheckConstraint(
            "rol IN ('super_beheerder', 'beheerder', 'hr')",
            name="chk_rol_geldig",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    gebruiker_id = Column(
        Integer, ForeignKey("gebruikers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    rol = Column(Enum(GebruikerRolType), nullable=False, index=True)

    # Getypeerde scope-FK's — vervangt het polymorfische scope_id veld
    scope_locatie_id = Column(
        Integer, ForeignKey("locaties.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    scope_area_id = Column(
        Integer, ForeignKey("areas.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )

    is_actief = Column(Boolean, default=True, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    verwijderd_op = Column(DateTime, nullable=True)
    verwijderd_door_id = Column(Integer, nullable=True)

    # Relaties
    gebruiker = relationship("Gebruiker", back_populates="rollen")
