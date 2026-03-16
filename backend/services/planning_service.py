import logging
from calendar import monthrange
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol
from models.planning import Planning, Shiftcode
from models.team import Team
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

    def haal_maandgrid(self, team_id: int, jaar: int, maand: int) -> dict:
        """Bouw maandplanning als grid-structuur voor de template."""
        _, aantal_dagen = monthrange(jaar, maand)
        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

        locatie_id = self._locatie_van_team(team_id)

        gebruikers = (
            self.db.query(Gebruiker)
            .join(GebruikerRol, GebruikerRol.gebruiker_id == Gebruiker.id)
            .filter(
                GebruikerRol.rol.in_(["teamlid", "planner"]),
                GebruikerRol.scope_id == team_id,
                GebruikerRol.is_actief == True,
                Gebruiker.is_actief == True,
            )
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

        shifts_db = (
            self.db.query(Planning)
            .filter(
                Planning.team_id == team_id,
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
            "is_gepubliceerd": self._is_gepubliceerd(team_id, jaar, maand),
            "shiftcodes": self.haal_shiftcodes(locatie_id),
            "shiftcodes_gegroepeerd": self.haal_shiftcodes_gegroepeerd(locatie_id),
            "vorige": vorige,
            "volgende": volgende,
        }

    def haal_shiftcodes(self, locatie_id: int) -> list[Shiftcode]:
        """Geeft alle shiftcodes voor de locatie (inclusief nationale codes), gesorteerd op code."""
        return (
            self.db.query(Shiftcode)
            .filter(
                (Shiftcode.locatie_id == locatie_id) | (Shiftcode.locatie_id.is_(None))
            )
            .order_by(Shiftcode.code)
            .all()
        )

    def haal_shiftcodes_gegroepeerd(self, locatie_id: int) -> list[dict]:
        codes = (
            self.db.query(Shiftcode)
            .filter(
                (Shiftcode.locatie_id == locatie_id) | (Shiftcode.locatie_id.is_(None))
            )
            .order_by(Shiftcode.code)
            .all()
        )
        return groepeer_shiftcodes(codes)

    def sla_shift_op(
        self,
        gebruiker_id: int,
        team_id: int,
        datum: date,
        shift_code: Optional[str],
    ) -> Planning:
        """UPSERT een planning shift."""
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
                team_id=team_id,
                datum=datum,
                shift_code=code,
                status="concept",
            )
            self.db.add(shift)

        self.db.commit()
        self.db.refresh(shift)
        return shift

    def verwijder_shift(self, gebruiker_id: int, team_id: int, datum: date) -> None:
        shift = (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.team_id == team_id,
                Planning.datum == datum,
            )
            .first()
        )
        if shift:
            self.db.delete(shift)
            self.db.commit()

    def publiceer_maand(self, team_id: int, jaar: int, maand: int) -> int:
        _, aantal_dagen = monthrange(jaar, maand)
        start, eind = date(jaar, maand, 1), date(jaar, maand, aantal_dagen)

        shifts = (
            self.db.query(Planning)
            .filter(
                Planning.team_id == team_id,
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

    def zet_terug_naar_concept(self, team_id: int, jaar: int, maand: int) -> int:
        _, aantal_dagen = monthrange(jaar, maand)
        start, eind = date(jaar, maand, 1), date(jaar, maand, aantal_dagen)

        shifts = (
            self.db.query(Planning)
            .filter(
                Planning.team_id == team_id,
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

    def haal_eigen_planning(self, gebruiker_id: int, team_id: int, jaar: int, maand: int) -> dict:
        _, aantal_dagen = monthrange(jaar, maand)
        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

        shifts_db = (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.team_id == team_id,
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

    def haal_komende_shifts(self, gebruiker_id: int, team_id: int, aantal_dagen: int = 7) -> list[Planning]:
        """Gepubliceerde shifts voor de komende N dagen."""
        vandaag = date.today()
        tot = vandaag + timedelta(days=aantal_dagen)
        return (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.team_id == team_id,
                Planning.datum >= vandaag,
                Planning.datum <= tot,
                Planning.status == "gepubliceerd",
            )
            .order_by(Planning.datum)
            .all()
        )

    def _is_gepubliceerd(self, team_id: int, jaar: int, maand: int) -> bool:
        _, aantal_dagen = monthrange(jaar, maand)
        start, eind = date(jaar, maand, 1), date(jaar, maand, aantal_dagen)

        totaal = self.db.query(Planning).filter(
            Planning.team_id == team_id,
            Planning.datum >= start,
            Planning.datum <= eind,
            Planning.shift_code.isnot(None),
        ).count()

        if totaal == 0:
            return False

        concept = self.db.query(Planning).filter(
            Planning.team_id == team_id,
            Planning.datum >= start,
            Planning.datum <= eind,
            Planning.shift_code.isnot(None),
            Planning.status == "concept",
        ).count()

        return concept == 0

    def haal_maand_navigatie(self, jaar: int, maand: int) -> dict:
        """Geef navigatiedata (vorige/volgende maand + maandnaam) voor template-gebruik."""
        vorige, volgende = bereken_navigatie(jaar, maand)
        return {
            "vorige": vorige,
            "volgende": volgende,
            "maand_naam": MAAND_NAMEN[maand],
        }

    def _locatie_van_team(self, team_id: int) -> Optional[int]:
        """Hulpfunctie: geeft locatie_id van een team."""
        team = self.db.query(Team).filter(Team.id == team_id).first()
        return team.locatie_id if team else None
