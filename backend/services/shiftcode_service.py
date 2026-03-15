"""Shiftcode service — CRUD voor shiftcodes en werkposten."""
import logging

from sqlalchemy.orm import Session

from models.planning import Shiftcode, Werkpost
from services.domein.shiftcode_domein import SHIFT_TYPES, DAG_TYPES, normaliseer_shiftcode

logger = logging.getLogger(__name__)


class ShiftcodeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Werkposten                                                           #
    # ------------------------------------------------------------------ #

    def haal_werkposten(self, groep_id: int) -> list[Werkpost]:
        return (
            self.db.query(Werkpost)
            .filter(Werkpost.groep_id == groep_id, Werkpost.is_actief == True)
            .order_by(Werkpost.naam)
            .all()
        )

    # ------------------------------------------------------------------ #
    # Shiftcodes lezen                                                     #
    # ------------------------------------------------------------------ #

    def haal_alle(self, groep_id: int) -> list[Shiftcode]:
        return (
            self.db.query(Shiftcode)
            .filter(Shiftcode.groep_id == groep_id)
            .order_by(Shiftcode.shift_type, Shiftcode.code)
            .all()
        )

    def haal_op_id(self, shiftcode_id: int, groep_id: int) -> Shiftcode | None:
        return (
            self.db.query(Shiftcode)
            .filter(Shiftcode.id == shiftcode_id, Shiftcode.groep_id == groep_id)
            .first()
        )

    # ------------------------------------------------------------------ #
    # Aanmaken                                                             #
    # ------------------------------------------------------------------ #

    def maak_aan(
        self,
        groep_id: int,
        code: str,
        shift_type: str | None,
        dag_type: str | None,
        start_uur: str | None,
        eind_uur: str | None,
        werkpost_id: int | None,
        is_kritisch: bool,
    ) -> Shiftcode:
        code = normaliseer_shiftcode(code)
        if not code:
            raise ValueError("Code mag niet leeg zijn.")
        bestaand = self.db.query(Shiftcode).filter(
            Shiftcode.groep_id == groep_id, Shiftcode.code == code
        ).first()
        if bestaand:
            raise ValueError(f"Code '{code}' bestaat al.")

        sc = Shiftcode(
            groep_id=groep_id,
            code=code,
            shift_type=shift_type or None,
            dag_type=dag_type or None,
            start_uur=start_uur or None,
            eind_uur=eind_uur or None,
            werkpost_id=werkpost_id or None,
            is_kritisch=is_kritisch,
        )
        self.db.add(sc)
        self.db.commit()
        self.db.refresh(sc)
        logger.info("Shiftcode aangemaakt: %s (groep %s)", code, groep_id)
        return sc

    # ------------------------------------------------------------------ #
    # Bewerken                                                             #
    # ------------------------------------------------------------------ #

    def bewerk(
        self,
        shiftcode_id: int,
        groep_id: int,
        shift_type: str | None,
        dag_type: str | None,
        start_uur: str | None,
        eind_uur: str | None,
        werkpost_id: int | None,
        is_kritisch: bool,
    ) -> Shiftcode:
        sc = self._haal_of_fout(shiftcode_id, groep_id)
        sc.shift_type = shift_type or None
        sc.dag_type = dag_type or None
        sc.start_uur = start_uur or None
        sc.eind_uur = eind_uur or None
        sc.werkpost_id = werkpost_id or None
        sc.is_kritisch = is_kritisch
        self.db.commit()
        logger.info("Shiftcode %s bijgewerkt", sc.code)
        return sc

    # ------------------------------------------------------------------ #
    # Verwijderen                                                          #
    # ------------------------------------------------------------------ #

    def verwijder(self, shiftcode_id: int, groep_id: int) -> None:
        sc = self._haal_of_fout(shiftcode_id, groep_id)
        self.db.delete(sc)
        self.db.commit()
        logger.info("Shiftcode %s verwijderd", sc.code)

    # ------------------------------------------------------------------ #
    # Intern                                                               #
    # ------------------------------------------------------------------ #

    def _haal_of_fout(self, shiftcode_id: int, groep_id: int) -> Shiftcode:
        sc = self.haal_op_id(shiftcode_id, groep_id)
        if not sc:
            raise ValueError("Shiftcode niet gevonden.")
        return sc
