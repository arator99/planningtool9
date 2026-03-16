"""Notitie service — berichten tussen gebruikers per team."""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models.notitie import Notitie
from models.gebruiker import Gebruiker
from services.domein.notitie_domein import valideer_bericht, valideer_prioriteit

logger = logging.getLogger(__name__)


class NotitieService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_op_uuid(self, uuid: str) -> Notitie:
        """Zoek een notitie op extern uuid. Gooit ValueError als niet gevonden."""
        obj = self.db.query(Notitie).filter(Notitie.uuid == uuid).first()
        if not obj:
            raise ValueError(f"Notitie niet gevonden: {uuid}")
        return obj

    def haal_inbox(self, gebruiker_id: int, team_id: int) -> list[Notitie]:
        """Ontvangen notities — direct aan mij of naar de team-mailbox."""
        return (
            self.db.query(Notitie)
            .filter(
                Notitie.team_id == team_id,
                (Notitie.naar_gebruiker_id == gebruiker_id) | (Notitie.naar_gebruiker_id.is_(None)),
            )
            .order_by(Notitie.aangemaakt_op.desc())
            .all()
        )

    def haal_verzonden(self, gebruiker_id: int, team_id: int) -> list[Notitie]:
        return (
            self.db.query(Notitie)
            .filter(Notitie.van_gebruiker_id == gebruiker_id, Notitie.team_id == team_id)
            .order_by(Notitie.aangemaakt_op.desc())
            .all()
        )

    def haal_ongelezen_aantal(self, gebruiker_id: int, team_id: int) -> int:
        return (
            self.db.query(Notitie)
            .filter(
                Notitie.team_id == team_id,
                Notitie.is_gelezen == False,
                (Notitie.naar_gebruiker_id == gebruiker_id) | (Notitie.naar_gebruiker_id.is_(None)),
            )
            .count()
        )

    def stuur(
        self,
        van_id: int,
        team_id: int,
        bericht: str,
        naar_id: int | None,
        prioriteit: str,
    ) -> Notitie:
        valideer_bericht(bericht)
        valideer_prioriteit(prioriteit)
        notitie = Notitie(
            team_id=team_id,
            van_gebruiker_id=van_id,
            naar_gebruiker_id=naar_id,
            bericht=bericht.strip(),
            prioriteit=prioriteit,
        )
        self.db.add(notitie)
        self.db.commit()
        self.db.refresh(notitie)
        return notitie

    def markeer_gelezen(self, notitie_id: int, gebruiker_id: int, team_id: int) -> None:
        n = self.db.query(Notitie).filter(
            Notitie.id == notitie_id, Notitie.team_id == team_id,
            (Notitie.naar_gebruiker_id == gebruiker_id) | (Notitie.naar_gebruiker_id.is_(None)),
        ).first()
        if n and not n.is_gelezen:
            n.is_gelezen = True
            n.gelezen_op = datetime.now()
            self.db.commit()

    def markeer_alles_gelezen(self, gebruiker_id: int, team_id: int) -> None:
        notities = self.db.query(Notitie).filter(
            Notitie.team_id == team_id,
            Notitie.is_gelezen == False,
            (Notitie.naar_gebruiker_id == gebruiker_id) | (Notitie.naar_gebruiker_id.is_(None)),
        ).all()
        for n in notities:
            n.is_gelezen = True
            n.gelezen_op = datetime.now()
        self.db.commit()

    def verwijder(self, notitie_id: int, van_id: int, team_id: int) -> None:
        n = self.db.query(Notitie).filter(
            Notitie.id == notitie_id,
            Notitie.van_gebruiker_id == van_id,
            Notitie.team_id == team_id,
        ).first()
        if not n:
            raise ValueError("Notitie niet gevonden of geen toegang.")
        self.db.delete(n)
        self.db.commit()
