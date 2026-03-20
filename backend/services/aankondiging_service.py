"""Aankondiging service — CRUD en activatiebeheer voor systeemberichten."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models.aankondiging import Aankondiging, AANKONDIGING_SJABLONEN

logger = logging.getLogger(__name__)


class AankondigingService:
    """Beheer van systeemaankondigingen (onderhoud, updates, ...)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_alle(self) -> list[Aankondiging]:
        """Geeft alle aankondigingen, nieuwste eerst."""
        return (
            self.db.query(Aankondiging)
            .order_by(Aankondiging.aangemaakt_op.desc())
            .all()
        )

    def haal_actief(self) -> list[Aankondiging]:
        """Geeft aankondigingen die nu zichtbaar zijn (actief + binnen tijdvenster)."""
        nu = datetime.now(timezone.utc).replace(tzinfo=None)
        return (
            self.db.query(Aankondiging)
            .filter(
                Aankondiging.is_actief == True,
                (Aankondiging.gepland_van == None) | (Aankondiging.gepland_van <= nu),
                (Aankondiging.gepland_tot == None) | (Aankondiging.gepland_tot >= nu),
            )
            .order_by(Aankondiging.aangemaakt_op.desc())
            .all()
        )

    def haal_op_uuid(self, uuid: str) -> Aankondiging:
        """Zoek een aankondiging op uuid. Gooit ValueError als niet gevonden."""
        obj = self.db.query(Aankondiging).filter(Aankondiging.uuid == uuid).first()
        if not obj:
            raise ValueError(f"Aankondiging niet gevonden: {uuid}")
        return obj

    def maak_aan(
        self,
        sjabloon: str,
        ernst: str,
        type: str,
        aangemaakt_door_id: int,
        extra_info: Optional[str] = None,
        gepland_van: Optional[datetime] = None,
        gepland_tot: Optional[datetime] = None,
        is_actief: bool = False,
    ) -> Aankondiging:
        """Maakt een nieuwe aankondiging aan.

        Raises:
            ValueError: Bij ongeldige invoer.
        """
        self._valideer(sjabloon, ernst, type, gepland_van, gepland_tot)
        obj = Aankondiging(
            sjabloon=sjabloon,
            extra_info=extra_info or None,
            ernst=ernst,
            type=type,
            gepland_van=gepland_van,
            gepland_tot=gepland_tot,
            is_actief=is_actief,
            aangemaakt_door_id=aangemaakt_door_id,
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        logger.info("Aankondiging aangemaakt: sjabloon='%s'", sjabloon)
        return obj

    def bewerk(
        self,
        uuid: str,
        sjabloon: str,
        ernst: str,
        type: str,
        extra_info: Optional[str] = None,
        gepland_van: Optional[datetime] = None,
        gepland_tot: Optional[datetime] = None,
        is_actief: bool = False,
    ) -> Aankondiging:
        """Past een bestaande aankondiging aan."""
        self._valideer(sjabloon, ernst, type, gepland_van, gepland_tot)
        obj = self.haal_op_uuid(uuid)
        obj.sjabloon = sjabloon
        obj.extra_info = extra_info or None
        obj.ernst = ernst
        obj.type = type
        obj.gepland_van = gepland_van
        obj.gepland_tot = gepland_tot
        obj.is_actief = is_actief
        self.db.commit()
        logger.info("Aankondiging bijgewerkt: sjabloon='%s'", sjabloon)
        return obj

    def zet_actief(self, uuid: str, actief: bool) -> Aankondiging:
        """Activeer of deactiveer een aankondiging."""
        obj = self.haal_op_uuid(uuid)
        obj.is_actief = actief
        self.db.commit()
        logger.info("Aankondiging '%s' is_actief=%s", obj.sjabloon, actief)
        return obj

    def verwijder(self, uuid: str) -> None:
        """Verwijdert een aankondiging permanent."""
        obj = self.haal_op_uuid(uuid)
        self.db.delete(obj)
        self.db.commit()
        logger.info("Aankondiging verwijderd: '%s'", uuid)

    # ------------------------------------------------------------------ #
    # Privé helpers                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _valideer(
        sjabloon: str,
        ernst: str,
        type: str,
        gepland_van: Optional[datetime],
        gepland_tot: Optional[datetime],
    ) -> None:
        if sjabloon not in AANKONDIGING_SJABLONEN:
            raise ValueError("Ongeldig sjabloon.")
        if ernst not in ("info", "waarschuwing", "kritiek"):
            raise ValueError("Ongeldig ernst-niveau.")
        if type not in ("banner", "dialoog"):
            raise ValueError("Ongeldig type.")
        if gepland_van and gepland_tot and gepland_van >= gepland_tot:
            raise ValueError("'Zichtbaar tot' moet na 'Zichtbaar van' liggen.")
