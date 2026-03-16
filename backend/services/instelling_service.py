"""Instelling service — locatie-instellingen opslaan en ophalen."""
import logging

from sqlalchemy.orm import Session

from models.instelling import AppInstelling, INSTELLING_SLEUTELS

logger = logging.getLogger(__name__)


class InstellingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_alle(self, locatie_id: int) -> dict[str, str]:
        """Geeft alle instellingen voor de groep terug als {sleutel: waarde} dict.
        Ontbrekende sleutels worden aangevuld met hun standaardwaarde."""
        rijen = self.db.query(AppInstelling).filter(AppInstelling.locatie_id == locatie_id).all()
        opgeslagen = {r.sleutel: r.waarde for r in rijen}
        resultaat = {}
        for sleutel, meta in INSTELLING_SLEUTELS.items():
            resultaat[sleutel] = opgeslagen.get(sleutel, meta["standaard"])
        return resultaat

    def haal_waarde(self, locatie_id: int, sleutel: str) -> str:
        """Geeft de waarde van één instelling, of de standaardwaarde."""
        if sleutel not in INSTELLING_SLEUTELS:
            raise ValueError(f"Onbekende instelling: {sleutel}")
        rij = self.db.query(AppInstelling).filter(
            AppInstelling.locatie_id == locatie_id,
            AppInstelling.sleutel == sleutel,
        ).first()
        return rij.waarde if rij else INSTELLING_SLEUTELS[sleutel]["standaard"]

    def sla_op(self, locatie_id: int, sleutel: str, waarde: str, gebruiker_id: int) -> None:
        """Sla één instelling op (upsert)."""
        if sleutel not in INSTELLING_SLEUTELS:
            raise ValueError(f"Onbekende instelling: {sleutel}")
        rij = self.db.query(AppInstelling).filter(
            AppInstelling.locatie_id == locatie_id,
            AppInstelling.sleutel == sleutel,
        ).first()
        if rij:
            rij.waarde = waarde
            rij.bijgewerkt_door = gebruiker_id
        else:
            rij = AppInstelling(
                locatie_id=locatie_id,
                sleutel=sleutel,
                waarde=waarde,
                bijgewerkt_door=gebruiker_id,
            )
            self.db.add(rij)
        self.db.commit()
        logger.info("Instelling %s = %s opgeslagen voor locatie %d", sleutel, waarde, locatie_id)
