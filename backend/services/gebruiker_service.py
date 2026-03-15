import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.groep import GebruikerGroep
from models.planning import Planning
from services.domein.auth_domein import hash_wachtwoord, valideer_wachtwoord_sterkte
from services.domein.gebruiker_domein import valideer_gebruikersnaam_formaat

logger = logging.getLogger(__name__)


class GebruikerService:
    """Gebruikersbeheer: CRUD, validatie en wachtwoordbeheer binnen een groep."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_alle(self, groep_id: int) -> list[Gebruiker]:
        """Geeft alle vaste leden van een groep via junction table, gesorteerd op naam."""
        return (
            self.db.query(Gebruiker)
            .join(GebruikerGroep, GebruikerGroep.gebruiker_id == Gebruiker.id)
            .filter(GebruikerGroep.groep_id == groep_id, GebruikerGroep.is_reserve == False)
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def haal_reserves(self, groep_id: int) -> list[Gebruiker]:
        """Geeft gebruikers die als reserve gekoppeld zijn aan deze groep."""
        return (
            self.db.query(Gebruiker)
            .join(GebruikerGroep, GebruikerGroep.gebruiker_id == Gebruiker.id)
            .filter(GebruikerGroep.groep_id == groep_id, GebruikerGroep.is_reserve == True)
            .filter(Gebruiker.is_actief == True)
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def haal_gefilterd(
        self,
        groep_id: int,
        zoek: str = "",
        rol: str = "",
        status: str = "actief",
    ) -> list[Gebruiker]:
        """Gefilterde gebruikerslijst (vaste leden) op basis van zoekterm, rol en status."""
        query = (
            self.db.query(Gebruiker)
            .join(GebruikerGroep, GebruikerGroep.gebruiker_id == Gebruiker.id)
            .filter(GebruikerGroep.groep_id == groep_id, GebruikerGroep.is_reserve == False)
        )
        if status == "actief":
            query = query.filter(Gebruiker.is_actief == True)
        elif status == "inactief":
            query = query.filter(Gebruiker.is_actief == False)
        if rol:
            query = query.filter(Gebruiker.rol == rol)
        if zoek:
            patroon = f"%{zoek}%"
            query = query.filter(
                (Gebruiker.volledige_naam.ilike(patroon)) |
                (Gebruiker.gebruikersnaam.ilike(patroon))
            )
        return query.order_by(Gebruiker.volledige_naam).all()

    def haal_actieve_medewerkers(self, groep_id: int) -> list[Gebruiker]:
        """Geeft actieve vaste leden van een groep via junction table, gesorteerd op naam."""
        return (
            self.db.query(Gebruiker)
            .join(GebruikerGroep, GebruikerGroep.gebruiker_id == Gebruiker.id)
            .filter(
                GebruikerGroep.groep_id == groep_id,
                GebruikerGroep.is_reserve == False,
                Gebruiker.is_actief == True,
            )
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def haal_op_id(self, gebruiker_id: int, groep_id: int) -> Optional[Gebruiker]:
        """Geeft één gebruiker terug, alleen als die tot de groep behoort."""
        return (
            self.db.query(Gebruiker)
            .filter(Gebruiker.id == gebruiker_id, Gebruiker.groep_id == groep_id)
            .first()
        )

    def maak_aan(
        self,
        groep_id: int,
        gebruikersnaam: str,
        wachtwoord: str,
        volledige_naam: str,
        rol: str,
        voornaam: Optional[str] = None,
        achternaam: Optional[str] = None,
        is_reserve: bool = False,
        startweek_typedienst: Optional[int] = None,
    ) -> Gebruiker:
        """
        Maakt een nieuwe gebruiker aan binnen de groep.

        Raises:
            ValueError: Bij validatiefouten of dubbele gebruikersnaam.
        """
        valideer_gebruikersnaam_formaat(gebruikersnaam)
        fout = valideer_wachtwoord_sterkte(wachtwoord)
        if fout:
            raise ValueError(fout)
        self._controleer_unieke_gebruikersnaam(gebruikersnaam)

        gebruiker = Gebruiker(
            groep_id=groep_id,
            gebruikersnaam=gebruikersnaam,
            gehashed_wachtwoord=hash_wachtwoord(wachtwoord),
            volledige_naam=volledige_naam,
            voornaam=voornaam,
            achternaam=achternaam,
            rol=rol,
            is_reserve=is_reserve,
            startweek_typedienst=startweek_typedienst,
            is_actief=True,
            totp_actief=False,
        )
        self.db.add(gebruiker)
        self.db.flush()  # verkrijg gebruiker.id vóór commit
        # Automatisch junction-record aanmaken
        koppeling = GebruikerGroep(
            gebruiker_id=gebruiker.id,
            groep_id=groep_id,
            is_reserve=is_reserve,
        )
        self.db.add(koppeling)
        self.db.commit()
        self.db.refresh(gebruiker)
        logger.info("Gebruiker aangemaakt: %s (groep %s)", gebruikersnaam, groep_id)
        return gebruiker

    def bewerk(
        self,
        gebruiker_id: int,
        groep_id: int,
        gebruikersnaam: str,
        volledige_naam: str,
        rol: str,
        voornaam: Optional[str] = None,
        achternaam: Optional[str] = None,
        is_reserve: bool = False,
        startweek_typedienst: Optional[int] = None,
    ) -> Gebruiker:
        """
        Past gegevens van een bestaande gebruiker aan.

        Raises:
            ValueError: Bij validatiefouten, dubbele naam of niet gevonden.
        """
        gebruiker = self._haal_op_of_fout(gebruiker_id, groep_id)
        valideer_gebruikersnaam_formaat(gebruikersnaam)
        self._controleer_unieke_gebruikersnaam(gebruikersnaam, exclusief_id=gebruiker_id)

        gebruiker.gebruikersnaam = gebruikersnaam
        gebruiker.volledige_naam = volledige_naam
        gebruiker.voornaam = voornaam
        gebruiker.achternaam = achternaam
        gebruiker.rol = rol
        gebruiker.is_reserve = is_reserve
        gebruiker.startweek_typedienst = startweek_typedienst
        self.db.commit()
        logger.info("Gebruiker bijgewerkt: ID %s", gebruiker_id)
        return gebruiker

    def deactiveer(self, gebruiker_id: int, groep_id: int, uitvoerder_id: int) -> None:
        """
        Deactiveert een gebruiker (soft delete).

        Raises:
            ValueError: Als gebruiker zichzelf probeert te deactiveren.
        """
        if gebruiker_id == uitvoerder_id:
            raise ValueError("U kunt uzelf niet deactiveren")
        gebruiker = self._haal_op_of_fout(gebruiker_id, groep_id)
        gebruiker.is_actief = False
        self.db.commit()
        logger.info("Gebruiker gedeactiveerd: ID %s", gebruiker_id)

    def activeer(self, gebruiker_id: int, groep_id: int) -> None:
        """Heractiveer een gedeactiveerde gebruiker."""
        gebruiker = self._haal_op_of_fout(gebruiker_id, groep_id)
        gebruiker.is_actief = True
        self.db.commit()
        logger.info("Gebruiker geactiveerd: ID %s", gebruiker_id)

    def reset_wachtwoord(self, gebruiker_id: int, groep_id: int, nieuw_wachtwoord: str) -> None:
        """
        Reset het wachtwoord van een gebruiker (door beheerder).

        Raises:
            ValueError: Bij zwak wachtwoord of gebruiker niet gevonden.
        """
        fout = valideer_wachtwoord_sterkte(nieuw_wachtwoord)
        if fout:
            raise ValueError(fout)
        gebruiker = self._haal_op_of_fout(gebruiker_id, groep_id)
        gebruiker.gehashed_wachtwoord = hash_wachtwoord(nieuw_wachtwoord)
        self.db.commit()
        logger.info("Wachtwoord gereset voor gebruiker ID %s", gebruiker_id)

    def haal_reserve_bezetting(
        self,
        gebruiker_id: int,
        datum_van: date,
        datum_tot: date,
    ) -> list[dict]:
        """
        Geeft de geplande shifts van een reservemedewerker over alle groepen.
        Retourneert lijst van dicts: datum, shift_code, groep_naam.
        """
        from models.groep import Groep

        rijen = (
            self.db.query(Planning, Groep.naam.label("groep_naam"))
            .join(Groep, Groep.id == Planning.groep_id)
            .filter(
                Planning.gebruiker_id == gebruiker_id,
                Planning.datum >= datum_van,
                Planning.datum <= datum_tot,
                Planning.shift_code.isnot(None),
            )
            .order_by(Planning.datum)
            .all()
        )
        return [
            {
                "datum": r.Planning.datum,
                "shift_code": r.Planning.shift_code,
                "groep_naam": r.groep_naam,
                "status": r.Planning.status,
            }
            for r in rijen
        ]

    # ------------------------------------------------------------------ #
    # Privé helpers                                                        #
    # ------------------------------------------------------------------ #

    def _haal_op_of_fout(self, gebruiker_id: int, groep_id: int) -> Gebruiker:
        gebruiker = self.haal_op_id(gebruiker_id, groep_id)
        if not gebruiker:
            raise ValueError(f"Gebruiker {gebruiker_id} niet gevonden")
        return gebruiker

    def _controleer_unieke_gebruikersnaam(
        self, gebruikersnaam: str, exclusief_id: Optional[int] = None
    ) -> None:
        query = self.db.query(Gebruiker).filter(Gebruiker.gebruikersnaam == gebruikersnaam)
        if exclusief_id is not None:
            query = query.filter(Gebruiker.id != exclusief_id)
        if query.first():
            raise ValueError(f"Gebruikersnaam '{gebruikersnaam}' is al in gebruik")
