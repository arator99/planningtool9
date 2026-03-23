"""AdvService — CRUD voor ADV-toekenningen per locatie (Fase 8)."""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.adv import AdvToekenning
from models.gebruiker import Gebruiker
from models.lidmaatschap import Lidmaatschap
from models.team import Team
from services.domein.adv_domein import (
    AdvInfo,
    genereer_adv_dagen,
    maak_adv_lookup,
    valideer_adv_toekenning,
)

logger = logging.getLogger(__name__)


class AdvService:
    def __init__(self, db: Session, locatie_id: int) -> None:
        self.db = db
        self.locatie_id = locatie_id

    # ------------------------------------------------------------------ #
    # CRUD                                                                #
    # ------------------------------------------------------------------ #

    def haal_alle(self, gebruiker_id: Optional[int] = None) -> list[AdvToekenning]:
        """
        Geef alle actieve ADV-toekenningen voor de locatie.

        Args:
            gebruiker_id: Optioneel filter op specifieke gebruiker.
        """
        q = (
            self.db.query(AdvToekenning)
            .join(Gebruiker, Gebruiker.id == AdvToekenning.gebruiker_id)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Team.locatie_id == self.locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                AdvToekenning.verwijderd_op.is_(None),
            )
        )
        if gebruiker_id is not None:
            q = q.filter(AdvToekenning.gebruiker_id == gebruiker_id)
        return q.order_by(AdvToekenning.gebruiker_id, AdvToekenning.start_datum).all()

    def haal_op_uuid(self, uuid: str) -> AdvToekenning:
        """
        Geef een ADV-toekenning op uuid.

        Gooit ValueError als niet gevonden of buiten de locatie.
        """
        t = (
            self.db.query(AdvToekenning)
            .join(Gebruiker, Gebruiker.id == AdvToekenning.gebruiker_id)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                AdvToekenning.uuid == uuid,
                Team.locatie_id == self.locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                AdvToekenning.verwijderd_op.is_(None),
            )
            .first()
        )
        if not t:
            raise ValueError("ADV-toekenning niet gevonden.")
        return t

    def maak(
        self,
        gebruiker_id: int,
        adv_type: str,
        dag_van_week: Optional[int],
        start_datum: date,
        aangemaakt_door_id: int,
        eind_datum: Optional[date] = None,
    ) -> AdvToekenning:
        """
        Maak een nieuwe ADV-toekenning aan.

        Gooit ValueError bij ongeldige invoer.
        """
        self._check_gebruiker_in_locatie(gebruiker_id)
        valideer_adv_toekenning(adv_type, dag_van_week, start_datum, eind_datum)

        t = AdvToekenning(
            gebruiker_id=gebruiker_id,
            adv_type=adv_type,
            dag_van_week=dag_van_week,
            start_datum=start_datum,
            eind_datum=eind_datum,
            is_actief=True,
            aangemaakt_door_id=aangemaakt_door_id,
        )
        self.db.add(t)
        self.db.flush()
        logger.info("ADV-toekenning aangemaakt: type=%s gebruiker=%d", adv_type, gebruiker_id)
        return t

    def update(
        self,
        uuid: str,
        adv_type: str,
        dag_van_week: Optional[int],
        start_datum: date,
        eind_datum: Optional[date] = None,
    ) -> AdvToekenning:
        """
        Werk een ADV-toekenning bij.

        Gooit ValueError bij ongeldige invoer.
        """
        t = self.haal_op_uuid(uuid)
        valideer_adv_toekenning(adv_type, dag_van_week, start_datum, eind_datum)
        t.adv_type = adv_type
        t.dag_van_week = dag_van_week
        t.start_datum = start_datum
        t.eind_datum = eind_datum
        self.db.flush()
        return t

    def verwijder(self, uuid: str, verwijderd_door_id: int) -> None:
        """Soft-delete een ADV-toekenning."""
        from datetime import datetime
        t = self.haal_op_uuid(uuid)
        t.verwijderd_op = datetime.utcnow()
        t.verwijderd_door_id = verwijderd_door_id
        t.is_actief = False
        self.db.flush()

    def deactiveer(self, uuid: str) -> None:
        """Deactiveer zonder te verwijderen (behoudt historiek)."""
        t = self.haal_op_uuid(uuid)
        t.is_actief = False
        self.db.flush()

    def activeer(self, uuid: str) -> None:
        """Heractiveer een gedeactiveerde toekenning."""
        t = self.haal_op_uuid(uuid)
        t.is_actief = True
        self.db.flush()

    # ------------------------------------------------------------------ #
    # Lookup voor grid / planning                                         #
    # ------------------------------------------------------------------ #

    def haal_adv_lookup(self, jaar: int, maand: int) -> dict[tuple[int, str], AdvInfo]:
        """
        Geef een (gebruiker_id, 'YYYY-MM-DD') → AdvInfo lookup voor een maand.

        Gebruikt door PlanningService voor grid-rendering.
        """
        actieve = self.haal_alle()
        actieve = [t for t in actieve if t.is_actief]
        return maak_adv_lookup(actieve, jaar, maand)

    def genereer_dagen_voor_gebruiker(
        self, gebruiker_id: int, jaar: int, maand: int
    ) -> list[date]:
        """Genereer alle ADV-dagen voor één gebruiker in een maand."""
        toekenningen = self.haal_alle(gebruiker_id=gebruiker_id)
        dagen: list[date] = []
        for t in toekenningen:
            if not t.is_actief:
                continue
            dagen.extend(genereer_adv_dagen(
                adv_type=t.adv_type,
                dag_van_week=t.dag_van_week,
                start_datum=t.start_datum,
                eind_datum=t.eind_datum,
                jaar=jaar,
                maand=maand,
            ))
        return sorted(set(dagen))

    # ------------------------------------------------------------------ #
    # Intern                                                              #
    # ------------------------------------------------------------------ #

    def _check_gebruiker_in_locatie(self, gebruiker_id: int) -> None:
        g = (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Gebruiker.id == gebruiker_id,
                Team.locatie_id == self.locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
            .first()
        )
        if not g:
            raise ValueError("Gebruiker niet gevonden in deze locatie.")
