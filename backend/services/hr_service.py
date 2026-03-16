"""HR service — twee-laagse validatieregels beheer (Fase 2)."""
import logging
from datetime import date

from sqlalchemy.orm import Session

from models.hr import NationaleHRRegel, LocatieHROverride
from models.planning import RodeLijnConfig
from services.domein.hr_domein import (
    ERNST_NIVEAUS,
    valideer_ernst_niveau,
    valideer_richting,
    valideer_override_waarde,
)

logger = logging.getLogger(__name__)


class HRService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Effectieve waarde (kern van twee-laagse logica)                     #
    # ------------------------------------------------------------------ #

    def haal_effectieve_waarde(self, regel_code: str, locatie_id: int) -> int | None:
        """
        Geeft de effectieve waarde voor een HR-regel voor een specifieke locatie.

        Logica:
        1. Zoek een actieve NationaleHRRegel met de gegeven code.
        2. Kijk of er een LocatieHROverride bestaat voor deze locatie.
        3. Geef de override waarde terug als die bestaat, anders de nationale waarde.
        4. Geef None terug als de regel niet actief is of niet bestaat.
        """
        nationale_regel = (
            self.db.query(NationaleHRRegel)
            .filter(NationaleHRRegel.code == regel_code, NationaleHRRegel.is_actief == True)
            .first()
        )
        if not nationale_regel:
            return None

        override = (
            self.db.query(LocatieHROverride)
            .filter(
                LocatieHROverride.nationale_regel_id == nationale_regel.id,
                LocatieHROverride.locatie_id == locatie_id,
            )
            .first()
        )
        return override.waarde if override else nationale_regel.waarde

    # ------------------------------------------------------------------ #
    # Nationale HR-regels (super_beheerder)                               #
    # ------------------------------------------------------------------ #

    def haal_alle_nationale_regels(self) -> list[NationaleHRRegel]:
        return (
            self.db.query(NationaleHRRegel)
            .order_by(NationaleHRRegel.ernst_niveau, NationaleHRRegel.naam)
            .all()
        )

    def haal_nationale_regel(self, regel_id: int) -> NationaleHRRegel | None:
        return self.db.query(NationaleHRRegel).filter(NationaleHRRegel.id == regel_id).first()

    def haal_op_uuid(self, uuid: str) -> NationaleHRRegel:
        """Zoek een nationale HR-regel op extern uuid. Gooit ValueError als niet gevonden."""
        obj = (
            self.db.query(NationaleHRRegel)
            .filter(NationaleHRRegel.uuid == uuid, NationaleHRRegel.is_actief == True)
            .first()
        )
        if not obj:
            raise ValueError(f"NationaleHRRegel niet gevonden: {uuid}")
        return obj

    def haal_nationale_regel_by_code(self, code: str) -> NationaleHRRegel | None:
        return self.db.query(NationaleHRRegel).filter(NationaleHRRegel.code == code).first()

    def maak_nationale_regel(
        self,
        code: str,
        naam: str,
        waarde: int,
        ernst_niveau: str,
        richting: str,
        eenheid: str | None = None,
        beschrijving: str | None = None,
    ) -> NationaleHRRegel:
        valideer_ernst_niveau(ernst_niveau)
        valideer_richting(richting)
        if self.haal_nationale_regel_by_code(code):
            raise ValueError(f"Nationale HR-regel met code '{code}' bestaat al.")
        regel = NationaleHRRegel(
            code=code,
            naam=naam,
            waarde=waarde,
            ernst_niveau=ernst_niveau,
            richting=richting,
            eenheid=eenheid or None,
            beschrijving=beschrijving or None,
        )
        self.db.add(regel)
        self.db.commit()
        self.db.refresh(regel)
        logger.info("Nationale HR-regel '%s' aangemaakt.", code)
        return regel

    def bewerk_nationale_regel(
        self,
        regel_id: int,
        naam: str,
        waarde: int,
        ernst_niveau: str,
        richting: str,
        eenheid: str | None = None,
        beschrijving: str | None = None,
        is_actief: bool = True,
    ) -> NationaleHRRegel:
        regel = self._haal_nationale_of_fout(regel_id)
        valideer_ernst_niveau(ernst_niveau)
        valideer_richting(richting)
        regel.naam = naam
        regel.waarde = waarde
        regel.ernst_niveau = ernst_niveau
        regel.richting = richting
        regel.eenheid = eenheid or None
        regel.beschrijving = beschrijving or None
        regel.is_actief = is_actief
        self.db.commit()
        logger.info("Nationale HR-regel '%s' bijgewerkt.", regel.code)
        return regel

    # ------------------------------------------------------------------ #
    # Locatie-overrides (beheerder)                                       #
    # ------------------------------------------------------------------ #

    def haal_overrides_voor_locatie(self, locatie_id: int) -> list[LocatieHROverride]:
        return (
            self.db.query(LocatieHROverride)
            .filter(LocatieHROverride.locatie_id == locatie_id)
            .all()
        )

    def haal_override(self, nationale_regel_id: int, locatie_id: int) -> LocatieHROverride | None:
        return (
            self.db.query(LocatieHROverride)
            .filter(
                LocatieHROverride.nationale_regel_id == nationale_regel_id,
                LocatieHROverride.locatie_id == locatie_id,
            )
            .first()
        )

    def sla_override_op(
        self, nationale_regel_id: int, locatie_id: int, waarde: int
    ) -> LocatieHROverride:
        """Upsert: maak aan of update een lokale override. Valideert dat de waarde strenger is."""
        regel = self._haal_nationale_of_fout(nationale_regel_id)
        valideer_override_waarde(regel.richting, regel.waarde, waarde)

        override = self.haal_override(nationale_regel_id, locatie_id)
        if override:
            override.waarde = waarde
        else:
            override = LocatieHROverride(
                nationale_regel_id=nationale_regel_id,
                locatie_id=locatie_id,
                waarde=waarde,
            )
            self.db.add(override)
        self.db.commit()
        self.db.refresh(override)
        logger.info(
            "Override voor regel_id=%d locatie_id=%d ingesteld op %d.",
            nationale_regel_id, locatie_id, waarde,
        )
        return override

    def verwijder_override(self, nationale_regel_id: int, locatie_id: int) -> bool:
        """Verwijder een lokale override (reset naar nationale waarde)."""
        override = self.haal_override(nationale_regel_id, locatie_id)
        if not override:
            return False
        self.db.delete(override)
        self.db.commit()
        logger.info(
            "Override voor regel_id=%d locatie_id=%d verwijderd.",
            nationale_regel_id, locatie_id,
        )
        return True

    # ------------------------------------------------------------------ #
    # Rode Lijn Config                                                    #
    # ------------------------------------------------------------------ #

    def haal_rode_lijn_config(self) -> RodeLijnConfig | None:
        return self.db.query(RodeLijnConfig).first()

    def sla_rode_lijn_config_op(self, referentie_datum: date) -> RodeLijnConfig:
        config = self.haal_rode_lijn_config()
        if config:
            config.referentie_datum = referentie_datum
        else:
            config = RodeLijnConfig(referentie_datum=referentie_datum)
            self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    # ------------------------------------------------------------------ #
    # Intern                                                              #
    # ------------------------------------------------------------------ #

    def _haal_nationale_of_fout(self, regel_id: int) -> NationaleHRRegel:
        regel = self.haal_nationale_regel(regel_id)
        if not regel:
            raise ValueError("Nationale HR-regel niet gevonden.")
        return regel
