"""Gebruiker service — CRUD en wachtwoordbeheer binnen een locatie/team."""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol
from models.planning import Planning
from models.team import Team
from services.domein.auth_domein import hash_wachtwoord, valideer_wachtwoord_sterkte
from services.domein.gebruiker_domein import valideer_gebruikersnaam_formaat

logger = logging.getLogger(__name__)


class GebruikerService:
    """Gebruikersbeheer: CRUD, validatie en wachtwoordbeheer binnen een locatie."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_alle(self, locatie_id: int) -> list[Gebruiker]:
        """Geeft alle actieve gebruikers van een locatie, gesorteerd op naam."""
        return (
            self.db.query(Gebruiker)
            .filter(Gebruiker.locatie_id == locatie_id, Gebruiker.is_actief == True)
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def haal_team_leden(self, team_id: int, inclusief_reserves: bool = False) -> list[Gebruiker]:
        """Geeft gebruikers gekoppeld aan een team via GebruikerRol."""
        query = (
            self.db.query(Gebruiker)
            .join(GebruikerRol, GebruikerRol.gebruiker_id == Gebruiker.id)
            .filter(
                GebruikerRol.scope_id == team_id,
                GebruikerRol.rol.in_(["teamlid", "planner"]),
                GebruikerRol.is_actief == True,
                Gebruiker.is_actief == True,
            )
        )
        if not inclusief_reserves:
            query = query.filter(GebruikerRol.is_reserve == False)
        return query.order_by(Gebruiker.volledige_naam).all()

    def haal_team_leden_meervoud(self, team_ids: list[int]) -> list[Gebruiker]:
        """Geeft actieve gebruikers gekoppeld aan een of meerdere teams via GebruikerRol."""
        return (
            self.db.query(Gebruiker)
            .join(GebruikerRol, GebruikerRol.gebruiker_id == Gebruiker.id)
            .filter(
                GebruikerRol.scope_id.in_(team_ids),
                GebruikerRol.rol.in_(["teamlid", "planner"]),
                GebruikerRol.is_actief == True,
                Gebruiker.is_actief == True,
            )
            .distinct()
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def haal_reserves(self, team_id: int) -> list[Gebruiker]:
        """Geeft gebruikers die als reserve gekoppeld zijn aan dit team."""
        return (
            self.db.query(Gebruiker)
            .join(GebruikerRol, GebruikerRol.gebruiker_id == Gebruiker.id)
            .filter(
                GebruikerRol.scope_id == team_id,
                GebruikerRol.is_reserve == True,
                GebruikerRol.is_actief == True,
                Gebruiker.is_actief == True,
            )
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def haal_gefilterd(
        self,
        locatie_id: int,
        zoek: str = "",
        rol: str = "",
        status: str = "actief",
        team_id: int | None = None,
    ) -> list[Gebruiker]:
        """Gefilterde gebruikerslijst op basis van zoekterm, rol, status en optioneel team."""
        query = self.db.query(Gebruiker).filter(Gebruiker.locatie_id == locatie_id)
        if status == "actief":
            query = query.filter(Gebruiker.is_actief == True)
        elif status == "inactief":
            query = query.filter(Gebruiker.is_actief == False)
        if rol:
            query = query.filter(Gebruiker.rol == rol)
        if team_id:
            query = query.join(GebruikerRol, GebruikerRol.gebruiker_id == Gebruiker.id).filter(
                GebruikerRol.scope_id == team_id,
                GebruikerRol.rol.in_(["teamlid", "planner"]),
                GebruikerRol.is_actief == True,
            )
        if zoek:
            patroon = f"%{zoek}%"
            query = query.filter(
                (Gebruiker.volledige_naam.ilike(patroon)) |
                (Gebruiker.gebruikersnaam.ilike(patroon))
            )
        return query.order_by(Gebruiker.volledige_naam).all()

    def haal_actieve_medewerkers(self, locatie_id: int) -> list[Gebruiker]:
        """Geeft actieve gebruikers van een locatie, gesorteerd op naam."""
        return (
            self.db.query(Gebruiker)
            .filter(Gebruiker.locatie_id == locatie_id, Gebruiker.is_actief == True)
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def haal_op_id(self, gebruiker_id: int, locatie_id: int) -> Optional[Gebruiker]:
        """Geeft één gebruiker terug, alleen als die tot de locatie behoort."""
        return (
            self.db.query(Gebruiker)
            .filter(Gebruiker.id == gebruiker_id, Gebruiker.locatie_id == locatie_id)
            .first()
        )

    def haal_op_uuid(self, uuid: str) -> Gebruiker:
        """Zoek een gebruiker op extern uuid. Gooit ValueError als niet gevonden."""
        obj = (
            self.db.query(Gebruiker)
            .filter(Gebruiker.uuid == uuid, Gebruiker.is_actief == True)
            .first()
        )
        if not obj:
            raise ValueError(f"Gebruiker niet gevonden: {uuid}")
        return obj

    def maak_aan(
        self,
        locatie_id: int,
        gebruikersnaam: str,
        wachtwoord: str,
        volledige_naam: str,
        rol: str,
        voornaam: Optional[str] = None,
        achternaam: Optional[str] = None,
        team_id: Optional[int] = None,
        is_reserve: bool = False,
        startweek_typedienst: Optional[int] = None,
    ) -> Gebruiker:
        """
        Maakt een nieuwe gebruiker aan binnen de locatie.
        Als team_id opgegeven is, wordt ook een GebruikerRol record aangemaakt.

        Raises:
            ValueError: Bij validatiefouten of dubbele gebruikersnaam.
        """
        valideer_gebruikersnaam_formaat(gebruikersnaam)
        fout = valideer_wachtwoord_sterkte(wachtwoord)
        if fout:
            raise ValueError(fout)
        self._controleer_unieke_gebruikersnaam(gebruikersnaam)

        gebruiker = Gebruiker(
            locatie_id=locatie_id,
            gebruikersnaam=gebruikersnaam,
            gehashed_wachtwoord=hash_wachtwoord(wachtwoord),
            volledige_naam=volledige_naam,
            voornaam=voornaam,
            achternaam=achternaam,
            rol=rol,
            startweek_typedienst=startweek_typedienst,
            is_actief=True,
            totp_actief=False,
        )
        self.db.add(gebruiker)
        self.db.flush()  # verkrijg gebruiker.id vóór commit

        # Rol-record aanmaken
        scope_id = team_id if rol in ("teamlid", "planner") else locatie_id
        koppeling = GebruikerRol(
            gebruiker_id=gebruiker.id,
            rol=rol,
            scope_id=scope_id,
            is_reserve=is_reserve,
            is_actief=True,
        )
        self.db.add(koppeling)
        self.db.commit()
        self.db.refresh(gebruiker)
        logger.info("Gebruiker aangemaakt: %s (locatie %s)", gebruikersnaam, locatie_id)
        return gebruiker

    def bewerk(
        self,
        gebruiker_id: int,
        locatie_id: int,
        gebruikersnaam: str,
        volledige_naam: str,
        rol: str,
        voornaam: Optional[str] = None,
        achternaam: Optional[str] = None,
        startweek_typedienst: Optional[int] = None,
        nieuwe_locatie_id: Optional[int] = None,
    ) -> Gebruiker:
        """
        Past gegevens van een bestaande gebruiker aan.
        nieuwe_locatie_id: verplaatst de gebruiker naar een andere locatie (super_beheerder only).

        Raises:
            ValueError: Bij validatiefouten, dubbele naam of niet gevonden.
        """
        gebruiker = self._haal_op_of_fout(gebruiker_id, locatie_id)
        valideer_gebruikersnaam_formaat(gebruikersnaam)
        self._controleer_unieke_gebruikersnaam(gebruikersnaam, exclusief_id=gebruiker_id)

        gebruiker.gebruikersnaam = gebruikersnaam
        gebruiker.volledige_naam = volledige_naam
        gebruiker.voornaam = voornaam
        gebruiker.achternaam = achternaam
        gebruiker.rol = rol
        gebruiker.startweek_typedienst = startweek_typedienst

        # Synchroniseer de locatie-gebonden GebruikerRol met het nieuwe rol.
        # De locatie-gebonden record is de primaire rol (beheerder/hr/planner aangemaakt
        # zonder team, of teamlid zonder team). Team-gekoppelde records (scope_id = team_id)
        # worden niet aangeraakt — die worden beheerd via teambeheer.
        primaire_rol_record = next(
            (r for r in gebruiker.rollen if r.is_actief and r.scope_id == locatie_id),
            None,
        )
        if primaire_rol_record:
            primaire_rol_record.rol = rol
        else:
            # Geen locatie-gebonden record gevonden (bijv. gebruiker heeft enkel team-rollen):
            # maak een nieuw locatie-gebonden record aan voor beheerder/hr.
            if rol not in ("teamlid", "planner"):
                self.db.add(GebruikerRol(
                    gebruiker_id=gebruiker_id,
                    rol=rol,
                    scope_id=locatie_id,
                    is_reserve=False,
                    is_actief=True,
                ))

        if nieuwe_locatie_id is not None:
            oude_locatie_id = gebruiker.locatie_id
            gebruiker.locatie_id = nieuwe_locatie_id
            # Scope van locatie-gebonden rollen (beheerder, hr) ook verplaatsen
            for rol_record in gebruiker.rollen:
                if rol_record.rol in ("beheerder", "hr") and rol_record.scope_id == oude_locatie_id:
                    rol_record.scope_id = nieuwe_locatie_id
        self.db.commit()
        logger.info("Gebruiker bijgewerkt: ID %s", gebruiker_id)
        return gebruiker

    def deactiveer(self, gebruiker_id: int, locatie_id: int, uitvoerder_id: int) -> None:
        """
        Deactiveert een gebruiker (soft delete).

        Raises:
            ValueError: Als gebruiker zichzelf probeert te deactiveren.
        """
        if gebruiker_id == uitvoerder_id:
            raise ValueError("U kunt uzelf niet deactiveren")
        gebruiker = self._haal_op_of_fout(gebruiker_id, locatie_id)
        gebruiker.is_actief = False
        self.db.commit()
        logger.info("Gebruiker gedeactiveerd: ID %s", gebruiker_id)

    def activeer(self, gebruiker_id: int, locatie_id: int) -> None:
        """Heractiveer een gedeactiveerde gebruiker."""
        gebruiker = self._haal_op_of_fout(gebruiker_id, locatie_id)
        gebruiker.is_actief = True
        self.db.commit()
        logger.info("Gebruiker geactiveerd: ID %s", gebruiker_id)

    def reset_wachtwoord(self, gebruiker_id: int, locatie_id: int, nieuw_wachtwoord: str) -> None:
        """
        Reset het wachtwoord van een gebruiker (door beheerder).

        Raises:
            ValueError: Bij zwak wachtwoord of gebruiker niet gevonden.
        """
        fout = valideer_wachtwoord_sterkte(nieuw_wachtwoord)
        if fout:
            raise ValueError(fout)
        gebruiker = self._haal_op_of_fout(gebruiker_id, locatie_id)
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
        Geeft de geplande shifts van een reservemedewerker over alle teams.
        Retourneert lijst van dicts: datum, shift_code, team_naam.
        """
        rijen = (
            self.db.query(Planning, Team.naam.label("team_naam"))
            .join(Team, Team.id == Planning.team_id)
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
                "team_naam": r.team_naam,
                "status": r.Planning.status,
            }
            for r in rijen
        ]

    # ------------------------------------------------------------------ #
    # Privé helpers                                                        #
    # ------------------------------------------------------------------ #

    def _haal_op_of_fout(self, gebruiker_id: int, locatie_id: int) -> Gebruiker:
        gebruiker = self.haal_op_id(gebruiker_id, locatie_id)
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
