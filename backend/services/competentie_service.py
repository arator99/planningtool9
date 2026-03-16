"""Competentie service — CRUD voor competenties + gebruikerkoppelingen."""
import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from models.competentie import Competentie, GebruikerCompetentie, NIVEAUS
from models.gebruiker import Gebruiker

logger = logging.getLogger(__name__)


class CompetentieService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Competenties lezen                                                   #
    # ------------------------------------------------------------------ #

    def haal_alle(self, locatie_id: int, ook_inactief: bool = False) -> list[Competentie]:
        q = self.db.query(Competentie).filter(Competentie.locatie_id == locatie_id)
        if not ook_inactief:
            q = q.filter(Competentie.is_actief == True)
        return q.order_by(Competentie.categorie.nullslast(), Competentie.naam).all()

    def haal_op_id(self, competentie_id: int, locatie_id: int) -> Competentie | None:
        return (
            self.db.query(Competentie)
            .filter(Competentie.id == competentie_id, Competentie.locatie_id == locatie_id)
            .first()
        )

    def haal_op_uuid(self, uuid: str) -> Competentie:
        """Zoek een competentie op extern uuid. Gooit ValueError als niet gevonden."""
        obj = (
            self.db.query(Competentie)
            .filter(Competentie.uuid == uuid, Competentie.is_actief == True)
            .first()
        )
        if not obj:
            raise ValueError(f"Competentie niet gevonden: {uuid}")
        return obj

    # ------------------------------------------------------------------ #
    # Aanmaken                                                             #
    # ------------------------------------------------------------------ #

    def maak_aan(
        self,
        locatie_id: int,
        naam: str,
        beschrijving: str | None,
        categorie: str | None,
    ) -> Competentie:
        naam = naam.strip()
        if not naam:
            raise ValueError("Naam is verplicht.")
        bestaand = self.db.query(Competentie).filter(
            Competentie.locatie_id == locatie_id, Competentie.naam == naam
        ).first()
        if bestaand:
            raise ValueError(f"Competentie '{naam}' bestaat al.")

        comp = Competentie(
            locatie_id=locatie_id,
            naam=naam,
            beschrijving=beschrijving or None,
            categorie=categorie.strip() if categorie else None,
        )
        self.db.add(comp)
        self.db.commit()
        self.db.refresh(comp)
        logger.info("Competentie aangemaakt: %s (groep %s)", naam, locatie_id)
        return comp

    # ------------------------------------------------------------------ #
    # Bewerken                                                             #
    # ------------------------------------------------------------------ #

    def bewerk(
        self,
        competentie_id: int,
        locatie_id: int,
        naam: str,
        beschrijving: str | None,
        categorie: str | None,
    ) -> Competentie:
        comp = self._haal_of_fout(competentie_id, locatie_id)
        naam = naam.strip()
        if not naam:
            raise ValueError("Naam is verplicht.")
        conflict = self.db.query(Competentie).filter(
            Competentie.locatie_id == locatie_id,
            Competentie.naam == naam,
            Competentie.id != competentie_id,
        ).first()
        if conflict:
            raise ValueError(f"Competentie '{naam}' bestaat al.")
        comp.naam = naam
        comp.beschrijving = beschrijving or None
        comp.categorie = categorie.strip() if categorie else None
        self.db.commit()
        logger.info("Competentie %s bijgewerkt", comp.naam)
        return comp

    # ------------------------------------------------------------------ #
    # Deactiveren                                                          #
    # ------------------------------------------------------------------ #

    def deactiveer(self, competentie_id: int, locatie_id: int) -> None:
        comp = self._haal_of_fout(competentie_id, locatie_id)
        if not comp.is_actief:
            raise ValueError("Competentie is al inactief.")
        comp.is_actief = False
        comp.gedeactiveerd_op = datetime.now()
        self.db.commit()
        logger.info("Competentie %s gedeactiveerd", comp.naam)

    # ------------------------------------------------------------------ #
    # Gebruikerkoppelingen                                                 #
    # ------------------------------------------------------------------ #

    def haal_koppelingen(self, gebruiker_id: int) -> list[GebruikerCompetentie]:
        return (
            self.db.query(GebruikerCompetentie)
            .filter(GebruikerCompetentie.gebruiker_id == gebruiker_id)
            .all()
        )

    def stel_koppelingen_in(
        self,
        gebruiker_id: int,
        locatie_id: int,
        competentie_ids: list[int],
        niveaus: dict[int, str | None],
        geldig_tot: dict[int, date | None],
    ) -> None:
        """
        Vervang alle competentiekoppelingen voor een gebruiker.

        competentie_ids: lijst van actieve competentie-ID's
        niveaus: dict van competentie_id → niveau (of None)
        geldig_tot: dict van competentie_id → datum (of None)
        """
        # Controleer groep eigenaarschap van competenties
        geldige_ids = {
            c.id for c in self.haal_alle(locatie_id)
        }
        competentie_ids = [cid for cid in competentie_ids if cid in geldige_ids]

        bestaand = {
            k.competentie_id: k
            for k in self.haal_koppelingen(gebruiker_id)
        }

        # Verwijder koppelingen die niet meer in de lijst staan
        for cid, koppeling in list(bestaand.items()):
            if cid not in competentie_ids:
                self.db.delete(koppeling)

        # Toevoegen of bijwerken
        for cid in competentie_ids:
            niveau = niveaus.get(cid) or None
            if niveau and niveau not in NIVEAUS:
                niveau = None
            vd = geldig_tot.get(cid) or None

            if cid in bestaand:
                bestaand[cid].niveau = niveau
                bestaand[cid].geldig_tot = vd
            else:
                self.db.add(GebruikerCompetentie(
                    gebruiker_id=gebruiker_id,
                    competentie_id=cid,
                    niveau=niveau,
                    geldig_tot=vd,
                ))

        self.db.commit()
        logger.info("Competenties bijgewerkt voor gebruiker %s (%d koppelingen)", gebruiker_id, len(competentie_ids))

    # ------------------------------------------------------------------ #
    # Intern                                                               #
    # ------------------------------------------------------------------ #

    def _haal_of_fout(self, competentie_id: int, locatie_id: int) -> Competentie:
        comp = self.haal_op_id(competentie_id, locatie_id)
        if not comp:
            raise ValueError("Competentie niet gevonden.")
        return comp
