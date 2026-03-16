"""Rapport service — planningsoverzichten en exports."""
import logging
from calendar import monthrange
from datetime import date

from sqlalchemy.orm import Session, aliased

from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol
from models.planning import Planning, PlanningOverride
from models.verlof import VerlofAanvraag
from services.domein.planning_domein import DAG_NAMEN, MAAND_NAMEN, bouw_dag_info
from services.domein.rapport_domein import bouw_csv_inhoud, groepeer_verlof_per_medewerker

logger = logging.getLogger(__name__)


class RapportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def maandplanning_overzicht(self, team_id: int, jaar: int, maand: int) -> dict:
        """Zelfde grid als planning maar read-only, bedoeld voor afdrukken/export."""
        _, aantal_dagen = monthrange(jaar, maand)
        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

        gebruikers = (
            self.db.query(Gebruiker)
            .join(GebruikerRol, GebruikerRol.gebruiker_id == Gebruiker.id)
            .filter(
                GebruikerRol.scope_id == team_id,
                GebruikerRol.rol.in_(["teamlid", "planner"]),
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
        for g in gebruikers:
            rij = {"naam": g.volledige_naam or g.gebruikersnaam, "shifts": []}
            for datum in datums:
                shift = shifts_idx.get((g.id, datum))
                rij["shifts"].append(shift.shift_code if shift and shift.shift_code else "")
            grid.append(rij)

        dag_info = [
            {"dag": d.day, "dag_naam": DAG_NAMEN[d.weekday()], "is_weekend": d.weekday() >= 5}
            for d in datums
        ]
        return {
            "grid": grid,
            "dag_info": dag_info,
            "jaar": jaar,
            "maand": maand,
            "maand_naam": MAAND_NAMEN[maand],
            "datums": datums,
        }

    def maandplanning_csv(self, team_id: int, jaar: int, maand: int) -> str:
        """Genereer CSV string van de maandplanning."""
        data = self.maandplanning_overzicht(team_id, jaar, maand)
        return bouw_csv_inhoud(data["dag_info"], data["grid"])

    def verlof_overzicht(self, locatie_id: int, jaar: int) -> list[dict]:
        """Verlofaanvragen voor een jaar, gegroepeerd per medewerker."""
        start = date(jaar, 1, 1)
        eind = date(jaar, 12, 31)

        aanvragen = (
            self.db.query(VerlofAanvraag)
            .join(Gebruiker, Gebruiker.id == VerlofAanvraag.gebruiker_id)
            .filter(
                Gebruiker.locatie_id == locatie_id,
                VerlofAanvraag.start_datum >= start,
                VerlofAanvraag.eind_datum <= eind,
                VerlofAanvraag.status == "goedgekeurd",
            )
            .order_by(VerlofAanvraag.gebruiker_id, VerlofAanvraag.start_datum)
            .all()
        )

        return groepeer_verlof_per_medewerker(aanvragen)

    def override_audit(self, team_id: int, jaar: int, maand: int) -> list[dict]:
        """
        Alle PlanningOverrides voor een maand, gesorteerd op datum en medewerker.

        Returns:
            Lijst van dicts met: datum, medewerker_naam, regel_code, ernst_niveau,
            overtreding_bericht, reden_afwijking, goedgekeurd_door_naam, goedgekeurd_op.
        """
        _, aantal_dagen = monthrange(jaar, maand)
        start = date(jaar, maand, 1)
        eind = date(jaar, maand, aantal_dagen)

        Goedkeurder = aliased(Gebruiker)
        records = (
            self.db.query(PlanningOverride, Planning, Gebruiker, Goedkeurder)
            .join(Planning, PlanningOverride.planning_shift_id == Planning.id)
            .join(Gebruiker, Planning.gebruiker_id == Gebruiker.id)
            .outerjoin(Goedkeurder, PlanningOverride.goedgekeurd_door == Goedkeurder.id)
            .filter(
                Planning.team_id == team_id,
                Planning.datum >= start,
                Planning.datum <= eind,
            )
            .order_by(Planning.datum, Gebruiker.volledige_naam)
            .all()
        )

        resultaat = []
        for override, planning, medewerker, goedkeurder in records:
            resultaat.append({
                "datum": planning.datum,
                "medewerker_naam": medewerker.volledige_naam or medewerker.gebruikersnaam,
                "shift_code": planning.shift_code,
                "regel_code": override.regel_code,
                "ernst_niveau": override.ernst_niveau,
                "overtreding_bericht": override.overtreding_bericht,
                "reden_afwijking": override.reden_afwijking or "—",
                "goedgekeurd_door_naam": (
                    goedkeurder.volledige_naam or goedkeurder.gebruikersnaam
                ) if goedkeurder else "—",
                "goedgekeurd_op": override.goedgekeurd_op,
            })
        return resultaat

    def medewerkers_overzicht(self, locatie_id: int) -> list[Gebruiker]:
        """Alle gebruikers van de locatie (actief en inactief), gesorteerd op naam."""
        return (
            self.db.query(Gebruiker)
            .filter(Gebruiker.locatie_id == locatie_id)
            .order_by(Gebruiker.volledige_naam)
            .all()
        )
