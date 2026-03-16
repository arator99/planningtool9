"""Verlof service — aanvragen, overzicht, goedkeuren/weigeren."""
import calendar
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.planning import SpecialCode
from models.verlof import VerlofAanvraag
from services.domein.verlof_domein import (
    BEHANDELAAR_ROLLEN,
    bereken_verlof_dagen,
    valideer_verlof_periode,
)

logger = logging.getLogger(__name__)


class VerlofService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Lezen                                                                #
    # ------------------------------------------------------------------ #

    def haal_alle(self, locatie_id: int) -> list[VerlofAanvraag]:
        """Alle aanvragen voor de locatie, nieuwste eerst."""
        return (
            self.db.query(VerlofAanvraag)
            .join(Gebruiker, Gebruiker.id == VerlofAanvraag.gebruiker_id)
            .filter(Gebruiker.locatie_id == locatie_id)
            .order_by(VerlofAanvraag.aangevraagd_op.desc())
            .all()
        )

    def haal_eigen(self, gebruiker_id: int) -> list[VerlofAanvraag]:
        """Aanvragen van één gebruiker, nieuwste eerst."""
        return (
            self.db.query(VerlofAanvraag)
            .filter(VerlofAanvraag.gebruiker_id == gebruiker_id)
            .order_by(VerlofAanvraag.aangevraagd_op.desc())
            .all()
        )

    def haal_op_id(self, aanvraag_id: int, locatie_id: int) -> VerlofAanvraag | None:
        return (
            self.db.query(VerlofAanvraag)
            .join(Gebruiker, Gebruiker.id == VerlofAanvraag.gebruiker_id)
            .filter(VerlofAanvraag.id == aanvraag_id, Gebruiker.locatie_id == locatie_id)
            .first()
        )

    def haal_op_uuid(self, uuid: str) -> VerlofAanvraag:
        """Zoek een verlofaanvraag op extern uuid. Gooit ValueError als niet gevonden."""
        obj = self.db.query(VerlofAanvraag).filter(VerlofAanvraag.uuid == uuid).first()
        if not obj:
            raise ValueError(f"VerlofAanvraag niet gevonden: {uuid}")
        return obj

    def haal_verlofcodes(self) -> list[SpecialCode]:
        return (
            self.db.query(SpecialCode)
            .filter(SpecialCode.term.isnot(None))
            .order_by(SpecialCode.naam)
            .all()
        )

    # ------------------------------------------------------------------ #
    # Aanmaken                                                             #
    # ------------------------------------------------------------------ #

    def maak_aanvraag(
        self,
        gebruiker_id: int,
        start_datum: date,
        eind_datum: date,
        opmerking: str | None,
        ingediend_door_id: int | None = None,
    ) -> VerlofAanvraag:
        valideer_verlof_periode(start_datum, eind_datum)
        aantal = bereken_verlof_dagen(start_datum, eind_datum)

        aanvraag = VerlofAanvraag(
            gebruiker_id=gebruiker_id,
            start_datum=start_datum,
            eind_datum=eind_datum,
            aantal_dagen=aantal,
            status="pending",
            opmerking=opmerking or None,
            ingediend_door=ingediend_door_id,
        )
        self.db.add(aanvraag)
        self.db.commit()
        self.db.refresh(aanvraag)
        logger.info("Verlofaanvraag aangemaakt: gebruiker %s, %s–%s", gebruiker_id, start_datum, eind_datum)
        return aanvraag

    # ------------------------------------------------------------------ #
    # Behandelen                                                           #
    # ------------------------------------------------------------------ #

    def goedkeuren(
        self,
        aanvraag_id: int,
        locatie_id: int,
        behandelaar_id: int,
        code_term: str | None = None,
    ) -> VerlofAanvraag:
        aanvraag = self._haal_pending(aanvraag_id, locatie_id)
        aanvraag.status = "goedgekeurd"
        aanvraag.behandeld_door = behandelaar_id
        aanvraag.behandeld_op = datetime.now()
        aanvraag.toegekende_code_term = code_term or None
        self.db.commit()
        logger.info("Verlofaanvraag %s goedgekeurd door %s", aanvraag_id, behandelaar_id)
        return aanvraag

    def weigeren(
        self,
        aanvraag_id: int,
        locatie_id: int,
        behandelaar_id: int,
        reden: str,
    ) -> VerlofAanvraag:
        if not reden or not reden.strip():
            raise ValueError("Reden van weigering is verplicht.")
        aanvraag = self._haal_pending(aanvraag_id, locatie_id)
        aanvraag.status = "geweigerd"
        aanvraag.behandeld_door = behandelaar_id
        aanvraag.behandeld_op = datetime.now()
        aanvraag.reden_weigering = reden.strip()
        self.db.commit()
        logger.info("Verlofaanvraag %s geweigerd door %s", aanvraag_id, behandelaar_id)
        return aanvraag

    def verwijder(self, aanvraag_id: int, gebruiker_id: int) -> None:
        aanvraag = (
            self.db.query(VerlofAanvraag)
            .filter(VerlofAanvraag.id == aanvraag_id, VerlofAanvraag.gebruiker_id == gebruiker_id)
            .first()
        )
        if not aanvraag:
            raise ValueError("Aanvraag niet gevonden.")
        if aanvraag.status != "pending":
            raise ValueError("Enkel pending aanvragen kunnen verwijderd worden.")
        self.db.delete(aanvraag)
        self.db.commit()

    def haal_maand_overzicht(self, locatie_id: int, jaar: int, maand: int) -> dict:
        laatste_dag = calendar.monthrange(jaar, maand)[1]
        eerste = date(jaar, maand, 1)
        laatste = date(jaar, maand, laatste_dag)

        medewerkers = (
            self.db.query(Gebruiker)
            .filter(Gebruiker.locatie_id == locatie_id, Gebruiker.is_actief == True)
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

        aanvragen = (
            self.db.query(VerlofAanvraag)
            .join(Gebruiker, Gebruiker.id == VerlofAanvraag.gebruiker_id)
            .filter(
                Gebruiker.locatie_id == locatie_id,
                VerlofAanvraag.start_datum <= laatste,
                VerlofAanvraag.eind_datum >= eerste,
                VerlofAanvraag.status.in_(["pending", "goedgekeurd"]),
            )
            .all()
        )

        verlof_per_dag: dict[int, dict[str, str]] = {}
        for a in aanvragen:
            cursor = max(a.start_datum, eerste)
            einde = min(a.eind_datum, laatste)
            while cursor <= einde:
                verlof_per_dag.setdefault(a.gebruiker_id, {})[cursor.isoformat()] = a.status
                cursor += timedelta(days=1)

        datums = [date(jaar, maand, d) for d in range(1, laatste_dag + 1)]
        return {
            "medewerkers": medewerkers,
            "datums": datums,
            "verlof_per_dag": verlof_per_dag,
        }

    def haal_pending_count(self, locatie_id: int) -> int:
        """Aantal openstaande verlofaanvragen voor de locatie."""
        return (
            self.db.query(VerlofAanvraag)
            .join(Gebruiker, Gebruiker.id == VerlofAanvraag.gebruiker_id)
            .filter(Gebruiker.locatie_id == locatie_id, VerlofAanvraag.status == "pending")
            .count()
        )

    # ------------------------------------------------------------------ #
    # Intern                                                               #
    # ------------------------------------------------------------------ #

    def _haal_pending(self, aanvraag_id: int, locatie_id: int) -> VerlofAanvraag:
        aanvraag = self.haal_op_id(aanvraag_id, locatie_id)
        if not aanvraag:
            raise ValueError("Aanvraag niet gevonden.")
        if aanvraag.status != "pending":
            raise ValueError("Aanvraag is al behandeld.")
        return aanvraag
