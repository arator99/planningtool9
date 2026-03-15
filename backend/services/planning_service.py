import logging
from calendar import monthrange
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.planning import Planning, Shiftcode
from services.domein.planning_domein import (
    MAAND_NAMEN,
    bouw_dag_info,
    bereken_navigatie,
    groepeer_shiftcodes,
)

logger = logging.getLogger(__name__)


class PlanningService:
    """Planning operaties: maandgrid, shift UPSERT en publicatie."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_maandgrid(self, groep_id: int, jaar: int, maand: int) -> dict:
        """
        Bouw maandplanning als grid-structuur voor de template.

        Returns:
            dict met grid, datums, metadata en shiftcodes.
        """
        _, aantal_dagen = monthrange(jaar, maand)
        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

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
                Planning.datum >= datums[0],
                Planning.datum <= datums[-1],
            )
            .all()
        )
        shifts_idx = {(s.gebruiker_id, s.datum): s for s in shifts_db}

        grid = []
        for gebruiker in gebruikers:
            rij = {
                "id": gebruiker.id,
                "naam": gebruiker.volledige_naam or gebruiker.gebruikersnaam,
                "shifts": {},
            }
            for datum in datums:
                shift = shifts_idx.get((gebruiker.id, datum))
                rij["shifts"][datum.isoformat()] = {
                    "code": shift.shift_code if shift else None,
                    "status": shift.status if shift else "concept",
                }
            grid.append(rij)

        vorige, volgende = bereken_navigatie(jaar, maand)

        return {
            "grid": grid,
            "dag_info": bouw_dag_info(datums),
            "jaar": jaar,
            "maand": maand,
            "maand_naam": MAAND_NAMEN[maand],
            "is_gepubliceerd": self._is_gepubliceerd(groep_id, jaar, maand),
            "shiftcodes": self.haal_shiftcodes(groep_id),
            "shiftcodes_gegroepeerd": self.haal_shiftcodes_gegroepeerd(groep_id),
            "vorige": vorige,
            "volgende": volgende,
        }

    def haal_shiftcodes(self, groep_id: int) -> list[Shiftcode]:
        """Geeft alle shiftcodes voor de groep, gesorteerd op code."""
        return (
            self.db.query(Shiftcode)
            .filter(Shiftcode.groep_id == groep_id)
            .order_by(Shiftcode.code)
            .all()
        )

    def haal_shiftcodes_gegroepeerd(self, groep_id: int) -> list[dict]:
        """
        Geeft shiftcodes gegroepeerd per shift_type categorie.

        Returns:
            Lijst van dicts met naam, kleur_bg, kleur_header en codes.
        """
        codes = (
            self.db.query(Shiftcode)
            .filter(Shiftcode.groep_id == groep_id)
            .order_by(Shiftcode.code)
            .all()
        )
        return groepeer_shiftcodes(codes)

    def sla_shift_op(
        self,
        gebruiker_id: int,
        groep_id: int,
        datum: date,
        shift_code: Optional[str],
    ) -> Planning:
        """
        UPSERT een planning shift.

        Raises:
            ValueError: Als gebruiker niet tot de groep behoort.
        """
        if not self.db.query(Gebruiker).filter(
            Gebruiker.id == gebruiker_id, Gebruiker.groep_id == groep_id
        ).first():
            raise ValueError(f"Gebruiker {gebruiker_id} niet gevonden in groep")

        code = shift_code.strip().upper() if shift_code and shift_code.strip() else None

        shift = (
            self.db.query(Planning)
            .filter(Planning.gebruiker_id == gebruiker_id, Planning.datum == datum)
            .first()
        )
        if shift:
            shift.shift_code = code
        else:
            shift = Planning(
                gebruiker_id=gebruiker_id,
                groep_id=groep_id,
                datum=datum,
                shift_code=code,
                status="concept",
            )
            self.db.add(shift)

        self.db.commit()
        self.db.refresh(shift)
        return shift

    def verwijder_shift(self, gebruiker_id: int, groep_id: int, datum: date) -> None:
        """Verwijder een shift."""
        shift = (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.groep_id == groep_id,
                Planning.datum == datum,
            )
            .first()
        )
        if shift:
            self.db.delete(shift)
            self.db.commit()

    def publiceer_maand(self, groep_id: int, jaar: int, maand: int) -> int:
        """
        Publiceert alle concept shifts in een maand.

        Returns:
            Aantal gepubliceerde shifts.
        """
        _, aantal_dagen = monthrange(jaar, maand)
        start, eind = date(jaar, maand, 1), date(jaar, maand, aantal_dagen)

        shifts = (
            self.db.query(Planning)
            .filter(
                Planning.groep_id == groep_id,
                Planning.datum >= start,
                Planning.datum <= eind,
                Planning.status == "concept",
                Planning.shift_code.isnot(None),
            )
            .all()
        )
        for shift in shifts:
            shift.status = "gepubliceerd"
        self.db.commit()
        logger.info("Maand %d-%02d gepubliceerd: %d shifts", jaar, maand, len(shifts))
        return len(shifts)

    def zet_terug_naar_concept(self, groep_id: int, jaar: int, maand: int) -> int:
        """
        Zet alle gepubliceerde shifts terug naar concept.

        Returns:
            Aantal teruggezette shifts.
        """
        _, aantal_dagen = monthrange(jaar, maand)
        start, eind = date(jaar, maand, 1), date(jaar, maand, aantal_dagen)

        shifts = (
            self.db.query(Planning)
            .filter(
                Planning.groep_id == groep_id,
                Planning.datum >= start,
                Planning.datum <= eind,
                Planning.status == "gepubliceerd",
            )
            .all()
        )
        for shift in shifts:
            shift.status = "concept"
        self.db.commit()
        logger.info("Maand %d-%02d naar concept: %d shifts", jaar, maand, len(shifts))
        return len(shifts)

    def haal_eigen_planning(self, gebruiker_id: int, groep_id: int, jaar: int, maand: int) -> dict:
        """
        Bouw maandoverzicht van gepubliceerde shifts voor één gebruiker.

        Returns:
            dict met shifts (datum → code), dag_info, navigatie en metadata.
        """
        _, aantal_dagen = monthrange(jaar, maand)
        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

        shifts_db = (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.groep_id == groep_id,
                Planning.datum >= datums[0],
                Planning.datum <= datums[-1],
                Planning.status == "gepubliceerd",
                Planning.shift_code.isnot(None),
            )
            .all()
        )
        shifts_idx = {s.datum.isoformat(): s.shift_code for s in shifts_db}

        vorige, volgende = bereken_navigatie(jaar, maand)

        return {
            "shifts": shifts_idx,
            "dag_info": bouw_dag_info(datums),
            "jaar": jaar,
            "maand": maand,
            "maand_naam": MAAND_NAMEN[maand],
            "vorige": vorige,
            "volgende": volgende,
        }

    def haal_komende_shifts(self, gebruiker_id: int, groep_id: int, aantal_dagen: int = 7) -> list[Planning]:
        """Gepubliceerde shifts voor de komende N dagen (vanaf morgen)."""
        vandaag = date.today()
        tot = vandaag + timedelta(days=aantal_dagen)
        return (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.groep_id == groep_id,
                Planning.datum >= vandaag,
                Planning.datum <= tot,
                Planning.is_gepubliceerd == True,
            )
            .order_by(Planning.datum)
            .all()
        )

    def _is_gepubliceerd(self, groep_id: int, jaar: int, maand: int) -> bool:
        _, aantal_dagen = monthrange(jaar, maand)
        start, eind = date(jaar, maand, 1), date(jaar, maand, aantal_dagen)

        totaal = self.db.query(Planning).filter(
            Planning.groep_id == groep_id,
            Planning.datum >= start,
            Planning.datum <= eind,
            Planning.shift_code.isnot(None),
        ).count()

        if totaal == 0:
            return False

        concept = self.db.query(Planning).filter(
            Planning.groep_id == groep_id,
            Planning.datum >= start,
            Planning.datum <= eind,
            Planning.shift_code.isnot(None),
            Planning.status == "concept",
        ).count()

        return concept == 0
