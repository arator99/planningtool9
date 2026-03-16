"""Shiftcode service — CRUD voor shiftcodes en werkposten."""
import logging
from typing import Optional

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

    def haal_werkposten(self, locatie_id: int) -> list[Werkpost]:
        return (
            self.db.query(Werkpost)
            .filter(Werkpost.locatie_id == locatie_id, Werkpost.is_actief == True)
            .order_by(Werkpost.naam)
            .all()
        )

    # ------------------------------------------------------------------ #
    # Shiftcodes lezen                                                     #
    # ------------------------------------------------------------------ #

    def haal_alle(self, locatie_id: int) -> list[Shiftcode]:
        """Geeft alle shiftcodes voor de locatie inclusief nationale codes (locatie_id IS NULL)."""
        return (
            self.db.query(Shiftcode)
            .filter(
                (Shiftcode.locatie_id == locatie_id) | (Shiftcode.locatie_id.is_(None))
            )
            .order_by(Shiftcode.shift_type, Shiftcode.code)
            .all()
        )

    def haal_op_id(self, shiftcode_id: int, locatie_id: int) -> Shiftcode | None:
        return (
            self.db.query(Shiftcode)
            .filter(
                Shiftcode.id == shiftcode_id,
                (Shiftcode.locatie_id == locatie_id) | (Shiftcode.locatie_id.is_(None)),
            )
            .first()
        )

    def haal_op_uuid(self, uuid: str) -> Shiftcode:
        """Zoek een shiftcode op extern uuid. Gooit ValueError als niet gevonden."""
        obj = self.db.query(Shiftcode).filter(Shiftcode.uuid == uuid).first()
        if not obj:
            raise ValueError(f"Shiftcode niet gevonden: {uuid}")
        return obj

    # ------------------------------------------------------------------ #
    # Aanmaken                                                             #
    # ------------------------------------------------------------------ #

    def maak_aan(
        self,
        locatie_id: int,
        code: str,
        shift_type: Optional[str],
        dag_type: Optional[str],
        start_uur: Optional[str],
        eind_uur: Optional[str],
        werkpost_id: Optional[int],
        is_kritisch: bool,
        telt_als_werkdag: bool = True,
        is_nachtprestatie: bool = False,
        reset_nacht: bool = False,
    ) -> Shiftcode:
        code = normaliseer_shiftcode(code)
        if not code:
            raise ValueError("Code mag niet leeg zijn.")
        bestaand = self.db.query(Shiftcode).filter(
            Shiftcode.locatie_id == locatie_id, Shiftcode.code == code
        ).first()
        if bestaand:
            raise ValueError(f"Code '{code}' bestaat al.")

        sc = Shiftcode(
            locatie_id=locatie_id,
            code=code,
            shift_type=shift_type or None,
            dag_type=dag_type or None,
            start_uur=start_uur or None,
            eind_uur=eind_uur or None,
            werkpost_id=werkpost_id or None,
            is_kritisch=is_kritisch,
            telt_als_werkdag=telt_als_werkdag,
            is_nachtprestatie=is_nachtprestatie,
            reset_nacht=reset_nacht,
        )
        self.db.add(sc)
        self.db.commit()
        self.db.refresh(sc)
        logger.info("Shiftcode aangemaakt: %s (locatie %s)", code, locatie_id)
        return sc

    # ------------------------------------------------------------------ #
    # Bewerken                                                             #
    # ------------------------------------------------------------------ #

    def bewerk(
        self,
        shiftcode_id: int,
        locatie_id: int,
        shift_type: Optional[str],
        dag_type: Optional[str],
        start_uur: Optional[str],
        eind_uur: Optional[str],
        werkpost_id: Optional[int],
        is_kritisch: bool,
        telt_als_werkdag: bool = True,
        is_nachtprestatie: bool = False,
        reset_nacht: bool = False,
    ) -> Shiftcode:
        sc = self._haal_of_fout(shiftcode_id, locatie_id)
        sc.shift_type = shift_type or None
        sc.dag_type = dag_type or None
        sc.start_uur = start_uur or None
        sc.eind_uur = eind_uur or None
        sc.werkpost_id = werkpost_id or None
        sc.is_kritisch = is_kritisch
        sc.telt_als_werkdag = telt_als_werkdag
        sc.is_nachtprestatie = is_nachtprestatie
        sc.reset_nacht = reset_nacht
        self.db.commit()
        logger.info("Shiftcode %s bijgewerkt", sc.code)
        return sc

    # ------------------------------------------------------------------ #
    # Verwijderen                                                          #
    # ------------------------------------------------------------------ #

    def verwijder(self, shiftcode_id: int, locatie_id: int) -> None:
        sc = self._haal_of_fout(shiftcode_id, locatie_id)
        self.db.delete(sc)
        self.db.commit()
        logger.info("Shiftcode %s verwijderd", sc.code)

    # ------------------------------------------------------------------ #
    # Intern                                                               #
    # ------------------------------------------------------------------ #

    def _haal_of_fout(self, shiftcode_id: int, locatie_id: int) -> Shiftcode:
        sc = self.haal_op_id(shiftcode_id, locatie_id)
        if not sc:
            raise ValueError("Shiftcode niet gevonden.")
        return sc
