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

    def haal_maandgrid(
        self,
        primair_team_id: int,
        jaar: int,
        maand: int,
        filter_team_id: Optional[int] = None,
    ) -> dict:
        """Bouw maandplanning als grid-structuur voor de template.

        Args:
            primair_team_id: Het primaire team van de ingelogde gebruiker (voor locatie-context).
            jaar: Het jaar van het overzicht.
            maand: De maand van het overzicht (1–12).
            filter_team_id: Als opgegeven, toon enkel dit team. Anders alle teams van de locatie.
        """
        _, aantal_dagen = monthrange(jaar, maand)
        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

        locatie_id = self._locatie_van_team(primair_team_id)

        # Bepaal welke team-IDs mee in het grid komen
        if filter_team_id is not None:
            actieve_team_ids = [filter_team_id]
        else:
            teams = (
                self.db.query(Team)
                .filter(Team.locatie_id == locatie_id, Team.is_actief == True)
                .all()
            )
            actieve_team_ids = [t.id for t in teams]

        gebruikers = (
            self.db.query(Gebruiker)
            .join(GebruikerRol, GebruikerRol.gebruiker_id == Gebruiker.id)
            .filter(
                GebruikerRol.rol.in_(["teamlid", "planner"]),
                GebruikerRol.scope_id.in_(actieve_team_ids),
                GebruikerRol.is_actief == True,
                Gebruiker.is_actief == True,
            )
            .order_by(Gebruiker.volledige_naam)
            .distinct()
            .all()
        )

        # Shifts: user-based query — shifts volgen de medewerker, niet het team
        actieve_gebruiker_ids = [g.id for g in gebruikers]
        shifts_db = (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id.in_(actieve_gebruiker_ids),
                Planning.datum >= datums[0],
                Planning.datum <= datums[-1],
            )
            .all()
        ) if actieve_gebruiker_ids else []
        shifts_idx = {(s.gebruiker_id, s.datum): s for s in shifts_db}

        grid = []
        for gebruiker in gebruikers:
            rij = {
                "id": gebruiker.id,
                "uuid": gebruiker.uuid,
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

        # Ex-leden: voormalige teamleden met historische shifts in deze periode
        ex_grid = self._bouw_ex_grid(actieve_team_ids, actieve_gebruiker_ids, datums)

        vorige, volgende = bereken_navigatie(jaar, maand)

        # is_gepubliceerd: enkel relevant voor het gefilterde team (of primaire team bij geen filter)
        check_team_id = filter_team_id if filter_team_id is not None else primair_team_id

        return {
            "grid": grid,
            "ex_grid": ex_grid,
            "dag_info": bouw_dag_info(datums),
            "jaar": jaar,
            "maand": maand,
            "maand_naam": MAAND_NAMEN[maand],
            "is_gepubliceerd": self._is_gepubliceerd(check_team_id, jaar, maand),
            "shiftcodes": self.haal_shiftcodes(locatie_id),
            "shiftcodes_gegroepeerd": self.haal_shiftcodes_gegroepeerd(locatie_id),
            "hud_werkposten": self.haal_hud_werkposten(locatie_id),
            "vorige": vorige,
            "volgende": volgende,
        }

    def haal_teams_voor_locatie(self, locatie_id: int) -> list[Team]:
        """Geef alle actieve teams voor een locatie, gesorteerd op naam."""
        return (
            self.db.query(Team)
            .filter(Team.locatie_id == locatie_id, Team.is_actief == True)
            .order_by(Team.naam)
            .all()
        )

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

    def haal_hud_werkposten(self, locatie_id: int) -> list[str]:
        """Geeft gesorteerde lijst van unieke werkpost-namen uit de shiftcodes voor de HUD-filter."""
        codes = self.haal_shiftcodes(locatie_id)
        return sorted({sc.werkpost.naam for sc in codes if sc.werkpost})

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

    def haal_collega_shifts(
        self,
        collega_id: int,
        team_id: int,
        jaar: int,
        maand: int,
    ) -> dict:
        """Gepubliceerde shifts van een collega (read-only, enkel eigen team).

        Args:
            collega_id: Gebruiker-ID van de collega.
            team_id: Team-ID van de aanvrager (voor scope-controle).
            jaar: Het jaar.
            maand: De maand (1–12).
        """
        _, aantal_dagen = monthrange(jaar, maand)
        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

        shifts_db = (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id == collega_id,
                Planning.team_id == team_id,
                Planning.datum >= datums[0],
                Planning.datum <= datums[-1],
                Planning.status == "gepubliceerd",
                Planning.shift_code.isnot(None),
            )
            .all()
        )
        return {s.datum.isoformat(): s.shift_code for s in shifts_db}

    def haal_teamleden(self, team_id: int) -> list[Gebruiker]:
        """Geef alle actieve teamleden (exclusief reserves) van een team."""
        return (
            self.db.query(Gebruiker)
            .join(GebruikerRol, GebruikerRol.gebruiker_id == Gebruiker.id)
            .filter(
                GebruikerRol.scope_id == team_id,
                GebruikerRol.rol.in_(["teamlid", "planner"]),
                GebruikerRol.is_reserve == False,
                GebruikerRol.is_actief == True,
                Gebruiker.is_actief == True,
            )
            .order_by(Gebruiker.volledige_naam)
            .distinct()
            .all()
        )

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

    def _bouw_ex_grid(
        self,
        actieve_team_ids: list[int],
        actieve_gebruiker_ids: list[int],
        datums: list,
    ) -> list[dict]:
        """Bouw grid-rijen voor ex-leden met historische shifts in de gegeven periode.

        Toont shifts van gebruikers die ooit in deze teams zaten (GebruikerRol.is_actief=False),
        gefilterd op Planning.team_id zodat enkel shifts uit deze teams worden getoond.
        Actieve leden worden uitgesloten (hun shifts staan al in het hoofdgrid).
        """
        ex_rollen = (
            self.db.query(GebruikerRol)
            .filter(
                GebruikerRol.scope_id.in_(actieve_team_ids),
                GebruikerRol.rol.in_(["teamlid", "planner"]),
                GebruikerRol.is_actief == False,
            )
            .all()
        )
        ex_gebruiker_ids = [
            r.gebruiker_id for r in ex_rollen
            if r.gebruiker_id not in actieve_gebruiker_ids
        ]
        if not ex_gebruiker_ids:
            return []

        ex_shifts = (
            self.db.query(Planning)
            .filter(
                Planning.team_id.in_(actieve_team_ids),
                Planning.gebruiker_id.in_(ex_gebruiker_ids),
                Planning.datum >= datums[0],
                Planning.datum <= datums[-1],
            )
            .all()
        )
        # Alleen ex-leden die daadwerkelijk shifts hebben in deze periode tonen
        ex_gebruikers_met_shifts = {s.gebruiker_id for s in ex_shifts}
        if not ex_gebruikers_met_shifts:
            return []

        ex_shifts_idx = {(s.gebruiker_id, s.datum): s for s in ex_shifts}

        ex_gebruikers = (
            self.db.query(Gebruiker)
            .filter(Gebruiker.id.in_(ex_gebruikers_met_shifts))
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

        ex_grid = []
        for gebruiker in ex_gebruikers:
            rij = {
                "id": gebruiker.id,
                "naam": gebruiker.volledige_naam or gebruiker.gebruikersnaam,
                "shifts": {},
            }
            for datum in datums:
                shift = ex_shifts_idx.get((gebruiker.id, datum))
                rij["shifts"][datum.isoformat()] = {
                    "code": shift.shift_code if shift else None,
                }
            ex_grid.append(rij)
        return ex_grid

    def _locatie_van_team(self, team_id: int) -> Optional[int]:
        """Hulpfunctie: geeft locatie_id van een team."""
        team = self.db.query(Team).filter(Team.id == team_id).first()
        return team.locatie_id if team else None
