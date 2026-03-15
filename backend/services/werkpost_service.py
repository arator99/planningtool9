"""Werkpost service — CRUD voor werkposten."""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models.planning import Werkpost

logger = logging.getLogger(__name__)


class WerkpostService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Lezen                                                                #
    # ------------------------------------------------------------------ #

    def haal_alle(self, groep_id: int, ook_inactief: bool = False) -> list[Werkpost]:
        q = self.db.query(Werkpost).filter(Werkpost.groep_id == groep_id)
        if not ook_inactief:
            q = q.filter(Werkpost.is_actief == True)
        return q.order_by(Werkpost.naam).all()

    def haal_op_id(self, werkpost_id: int, groep_id: int) -> Werkpost | None:
        return (
            self.db.query(Werkpost)
            .filter(Werkpost.id == werkpost_id, Werkpost.groep_id == groep_id)
            .first()
        )

    # ------------------------------------------------------------------ #
    # Aanmaken                                                             #
    # ------------------------------------------------------------------ #

    def maak_aan(
        self,
        groep_id: int,
        naam: str,
        beschrijving: str | None,
        telt_als_werkdag: bool,
        reset_12u_rust: bool,
        breekt_werk_reeks: bool,
    ) -> Werkpost:
        naam = naam.strip()
        if not naam:
            raise ValueError("Naam is verplicht.")
        bestaand = self.db.query(Werkpost).filter(
            Werkpost.groep_id == groep_id, Werkpost.naam == naam
        ).first()
        if bestaand:
            raise ValueError(f"Werkpost '{naam}' bestaat al.")

        wp = Werkpost(
            groep_id=groep_id,
            naam=naam,
            beschrijving=beschrijving or None,
            telt_als_werkdag=telt_als_werkdag,
            reset_12u_rust=reset_12u_rust,
            breekt_werk_reeks=breekt_werk_reeks,
        )
        self.db.add(wp)
        self.db.commit()
        self.db.refresh(wp)
        logger.info("Werkpost aangemaakt: %s (groep %s)", naam, groep_id)
        return wp

    # ------------------------------------------------------------------ #
    # Bewerken                                                             #
    # ------------------------------------------------------------------ #

    def bewerk(
        self,
        werkpost_id: int,
        groep_id: int,
        naam: str,
        beschrijving: str | None,
        telt_als_werkdag: bool,
        reset_12u_rust: bool,
        breekt_werk_reeks: bool,
    ) -> Werkpost:
        wp = self._haal_of_fout(werkpost_id, groep_id)
        naam = naam.strip()
        if not naam:
            raise ValueError("Naam is verplicht.")
        conflict = self.db.query(Werkpost).filter(
            Werkpost.groep_id == groep_id,
            Werkpost.naam == naam,
            Werkpost.id != werkpost_id,
        ).first()
        if conflict:
            raise ValueError(f"Werkpost '{naam}' bestaat al.")
        wp.naam = naam
        wp.beschrijving = beschrijving or None
        wp.telt_als_werkdag = telt_als_werkdag
        wp.reset_12u_rust = reset_12u_rust
        wp.breekt_werk_reeks = breekt_werk_reeks
        self.db.commit()
        logger.info("Werkpost %s bijgewerkt", wp.naam)
        return wp

    # ------------------------------------------------------------------ #
    # Deactiveren                                                          #
    # ------------------------------------------------------------------ #

    def deactiveer(self, werkpost_id: int, groep_id: int) -> None:
        wp = self._haal_of_fout(werkpost_id, groep_id)
        if not wp.is_actief:
            raise ValueError("Werkpost is al inactief.")
        wp.is_actief = False
        wp.gedeactiveerd_op = datetime.now()
        self.db.commit()
        logger.info("Werkpost %s gedeactiveerd", wp.naam)

    def activeer(self, werkpost_id: int, groep_id: int) -> None:
        wp = self._haal_of_fout(werkpost_id, groep_id)
        wp.is_actief = True
        wp.gedeactiveerd_op = None
        self.db.commit()
        logger.info("Werkpost %s geactiveerd", wp.naam)

    # ------------------------------------------------------------------ #
    # Intern                                                               #
    # ------------------------------------------------------------------ #

    def _haal_of_fout(self, werkpost_id: int, groep_id: int) -> Werkpost:
        wp = self.haal_op_id(werkpost_id, groep_id)
        if not wp:
            raise ValueError("Werkpost niet gevonden.")
        return wp
