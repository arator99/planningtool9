"""HR service — validatieregels en rode lijn beheer."""
import logging
from datetime import date

from sqlalchemy.orm import Session

from models.hr import HRRegel, RodeLijn
from services.domein.hr_domein import (
    ERNST_NIVEAUS,
    valideer_ernst_niveau,
    valideer_interval_dagen,
)

logger = logging.getLogger(__name__)


class HRService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # HR Regels                                                            #
    # ------------------------------------------------------------------ #

    def haal_alle_regels(self, groep_id: int) -> list[HRRegel]:
        return (
            self.db.query(HRRegel)
            .filter(HRRegel.groep_id == groep_id)
            .order_by(HRRegel.ernst_niveau, HRRegel.naam)
            .all()
        )

    def haal_regel(self, regel_id: int, groep_id: int) -> HRRegel | None:
        return (
            self.db.query(HRRegel)
            .filter(HRRegel.id == regel_id, HRRegel.groep_id == groep_id)
            .first()
        )

    def bewerk_regel(
        self,
        regel_id: int,
        groep_id: int,
        waarde: int | None,
        waarde_extra: str | None,
        ernst_niveau: str,
        is_actief: bool,
        beschrijving: str | None,
    ) -> HRRegel:
        regel = self._haal_of_fout(regel_id, groep_id)
        valideer_ernst_niveau(ernst_niveau)
        regel.waarde = waarde
        regel.waarde_extra = waarde_extra or None
        regel.ernst_niveau = ernst_niveau
        regel.is_actief = is_actief
        regel.beschrijving = beschrijving or None
        self.db.commit()
        logger.info("HR regel %s bijgewerkt", regel.code)
        return regel

    def activeer(self, regel_id: int, groep_id: int) -> HRRegel:
        regel = self._haal_of_fout(regel_id, groep_id)
        regel.is_actief = True
        self.db.commit()
        return regel

    def deactiveer(self, regel_id: int, groep_id: int) -> HRRegel:
        regel = self._haal_of_fout(regel_id, groep_id)
        regel.is_actief = False
        self.db.commit()
        return regel

    # ------------------------------------------------------------------ #
    # Rode Lijn                                                            #
    # ------------------------------------------------------------------ #

    def haal_rode_lijn(self, groep_id: int) -> RodeLijn | None:
        return (
            self.db.query(RodeLijn)
            .filter(RodeLijn.groep_id == groep_id, RodeLijn.is_actief == True)
            .first()
        )

    def sla_rode_lijn_op(
        self,
        groep_id: int,
        start_datum: date,
        interval_dagen: int,
    ) -> RodeLijn:
        valideer_interval_dagen(interval_dagen)
        rode_lijn = self.haal_rode_lijn(groep_id)
        if rode_lijn:
            rode_lijn.start_datum = start_datum
            rode_lijn.interval_dagen = interval_dagen
        else:
            rode_lijn = RodeLijn(
                groep_id=groep_id,
                start_datum=start_datum,
                interval_dagen=interval_dagen,
                is_actief=True,
            )
            self.db.add(rode_lijn)
        self.db.commit()
        self.db.refresh(rode_lijn)
        return rode_lijn

    # ------------------------------------------------------------------ #
    # Intern                                                               #
    # ------------------------------------------------------------------ #

    def _haal_of_fout(self, regel_id: int, groep_id: int) -> HRRegel:
        regel = self.haal_regel(regel_id, groep_id)
        if not regel:
            raise ValueError("HR regel niet gevonden.")
        return regel
