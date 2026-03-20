"""TypetabelService — CRUD + grid-beheer voor roostersjablonen (Fase 8)."""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.typetabel import Typetabel, TypetabelEntry
from services.domein.typetabel_domein import (
    bereken_verwachte_shift,
    valideer_aantal_weken,
    valideer_typetabel_naam,
)

logger = logging.getLogger(__name__)


class TypetabelService:
    def __init__(self, db: Session, locatie_id: int) -> None:
        self.db = db
        self.locatie_id = locatie_id

    # ------------------------------------------------------------------ #
    # CRUD                                                                #
    # ------------------------------------------------------------------ #

    def haal_alle(self) -> list[Typetabel]:
        """Geef alle actieve (niet-verwijderde) typetabellen voor de locatie."""
        return (
            self.db.query(Typetabel)
            .filter(
                Typetabel.locatie_id == self.locatie_id,
                Typetabel.verwijderd_op.is_(None),
            )
            .order_by(Typetabel.naam)
            .all()
        )

    def haal_op_uuid(self, uuid: str) -> Typetabel:
        """
        Geef een typetabel op uuid inclusief entries.

        Gooit ValueError als niet gevonden of buiten de locatie.
        """
        tt = (
            self.db.query(Typetabel)
            .filter(
                Typetabel.uuid == uuid,
                Typetabel.locatie_id == self.locatie_id,
                Typetabel.verwijderd_op.is_(None),
            )
            .first()
        )
        if not tt:
            raise ValueError("Typetabel niet gevonden.")
        return tt

    def maak(
        self,
        naam: str,
        aantal_weken: int,
        aangemaakt_door_id: int,
        beschrijving: Optional[str] = None,
    ) -> Typetabel:
        """
        Maak een nieuwe typetabel aan voor de locatie.

        Gooit ValueError bij ongeldige invoer of als naam al bestaat.
        """
        valideer_typetabel_naam(naam)
        valideer_aantal_weken(aantal_weken)
        self._check_unieke_naam(naam)

        tt = Typetabel(
            locatie_id=self.locatie_id,
            naam=naam.strip(),
            beschrijving=beschrijving,
            aantal_weken=aantal_weken,
            is_actief=False,
            aangemaakt_door_id=aangemaakt_door_id,
        )
        self.db.add(tt)
        self.db.flush()
        logger.info("Typetabel aangemaakt: %s (locatie %d)", naam, self.locatie_id)
        return tt

    def update(
        self,
        uuid: str,
        naam: str,
        aantal_weken: int,
        beschrijving: Optional[str] = None,
    ) -> Typetabel:
        """
        Werk naam, weken en beschrijving bij.

        Gooit ValueError bij ongeldige invoer of naamsconflict.
        """
        tt = self.haal_op_uuid(uuid)
        valideer_typetabel_naam(naam)
        valideer_aantal_weken(aantal_weken)
        self._check_unieke_naam(naam, exclude_id=tt.id)

        tt.naam = naam.strip()
        tt.aantal_weken = aantal_weken
        tt.beschrijving = beschrijving
        self.db.flush()
        return tt

    def verwijder(self, uuid: str, verwijderd_door_id: int) -> None:
        """Soft-delete een typetabel (kan niet als actief)."""
        from datetime import datetime
        tt = self.haal_op_uuid(uuid)
        if tt.is_actief:
            raise ValueError("Kan een actieve typetabel niet verwijderen. Deactiveer eerst.")
        tt.verwijderd_op = datetime.utcnow()
        tt.verwijderd_door_id = verwijderd_door_id
        self.db.flush()

    def stel_actief(self, uuid: str) -> Typetabel:
        """
        Zet deze typetabel actief en deactiveer alle andere van de locatie.

        Retourneert de geactiveerde typetabel.
        """
        tt = self.haal_op_uuid(uuid)
        # Deactiveer alle anderen
        self.db.query(Typetabel).filter(
            Typetabel.locatie_id == self.locatie_id,
            Typetabel.verwijderd_op.is_(None),
            Typetabel.id != tt.id,
        ).update({"is_actief": False})
        tt.is_actief = True
        self.db.flush()
        return tt

    def kopieer(self, bron_uuid: str, nieuwe_naam: str, aangemaakt_door_id: int) -> Typetabel:
        """
        Kopieer een typetabel inclusief alle entries naar een nieuwe naam.

        Gooit ValueError als de naam al bestaat.
        """
        bron = self.haal_op_uuid(bron_uuid)
        valideer_typetabel_naam(nieuwe_naam)
        self._check_unieke_naam(nieuwe_naam)

        nieuw = Typetabel(
            locatie_id=self.locatie_id,
            naam=nieuwe_naam.strip(),
            beschrijving=bron.beschrijving,
            aantal_weken=bron.aantal_weken,
            is_actief=False,
            aangemaakt_door_id=aangemaakt_door_id,
        )
        self.db.add(nieuw)
        self.db.flush()

        for entry in bron.entries:
            self.db.add(TypetabelEntry(
                typetabel_id=nieuw.id,
                week_nummer=entry.week_nummer,
                dag_van_week=entry.dag_van_week,
                shift_code=entry.shift_code,
            ))
        self.db.flush()
        logger.info("Typetabel gekopieerd: %s → %s", bron.naam, nieuwe_naam)
        return nieuw

    # ------------------------------------------------------------------ #
    # Grid beheer                                                         #
    # ------------------------------------------------------------------ #

    def sla_grid_op(self, uuid: str, grid: list[list[Optional[str]]]) -> None:
        """
        Vervang alle entries van een typetabel door de grid-data.

        Args:
            uuid: UUID van de typetabel.
            grid: 2D lijst grid[week_index][dag_index] = shift_code (0-based week).
        """
        tt = self.haal_op_uuid(uuid)
        self.db.query(TypetabelEntry).filter(TypetabelEntry.typetabel_id == tt.id).delete()
        for week_idx, week_data in enumerate(grid):
            for dag, code in enumerate(week_data):
                if code and code.strip():
                    self.db.add(TypetabelEntry(
                        typetabel_id=tt.id,
                        week_nummer=week_idx + 1,
                        dag_van_week=dag,
                        shift_code=code.strip().upper(),
                    ))
        self.db.flush()

    def update_cel(self, uuid: str, week: int, dag: int, shift_code: Optional[str]) -> None:
        """
        Update één cel in het grid (upsert).

        Args:
            uuid: UUID van de typetabel.
            week: Week nummer (1-based).
            dag: Dag van week (0=ma, 6=zo).
            shift_code: Nieuwe shift code, of None om te wissen.
        """
        tt = self.haal_op_uuid(uuid)
        entry = (
            self.db.query(TypetabelEntry)
            .filter(
                TypetabelEntry.typetabel_id == tt.id,
                TypetabelEntry.week_nummer == week,
                TypetabelEntry.dag_van_week == dag,
            )
            .first()
        )
        code = shift_code.strip().upper() if shift_code and shift_code.strip() else None
        if entry:
            if code:
                entry.shift_code = code
            else:
                self.db.delete(entry)
        elif code:
            self.db.add(TypetabelEntry(
                typetabel_id=tt.id,
                week_nummer=week,
                dag_van_week=dag,
                shift_code=code,
            ))
        self.db.flush()

    def bouw_grid_dict(self, tt: Typetabel) -> dict[tuple[int, int], Optional[str]]:
        """Bouw een (week, dag) → shift_code lookup dict uit de entries van een typetabel."""
        return {(e.week_nummer, e.dag_van_week): e.shift_code for e in tt.entries}

    # ------------------------------------------------------------------ #
    # Shift lookup                                                        #
    # ------------------------------------------------------------------ #

    def bereken_verwachte_shift(self, startweek: int, datum: date) -> Optional[str]:
        """
        Bereken de verwachte shift voor een medewerker op een datum via de actieve typetabel.

        Args:
            startweek: De startweek van de medewerker (1-based).
            datum: De datum.

        Returns:
            Shift code of None als geen actieve typetabel of startweek ongeldig.
        """
        tt = (
            self.db.query(Typetabel)
            .filter(
                Typetabel.locatie_id == self.locatie_id,
                Typetabel.is_actief == True,
                Typetabel.verwijderd_op.is_(None),
            )
            .first()
        )
        if not tt:
            return None
        grid = self.bouw_grid_dict(tt)
        return bereken_verwachte_shift(datum, startweek, grid, tt.aantal_weken)

    # ------------------------------------------------------------------ #
    # Intern                                                              #
    # ------------------------------------------------------------------ #

    def _check_unieke_naam(self, naam: str, exclude_id: Optional[int] = None) -> None:
        q = self.db.query(Typetabel).filter(
            Typetabel.locatie_id == self.locatie_id,
            Typetabel.naam == naam.strip(),
            Typetabel.verwijderd_op.is_(None),
        )
        if exclude_id:
            q = q.filter(Typetabel.id != exclude_id)
        if q.first():
            raise ValueError(f"Een typetabel met de naam '{naam}' bestaat al.")
