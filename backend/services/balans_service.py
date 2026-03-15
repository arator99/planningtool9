"""Balans service — berekent CXW/RXW/RXF compensatie balans per medewerker."""
import logging
from calendar import monthrange
from datetime import date

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.planning import Planning
from services.domein.balans_domein import (
    BalansResultaat,
    bereken_maand_schuld,
    bouw_balans_resultaat,
)

logger = logging.getLogger(__name__)


class BalansService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_team_balans(self, groep_id: int, jaar: int, maand: int) -> list[BalansResultaat]:
        """
        Bereken de CXW/RXW/RXF balans voor alle actieve medewerkers van de groep.

        Schuld = aantal zaterdagen / zondagen / Belgische feestdagen in de maand.
        Compensatie = aantal CXW / RXW / RXF codes in de planning van die maand.
        """
        _, aantal_dagen = monthrange(jaar, maand)
        start = date(jaar, maand, 1)
        eind = date(jaar, maand, aantal_dagen)

        gebruikers = (
            self.db.query(Gebruiker)
            .filter(Gebruiker.groep_id == groep_id, Gebruiker.is_actief == True)
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

        shifts_db = (
            self.db.query(Planning)
            .filter(
                Planning.groep_id == groep_id,
                Planning.datum >= start,
                Planning.datum <= eind,
            )
            .all()
        )

        # Index: gebruiker_id → lijst van shift_codes voor de maand
        shifts_idx: dict[int, list[str | None]] = {}
        for s in shifts_db:
            shifts_idx.setdefault(s.gebruiker_id, []).append(s.shift_code)

        zat_schuld, zon_schuld, feest_schuld = bereken_maand_schuld(jaar, maand)

        resultaten: list[BalansResultaat] = []
        for g in gebruikers:
            codes = shifts_idx.get(g.id, [])
            resultaten.append(
                bouw_balans_resultaat(
                    gebruiker_id=g.id,
                    gebruiker_naam=g.volledige_naam or g.gebruikersnaam,
                    zaterdag_schuld=zat_schuld,
                    zondag_schuld=zon_schuld,
                    feestdag_schuld=feest_schuld,
                    shift_codes=codes,
                )
            )

        logger.debug(
            "Balans berekend voor groep %s, %s-%02d: %d medewerkers",
            groep_id, jaar, maand, len(resultaten),
        )
        return resultaten
