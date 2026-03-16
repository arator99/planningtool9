"""Team service — beheer van teams en teamleden."""
import logging

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol
from models.team import Team

logger = logging.getLogger(__name__)


class TeamService:
    """Operaties op teams en teamlidmaatschappen."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def haal_op_uuid(self, uuid: str) -> Team:
        """Zoek een team op extern uuid. Gooit ValueError als niet gevonden."""
        team = self.db.query(Team).filter(Team.uuid == uuid, Team.is_actief == True).first()
        if not team:
            raise ValueError(f"Team niet gevonden: {uuid}")
        return team

    def haal_op_id(self, team_id: int, locatie_id: int) -> Team | None:
        """Zoek een team op id binnen een locatie. Geeft None als niet gevonden."""
        return self.db.query(Team).filter(
            Team.id == team_id,
            Team.locatie_id == locatie_id,
        ).first()

    def haal_alle(self, locatie_id: int) -> list[Team]:
        """Geef alle actieve teams voor een locatie, gesorteerd op naam."""
        return (
            self.db.query(Team)
            .filter(Team.locatie_id == locatie_id, Team.is_actief == True)
            .order_by(Team.naam)
            .all()
        )

    def naam_bestaat(self, locatie_id: int, naam: str) -> bool:
        """Controleer of een teamnaam al in gebruik is voor deze locatie."""
        return self.db.query(Team).filter(
            Team.locatie_id == locatie_id,
            Team.naam == naam,
            Team.is_actief == True,
        ).first() is not None

    def code_bestaat(self, locatie_id: int, code: str) -> bool:
        """Controleer of een teamcode al in gebruik is voor deze locatie."""
        return self.db.query(Team).filter(
            Team.locatie_id == locatie_id,
            Team.code == code,
            Team.is_actief == True,
        ).first() is not None

    def maak_aan(self, naam: str, code: str, locatie_id: int) -> Team:
        """Maak een nieuw team aan. Gooit ValueError bij dubbele naam of code."""
        if self.naam_bestaat(locatie_id, naam):
            raise ValueError("naam_bestaat")
        if self.code_bestaat(locatie_id, code):
            raise ValueError("code_bestaat")
        team = Team(naam=naam, code=code, locatie_id=locatie_id, is_actief=True)
        self.db.add(team)
        self.db.commit()
        logger.info("Team aangemaakt: %s (%s) voor locatie %d", naam, code, locatie_id)
        return team

    def bewerk(self, team: Team, naam: str, code: str) -> Team:
        """Pas naam en code van een bestaand team aan."""
        team.naam = naam
        team.code = code
        self.db.commit()
        return team

    def haal_leden(self, team_id: int) -> tuple[list[GebruikerRol], dict[int, GebruikerRol]]:
        """
        Geef alle GebruikerRol-records voor een team terug.

        Returns:
            (rollen_lijst, {gebruiker_id: GebruikerRol}) tuple voor template-gebruik.
        """
        rollen = (
            self.db.query(GebruikerRol)
            .filter(
                GebruikerRol.scope_id == team_id,
                GebruikerRol.rol.in_(["teamlid", "planner"]),
            )
            .all()
        )
        return rollen, {r.gebruiker_id: r for r in rollen}

    def haal_gebruikers_voor_locatie(self, locatie_id: int) -> list[Gebruiker]:
        """Geef alle actieve gebruikers van een locatie, gesorteerd op naam."""
        return (
            self.db.query(Gebruiker)
            .filter(Gebruiker.locatie_id == locatie_id, Gebruiker.is_actief == True)
            .order_by(Gebruiker.volledige_naam)
            .all()
        )

    def voeg_lid_toe(self, team_id: int, gebruiker_id: int, is_reserve: bool) -> None:
        """Voeg een gebruiker als teamlid toe. Updatet is_reserve bij bestaand lidmaatschap."""
        bestaand = (
            self.db.query(GebruikerRol)
            .filter(
                GebruikerRol.gebruiker_id == gebruiker_id,
                GebruikerRol.scope_id == team_id,
                GebruikerRol.rol.in_(["teamlid", "planner"]),
            )
            .first()
        )
        if bestaand:
            bestaand.is_reserve = is_reserve
        else:
            self.db.add(GebruikerRol(
                gebruiker_id=gebruiker_id,
                rol="teamlid",
                scope_id=team_id,
                is_reserve=is_reserve,
                is_actief=True,
            ))
        self.db.commit()
        logger.info("Lid %d toegevoegd aan team %d (reserve=%s)", gebruiker_id, team_id, is_reserve)

    def verwijder_lid(self, team_id: int, gebruiker_id: int) -> None:
        """Verwijder een teamlid-koppeling."""
        koppeling = (
            self.db.query(GebruikerRol)
            .filter(
                GebruikerRol.gebruiker_id == gebruiker_id,
                GebruikerRol.scope_id == team_id,
                GebruikerRol.rol.in_(["teamlid", "planner"]),
            )
            .first()
        )
        if koppeling:
            self.db.delete(koppeling)
            self.db.commit()
            logger.info("Lid %d verwijderd uit team %d", gebruiker_id, team_id)
