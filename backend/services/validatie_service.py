"""HR Validatie Service — controleert planning tegen arbeidstijdregels."""
import logging
from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.hr import HRRegel, RodeLijn
from models.planning import Planning, PlanningOverride, Shiftcode, SpecialCode
from services.domein.validatie_domein import (
    ValidatieFout,
    VALIDATORS,
    sorteer_fouten,
)

logger = logging.getLogger(__name__)


class ValidatieService:
    """Valideert de maandplanning van een groep tegen de actieve HR-regels."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def valideer_maand(
        self, groep_id: int, jaar: int, maand: int
    ) -> list[ValidatieFout]:
        """Draai alle actieve validators en geef gecombineerde resultaten terug."""
        _, dagen = monthrange(jaar, maand)
        maand_start = date(jaar, maand, 1)
        maand_eind = date(jaar, maand, dagen)
        context_start = maand_start - timedelta(days=14)  # lookback window

        # ── Data ophalen ─────────────────────────────────────────────
        shifts_db = (
            self.db.query(Planning)
            .filter(
                Planning.groep_id == groep_id,
                Planning.datum >= context_start,
                Planning.datum <= maand_eind,
            )
            .all()
        )

        gebruikers: dict[int, Gebruiker] = {
            g.id: g
            for g in self.db.query(Gebruiker)
            .filter(Gebruiker.groep_id == groep_id, Gebruiker.is_actief == True)
            .all()
        }

        sc_lut: dict[str, Shiftcode] = {
            sc.code: sc
            for sc in self.db.query(Shiftcode)
            .filter(Shiftcode.groep_id == groep_id)
            .all()
        }

        sp_lut: dict[str, SpecialCode] = {
            sp.code: sp for sp in self.db.query(SpecialCode).all()
        }

        regels: dict[str, HRRegel] = {
            r.code: r
            for r in self.db.query(HRRegel)
            .filter(HRRegel.groep_id == groep_id, HRRegel.is_actief == True)
            .all()
        }

        rode_lijn: RodeLijn | None = (
            self.db.query(RodeLijn)
            .filter(RodeLijn.groep_id == groep_id, RodeLijn.is_actief == True)
            .first()
        )

        # Actieve overrides: set van (gebruiker_id, datum, validator_code)
        overrides: set[tuple[int, date, str]] = set()
        for s in shifts_db:
            for o in s.overrides:
                overrides.add((s.gebruiker_id, s.datum, o.regel_code))

        # shifts_per_user: gebruiker_id → datum → shift_code | None
        shifts_per_user: dict[int, dict[date, str | None]] = {uid: {} for uid in gebruikers}
        for s in shifts_db:
            if s.gebruiker_id in shifts_per_user:
                shifts_per_user[s.gebruiker_id][s.datum] = s.shift_code

        # Alle shifts op een dag: datum → lijst shift_codes
        shifts_per_dag: dict[date, list[str | None]] = {}
        for s in shifts_db:
            if maand_start <= s.datum <= maand_eind:
                shifts_per_dag.setdefault(s.datum, []).append(s.shift_code)

        # ── Validators draaien ────────────────────────────────────────
        ctx = dict(
            groep_id=groep_id,
            maand_start=maand_start,
            maand_eind=maand_eind,
            context_start=context_start,
            gebruikers=gebruikers,
            shifts_per_user=shifts_per_user,
            shifts_per_dag=shifts_per_dag,
            sc_lut=sc_lut,
            sp_lut=sp_lut,
            regels=regels,
            rode_lijn=rode_lijn,
            overrides=overrides,
        )

        fouten: list[ValidatieFout] = []
        for fn in VALIDATORS:
            try:
                fouten.extend(fn(ctx))
            except Exception as e:
                logger.error("Validator %s crashte: %s", fn.__name__, e, exc_info=True)

        return sorteer_fouten(fouten)

    def maak_override(
        self,
        groep_id: int,
        gebruiker_id: int,
        datum: date,
        regel_code: str,
        reden: str,
        goedgekeurd_door_id: int,
    ) -> None:
        """Sla een planner-override op voor een CRITICAL overtreding."""
        planning = (
            self.db.query(Planning)
            .filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.groep_id == groep_id,
                Planning.datum == datum,
            )
            .first()
        )
        if not planning:
            raise ValueError("Geen planningshift gevonden voor die datum.")

        bestaand = (
            self.db.query(PlanningOverride)
            .filter(
                PlanningOverride.planning_shift_id == planning.id,
                PlanningOverride.regel_code == regel_code,
            )
            .first()
        )
        if bestaand:
            bestaand.reden_afwijking = reden
            bestaand.goedgekeurd_door = goedgekeurd_door_id
        else:
            override = PlanningOverride(
                planning_shift_id=planning.id,
                regel_code=regel_code,
                ernst_niveau="CRITICAL",
                overtreding_bericht=f"Override voor {regel_code} op {datum}",
                reden_afwijking=reden,
                goedgekeurd_door=goedgekeurd_door_id,
            )
            self.db.add(override)
        self.db.commit()
