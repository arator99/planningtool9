"""Rapport service — planningsoverzichten en exports."""
import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import Session, aliased

from models.gebruiker import Gebruiker
from models.lidmaatschap import Lidmaatschap
from models.planning import Planning, PlanningOverride, Shiftcode
from models.team import Team
from models.verlof import VerlofAanvraag
from services.domein.planning_domein import DAG_NAMEN, MAAND_NAMEN
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
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .filter(
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
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
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Team.locatie_id == locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                VerlofAanvraag.start_datum >= start,
                VerlofAanvraag.eind_datum <= eind,
                VerlofAanvraag.status == "goedgekeurd",
            )
            .distinct()
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
        """Alle gebruikers van de locatie via lidmaatschappen, gesorteerd op naam."""
        return (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Team.locatie_id == locatie_id,
                Lidmaatschap.verwijderd_op == None,
            )
            .distinct()
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def uren_rapport(self, locatie_id: int, jaar: int, maand: int) -> list[dict]:
        """Uren per medewerker voor een maand — shifts × shift-duur.

        Berekent duur uit Shiftcode.start_uur / eind_uur. Locatie-specifieke code
        heeft prioriteit boven nationale code (locatie_id IS NULL).
        """
        _, aantal_dagen = monthrange(jaar, maand)
        start = date(jaar, maand, 1)
        eind = date(jaar, maand, aantal_dagen)

        # Alle planning entries voor de locatie
        planningen = (
            self.db.query(Planning, Gebruiker)
            .join(Gebruiker, Planning.gebruiker_id == Gebruiker.id)
            .join(Team, Planning.team_id == Team.id)
            .filter(
                Team.locatie_id == locatie_id,
                Planning.datum >= start,
                Planning.datum <= eind,
            )
            .order_by(Gebruiker.volledige_naam, Planning.datum)
            .all()
        )

        # Laad shiftcodes — prefereer locatie-specifiek boven nationaal
        shift_codes = {p.shift_code for p, _ in planningen if p.shift_code}
        shiftcode_map: dict[str, Shiftcode] = {}
        if shift_codes:
            sc_rijen = (
                self.db.query(Shiftcode)
                .filter(
                    Shiftcode.code.in_(shift_codes),
                    or_(Shiftcode.locatie_id == locatie_id, Shiftcode.locatie_id.is_(None)),
                )
                .all()
            )
            for sc in sc_rijen:
                # Locatie-specifiek overschrijft nationaal
                if sc.code not in shiftcode_map or sc.locatie_id is not None:
                    shiftcode_map[sc.code] = sc

        # Aggregeer per medewerker
        data: dict[int, dict] = defaultdict(lambda: {
            "naam": "", "shifts": 0, "werkdagen": 0, "uren": 0.0,
        })

        for planning, gebruiker in planningen:
            uid = gebruiker.id
            data[uid]["naam"] = gebruiker.volledige_naam or gebruiker.gebruikersnaam
            data[uid]["shifts"] += 1

            sc = shiftcode_map.get(planning.shift_code) if planning.shift_code else None
            if sc:
                if sc.telt_als_werkdag:
                    data[uid]["werkdagen"] += 1
                if sc.start_uur and sc.eind_uur:
                    data[uid]["uren"] += _bereken_shift_uren(sc.start_uur, sc.eind_uur)

        return sorted(data.values(), key=lambda x: x["naam"])

    def verlof_maandgrid(self, team_id: int, jaar: int, maand: int) -> dict:
        """Maandgrid met goedgekeurde verlofaanvragen per medewerker.

        Geeft terug: grid (lijst van {naam, verlof: [code|None per dag]}),
        dag_info, capaciteitsrij (aantal beschikbare medewerkers per dag).
        """
        _, aantal_dagen = monthrange(jaar, maand)
        datums = [date(jaar, maand, d) for d in range(1, aantal_dagen + 1)]

        # Medewerkers van het team
        gebruikers = (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .filter(
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                Gebruiker.is_actief == True,
            )
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

        # Goedgekeurde verlofaanvragen die overlappen met de maand
        aanvragen = (
            self.db.query(VerlofAanvraag)
            .join(Gebruiker, Gebruiker.id == VerlofAanvraag.gebruiker_id)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .filter(
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                VerlofAanvraag.start_datum <= datums[-1],
                VerlofAanvraag.eind_datum >= datums[0],
                VerlofAanvraag.status == "goedgekeurd",
                VerlofAanvraag.verwijderd_op.is_(None),
            )
            .all()
        )

        # Bouw verlofindex: {gebruiker_id: {datum: code}}
        verlof_idx: dict[int, dict[date, str]] = {}
        for aanvraag in aanvragen:
            uid = aanvraag.gebruiker_id
            if uid not in verlof_idx:
                verlof_idx[uid] = {}
            cur = aanvraag.start_datum
            while cur <= aanvraag.eind_datum:
                if datums[0] <= cur <= datums[-1]:
                    verlof_idx[uid][cur] = aanvraag.toegekende_code_term or "VV"
                cur += timedelta(days=1)

        # Bouw grid
        grid = []
        capaciteit = [len(gebruikers)] * len(datums)

        for g in gebruikers:
            rij_verlof = []
            for i, datum in enumerate(datums):
                code = verlof_idx.get(g.id, {}).get(datum)
                rij_verlof.append(code)
                if code:
                    capaciteit[i] = max(0, capaciteit[i] - 1)
            grid.append({
                "naam": g.volledige_naam or g.gebruikersnaam,
                "verlof": rij_verlof,
            })

        dag_info = [
            {
                "dag": d.day,
                "dag_naam": DAG_NAMEN[d.weekday()],
                "is_weekend": d.weekday() >= 5,
            }
            for d in datums
        ]

        return {
            "grid": grid,
            "dag_info": dag_info,
            "capaciteit": capaciteit,
            "jaar": jaar,
            "maand": maand,
            "maand_naam": MAAND_NAMEN[maand],
        }


def _bereken_shift_uren(start_uur: str, eind_uur: str) -> float:
    """Bereken shift-duur in uren (ondersteunt over-middernacht)."""
    try:
        sh, sm = map(int, start_uur[:5].split(":"))
        eh, em = map(int, eind_uur[:5].split(":"))
        start_min = sh * 60 + sm
        eind_min = eh * 60 + em
        if eind_min <= start_min:
            eind_min += 24 * 60
        return round((eind_min - start_min) / 60, 2)
    except (ValueError, AttributeError):
        return 0.0
