"""
Suggestie service — shift-assistent voor de planner.

Vindt gescoorde shiftcode-suggesties voor een specifieke gebruiker/datum
op basis van historiek en shift-voorkeuren. HR-validatie na toepassing
via de bestaande ValidatieService + "Valideer" knop in het planning grid.
"""
import logging
from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.planning import Planning, Shiftcode
from models.verlof import VerlofAanvraag
from services.domein.suggestie_domein import (
    HISTORIEK_LOOKBACK_DAGEN,
    ShiftcodeSuggestie,
    bouw_historiek_per_weekdag,
    parseer_shift_voorkeuren,
    scoreer_shiftcode,
    suggereer_voor_weekdag,
)

logger = logging.getLogger(__name__)

# Rust/verlof/standby codes worden nooit als werkshift gesuggereerd
_NIET_SUGGEREREN: frozenset[str] = frozenset({
    "RX", "RXW", "RXF", "CXW", "CXA", "CX",
    "V", "VV", "VP", "KD", "ADV", "Z", "DA", "R", "RUST",
    "T", "WACHT", "STANDBY", "W",
})


class SuggestieService:
    """
    Shift-assistent: gescoorde shiftcode-suggesties per gebruiker/datum.

    Methodiek:
    1. Beschikbaarheidsfilter — geen verlof, geen bestaande shift
    2. Scoring — historiek (90 dagen) + shift-voorkeur uit gebruikersprofiel
    3. Sorteer — hoogste score eerst
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Publieke methodes                                                   #
    # ------------------------------------------------------------------ #

    def haal_shiftcode_suggesties(
        self,
        groep_id: int,
        gebruiker_id: int,
        datum: date,
    ) -> list[ShiftcodeSuggestie]:
        """
        Geef top-10 gescoorde shiftcode-suggesties voor een gebruiker op een datum.

        Retourneert lege lijst als:
        - gebruiker_id niet tot groep_id behoort
        - gebruiker al een shift heeft op die datum
        - gebruiker goedgekeurd verlof heeft op die datum

        Args:
            groep_id: Groep van de ingelogde planner.
            gebruiker_id: ID van de te plannen medewerker.
            datum: De doeldatum.
        """
        geb = self.db.query(Gebruiker).filter(
            Gebruiker.id == gebruiker_id,
            Gebruiker.groep_id == groep_id,
            Gebruiker.is_actief == True,
        ).first()
        if not geb:
            return []

        # Al een shift ingepland?
        bestaand = self.db.query(Planning).filter(
            Planning.gebruiker_id == gebruiker_id,
            Planning.datum == datum,
            Planning.groep_id == groep_id,
        ).first()
        if bestaand and bestaand.shift_code:
            return []

        # Goedgekeurd verlof?
        if self._heeft_verlof(gebruiker_id, groep_id, datum):
            return []

        # Actieve shiftcodes voor de groep (geen rust/verlof codes)
        shiftcodes = [
            sc for sc in self.db.query(Shiftcode)
            .filter(Shiftcode.groep_id == groep_id)
            .order_by(Shiftcode.code)
            .all()
            if sc.code.upper() not in _NIET_SUGGEREREN
        ]
        if not shiftcodes:
            return []

        # Historiek: recente shifts van deze gebruiker
        hist_start = datum - timedelta(days=HISTORIEK_LOOKBACK_DAGEN)
        historiek_codes = [
            rec.shift_code
            for rec in self.db.query(Planning).filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.groep_id == groep_id,
                Planning.datum >= hist_start,
                Planning.datum < datum,
            ).all()
        ]

        # Shift-voorkeuren uit profiel
        voorkeuren = parseer_shift_voorkeuren(geb.shift_voorkeuren)

        # Scoreer alle beschikbare shiftcodes
        suggesties = [
            scoreer_shiftcode(
                shiftcode=sc.code,
                shift_type=sc.shift_type,
                historiek=historiek_codes,
                voorkeuren=voorkeuren,
            )
            for sc in shiftcodes
        ]

        # Sorteer: hoogste score eerst; bij gelijke score: alfabetisch op code
        suggesties.sort(key=lambda s: (-s.score, s.shiftcode))
        return suggesties[:10]

    def auto_invullen(
        self,
        groep_id: int,
        gebruiker_id: int,
        datum: date,
    ) -> str | None:
        """
        Pas de beste suggestie toe voor een gebruiker/datum.

        Returns:
            De toegepaste shiftcode, of None als geen suggestie beschikbaar.
        """
        suggesties = self.haal_shiftcode_suggesties(groep_id, gebruiker_id, datum)
        if not suggesties:
            return None

        beste = suggesties[0]
        from services.planning_service import PlanningService
        PlanningService(self.db).sla_shift_op(
            gebruiker_id, groep_id, datum, beste.shiftcode
        )
        logger.debug(
            "Auto-invullen: gebruiker %s op %s → %s (score %.1f)",
            gebruiker_id, datum, beste.shiftcode, beste.score,
        )
        return beste.shiftcode

    def batch_auto_invullen(
        self,
        groep_id: int,
        jaar: int,
        maand: int,
    ) -> int:
        """
        Vul alle lege cellen in de maand in op basis van historiek per weekdag.

        Strategie: meest voorkomende werkshiftcode per weekdag in de afgelopen
        90 dagen. Slaat cellen over als de gebruiker verlof heeft.

        Returns:
            Aantal ingevulde cellen.
        """
        _, aantal_dagen = monthrange(jaar, maand)
        start = date(jaar, maand, 1)
        eind = date(jaar, maand, aantal_dagen)

        gebruikers = (
            self.db.query(Gebruiker)
            .filter(Gebruiker.groep_id == groep_id, Gebruiker.is_actief == True)
            .all()
        )

        # Index al bestaande shifts (met code) — om overwriting te vermijden
        bestaand_idx: set[tuple[int, date]] = {
            (s.gebruiker_id, s.datum)
            for s in self.db.query(Planning).filter(
                Planning.groep_id == groep_id,
                Planning.datum >= start,
                Planning.datum <= eind,
                Planning.shift_code.isnot(None),
            ).all()
        }

        # Historiek: 90 dagen voor de maand
        hist_start = start - timedelta(days=HISTORIEK_LOOKBACK_DAGEN)
        hist_records = (
            self.db.query(Planning)
            .filter(
                Planning.groep_id == groep_id,
                Planning.datum >= hist_start,
                Planning.datum < start,
                Planning.shift_code.isnot(None),
            )
            .all()
        )

        # Per gebruiker: historiek per weekdag
        hist_per_user: dict[int, dict[int, list[str | None]]] = {}
        for rec in hist_records:
            if rec.shift_code and rec.shift_code.upper() not in _NIET_SUGGEREREN:
                hist_per_user.setdefault(rec.gebruiker_id, {})
                weekdag = rec.datum.weekday()
                hist_per_user[rec.gebruiker_id].setdefault(weekdag, []).append(
                    rec.shift_code
                )

        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

        from services.planning_service import PlanningService
        planning_svc = PlanningService(self.db)
        toegepast = 0

        for g in gebruikers:
            weekdag_hist = hist_per_user.get(g.id, {})
            if not weekdag_hist:
                continue  # Geen bruikbare historiek

            for datum in datums:
                if (g.id, datum) in bestaand_idx:
                    continue  # Al ingevuld
                if self._heeft_verlof(g.id, groep_id, datum):
                    continue  # Verlof

                beste_code = suggereer_voor_weekdag(datum.weekday(), weekdag_hist)
                if not beste_code:
                    continue

                try:
                    planning_svc.sla_shift_op(g.id, groep_id, datum, beste_code)
                    bestaand_idx.add((g.id, datum))
                    toegepast += 1
                except ValueError as fout:
                    logger.debug("Batch skip %s/%s: %s", g.id, datum, fout)

        logger.info(
            "Batch auto-invullen groep %s %s-%02d: %d cellen ingevuld",
            groep_id, jaar, maand, toegepast,
        )
        return toegepast

    # ------------------------------------------------------------------ #
    # Privé hulpfuncties                                                  #
    # ------------------------------------------------------------------ #

    def _heeft_verlof(self, gebruiker_id: int, groep_id: int, datum: date) -> bool:
        """Check of de gebruiker goedgekeurd verlof heeft op de datum."""
        return self.db.query(VerlofAanvraag).filter(
            VerlofAanvraag.gebruiker_id == gebruiker_id,
            VerlofAanvraag.groep_id == groep_id,
            VerlofAanvraag.start_datum <= datum,
            VerlofAanvraag.eind_datum >= datum,
            VerlofAanvraag.status == "goedgekeurd",
        ).first() is not None
