"""Gebruiker service — CRUD en wachtwoordbeheer binnen een locatie/team."""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol, GebruikerRolType
from models.lidmaatschap import Lidmaatschap, LidmaatschapType
from models.planning import Planning
from models.team import Team
from services.domein.auth_domein import hash_wachtwoord, valideer_wachtwoord_sterkte
from services.domein.gebruiker_domein import valideer_gebruikersnaam_formaat

logger = logging.getLogger(__name__)


class GebruikerService:
    """Gebruikersbeheer: CRUD, validatie en wachtwoordbeheer."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_alle(self, locatie_id: int) -> list[Gebruiker]:
        """Geeft alle actieve gebruikers van een locatie via hun lidmaatschappen, gesorteerd op naam."""
        return (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Team.locatie_id == locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                Gebruiker.is_actief == True,
            )
            .distinct()
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def haal_team_leden(self, team_id: int, inclusief_reserves: bool = False) -> list[Gebruiker]:
        """Geeft gebruikers gekoppeld aan een team via Lidmaatschap."""
        query = (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .filter(
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
                Gebruiker.is_actief == True,
            )
        )
        if not inclusief_reserves:
            query = query.filter(Lidmaatschap.type != LidmaatschapType.reserve)
        return query.order_by(Gebruiker.volledige_naam).all()

    def haal_team_leden_meervoud(self, team_ids: list[int]) -> list[Gebruiker]:
        """Geeft actieve gebruikers gekoppeld aan een of meerdere teams via Lidmaatschap."""
        return (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .filter(
                Lidmaatschap.team_id.in_(team_ids),
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
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
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .filter(
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.type == LidmaatschapType.reserve,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
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
        query = (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Team.locatie_id == locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
        )
        if status == "actief":
            query = query.filter(Gebruiker.is_actief == True)
        elif status == "inactief":
            query = query.filter(Gebruiker.is_actief == False)
        if rol:
            query = query.filter(Gebruiker.rol == rol)
        if team_id:
            query = query.filter(Lidmaatschap.team_id == team_id)
        if zoek:
            patroon = f"%{zoek}%"
            query = query.filter(
                (Gebruiker.volledige_naam.ilike(patroon)) |
                (Gebruiker.gebruikersnaam.ilike(patroon))
            )
        return query.distinct().order_by(Gebruiker.volledige_naam).all()

    def haal_actieve_medewerkers(self, locatie_id: int) -> list[Gebruiker]:
        """Geeft actieve gebruikers van een locatie via hun lidmaatschappen, gesorteerd op naam."""
        return self.haal_alle(locatie_id)

    def haal_op_id(self, gebruiker_id: int, locatie_id: int) -> Optional[Gebruiker]:
        """Geeft één gebruiker terug als die tot de locatie behoort via een actief lidmaatschap."""
        return (
            self.db.query(Gebruiker)
            .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
            .join(Team, Team.id == Lidmaatschap.team_id)
            .filter(
                Gebruiker.id == gebruiker_id,
                Team.locatie_id == locatie_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
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
        gebruikersnaam: str,
        wachtwoord: str,
        volledige_naam: str,
        rol: str,
        team_id: int,
        voornaam: Optional[str] = None,
        achternaam: Optional[str] = None,
        lid_type: LidmaatschapType = LidmaatschapType.vast,
        is_planner: bool = False,
        startweek_typedienst: Optional[int] = None,
    ) -> Gebruiker:
        """
        Maakt een nieuwe gebruiker aan en koppelt die atomisch aan een team.

        Invariant: elke gebruiker heeft minstens 1 actief lidmaatschap — team_id is verplicht.

        Raises:
            ValueError: Bij validatiefouten, dubbele gebruikersnaam of ontbrekend team.
        """
        valideer_gebruikersnaam_formaat(gebruikersnaam)
        fout = valideer_wachtwoord_sterkte(wachtwoord)
        if fout:
            raise ValueError(fout)
        self._controleer_unieke_gebruikersnaam(gebruikersnaam)

        team = self.db.query(Team).filter(Team.id == team_id, Team.is_actief == True).first()
        if not team:
            raise ValueError(f"Team niet gevonden: {team_id}")

        gebruiker = Gebruiker(
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

        # Atomisch lidmaatschap aanmaken — invariant gegarandeerd
        self.db.add(Lidmaatschap(
            gebruiker_id=gebruiker.id,
            team_id=team_id,
            type=lid_type,
            is_planner=is_planner,
            is_actief=True,
        ))
        self.db.commit()
        self.db.refresh(gebruiker)
        logger.info("Gebruiker aangemaakt: %s (team %s)", gebruikersnaam, team_id)
        return gebruiker

    def maak_en_koppel_als_planner(
        self,
        planner_id: int,
        team_id: int,
        gebruikersnaam: str,
        wachtwoord: str,
        volledige_naam: str,
        voornaam: Optional[str] = None,
        achternaam: Optional[str] = None,
        lid_type: LidmaatschapType = LidmaatschapType.vast,
    ) -> Gebruiker:
        """
        Maakt een nieuwe gebruiker aan en koppelt die aan een team (Planner Zoek-en-Koppel stroom).
        Valideert dat de planner schrijfrechten heeft voor het opgegeven team.

        Raises:
            ValueError: Als planner geen rechten heeft, team niet gevonden, of gebruikersnaam bezet.
        """
        planner_lid = (
            self.db.query(Lidmaatschap)
            .filter(
                Lidmaatschap.gebruiker_id == planner_id,
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.is_planner == True,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
            .first()
        )
        if not planner_lid:
            raise ValueError("Geen plannerrechten voor dit team")

        return self.maak_aan(
            gebruikersnaam=gebruikersnaam,
            wachtwoord=wachtwoord,
            volledige_naam=volledige_naam,
            rol="teamlid",
            team_id=team_id,
            voornaam=voornaam,
            achternaam=achternaam,
            lid_type=lid_type,
            is_planner=False,
        )

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
    ) -> Gebruiker:
        """
        Past profielgegevens van een bestaande gebruiker aan.
        Rol-wijzigingen voor admin-rollen (beheerder/hr) verlopen via de GebruikerRol-router.

        Raises:
            ValueError: Bij validatiefouten, dubbele gebruikersnaam of niet gevonden.
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
