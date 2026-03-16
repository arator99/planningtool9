"""Locatie service — CRUD voor productielocaties (super_beheerder only)."""
import logging

from sqlalchemy.orm import Session

from models.locatie import Locatie

logger = logging.getLogger(__name__)

# De systeemlocatie 'NAT' is niet wijzigbaar of verwijderbaar
NAT_CODE = "NAT"


class LocatieService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_alle(self) -> list[Locatie]:
        """Geeft alle locaties, exclusief de systeemlocatie NAT."""
        return (
            self.db.query(Locatie)
            .filter(Locatie.code != NAT_CODE)
            .order_by(Locatie.naam)
            .all()
        )

    def haal_op_uuid(self, uuid: str) -> Locatie:
        """Zoek een locatie op extern uuid. Gooit ValueError als niet gevonden."""
        obj = self.db.query(Locatie).filter(Locatie.uuid == uuid).first()
        if not obj:
            raise ValueError(f"Locatie niet gevonden: {uuid}")
        if obj.code == NAT_CODE:
            raise ValueError("De systeemlocatie NAT is niet bewerkbaar.")
        return obj

    def maak_aan(self, naam: str, code: str, area_label: str | None) -> Locatie:
        """
        Maak een nieuwe locatie aan.

        Raises:
            ValueError: Bij dubbele naam of code.
        """
        naam = naam.strip()
        code = code.strip().upper()
        if not naam:
            raise ValueError("Naam is verplicht.")
        if not code:
            raise ValueError("Code is verplicht.")
        if code == NAT_CODE:
            raise ValueError("Code 'NAT' is gereserveerd voor de systeemlocatie.")

        self._controleer_unieke_naam(naam)
        self._controleer_unieke_code(code)

        locatie = Locatie(
            naam=naam,
            code=code,
            area_label=area_label.strip() if area_label else None,
            is_actief=True,
        )
        self.db.add(locatie)
        self.db.commit()
        self.db.refresh(locatie)
        logger.info("Locatie aangemaakt: %s (%s)", naam, code)
        return locatie

    def bewerk(
        self,
        locatie_id: int,
        naam: str,
        area_label: str | None,
    ) -> Locatie:
        """
        Pas naam en area_label aan. Code is niet wijzigbaar na aanmaken.

        Raises:
            ValueError: Bij dubbele naam of locatie niet gevonden.
        """
        locatie = self._haal_op_id_of_fout(locatie_id)
        naam = naam.strip()
        if not naam:
            raise ValueError("Naam is verplicht.")

        self._controleer_unieke_naam(naam, exclusief_id=locatie_id)
        locatie.naam = naam
        locatie.area_label = area_label.strip() if area_label else None
        self.db.commit()
        self.db.refresh(locatie)
        logger.info("Locatie bijgewerkt: ID %s", locatie_id)
        return locatie

    def deactiveer(self, locatie_id: int) -> None:
        """Deactiveer een locatie (soft delete via is_actief=False)."""
        locatie = self._haal_op_id_of_fout(locatie_id)
        locatie.is_actief = False
        self.db.commit()
        logger.info("Locatie gedeactiveerd: ID %s", locatie_id)

    # ------------------------------------------------------------------ #
    # Privé helpers                                                        #
    # ------------------------------------------------------------------ #

    def _haal_op_id_of_fout(self, locatie_id: int) -> Locatie:
        locatie = self.db.query(Locatie).filter(Locatie.id == locatie_id).first()
        if not locatie:
            raise ValueError(f"Locatie {locatie_id} niet gevonden.")
        if locatie.code == NAT_CODE:
            raise ValueError("De systeemlocatie NAT is niet bewerkbaar.")
        return locatie

    def _controleer_unieke_naam(self, naam: str, exclusief_id: int | None = None) -> None:
        query = self.db.query(Locatie).filter(Locatie.naam == naam)
        if exclusief_id is not None:
            query = query.filter(Locatie.id != exclusief_id)
        if query.first():
            raise ValueError(f"Locatienaam '{naam}' bestaat al.")

    def _controleer_unieke_code(self, code: str, exclusief_id: int | None = None) -> None:
        query = self.db.query(Locatie).filter(Locatie.code == code)
        if exclusief_id is not None:
            query = query.filter(Locatie.id != exclusief_id)
        if query.first():
            raise ValueError(f"Locatiecode '{code}' bestaat al.")
