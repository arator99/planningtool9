"""Team service — beheer van teams en teamleden."""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.lidmaatschap import Lidmaatschap, LidmaatschapType
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

    def haal_leden(self, team_id: int) -> tuple[list[Lidmaatschap], dict[int, Lidmaatschap]]:
        """
        Geef alle actieve Lidmaatschap-records voor een team terug.

        Returns:
            (lidmaatschappen_lijst, {gebruiker_id: Lidmaatschap}) tuple voor template-gebruik.
        """
        lidmaatschappen = (
            self.db.query(Lidmaatschap)
            .filter(
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
            .all()
        )
        return lidmaatschappen, {l.gebruiker_id: l for l in lidmaatschappen}

    def haal_gebruikers_voor_locatie(self, locatie_id: int) -> list[Gebruiker]:
        """Geef alle actieve gebruikers van een locatie via hun lidmaatschappen, gesorteerd op naam."""
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

    def voeg_lid_toe(
        self,
        team_id: int,
        gebruiker_id: int,
        lid_type: LidmaatschapType = LidmaatschapType.vast,
        is_planner: bool = False,
    ) -> None:
        """
        Voeg een gebruiker als teamlid toe. Heractiveer bij eerder verwijderd lidmaatschap.

        Args:
            team_id: Het doelteam.
            gebruiker_id: De toe te voegen gebruiker.
            lid_type: Vast, Reserve of Detachering.
            is_planner: True om plannerrechten toe te kennen voor dit team.
        """
        bestaand = (
            self.db.query(Lidmaatschap)
            .filter(
                Lidmaatschap.gebruiker_id == gebruiker_id,
                Lidmaatschap.team_id == team_id,
            )
            .first()
        )
        if bestaand:
            bestaand.type = lid_type
            bestaand.is_planner = is_planner
            bestaand.is_actief = True
            bestaand.verwijderd_op = None
            bestaand.verwijderd_door_id = None
        else:
            self.db.add(Lidmaatschap(
                gebruiker_id=gebruiker_id,
                team_id=team_id,
                type=lid_type,
                is_planner=is_planner,
                is_actief=True,
            ))
        self.db.commit()
        logger.info("Lid %d toegevoegd aan team %d (type=%s, planner=%s)", gebruiker_id, team_id, lid_type, is_planner)

    def verwijder_lid(self, team_id: int, gebruiker_id: int, verwijderd_door_id: int | None = None) -> None:
        """Deactiveer een teamlidmaatschap (soft delete). Behoudt historische shifts zichtbaarheid.

        Raises ValueError als dit het laatste actieve lidmaatschap van de gebruiker is
        (invariant: elke gebruiker heeft altijd minstens 1 actief lidmaatschap).
        """
        koppeling = (
            self.db.query(Lidmaatschap)
            .filter(
                Lidmaatschap.gebruiker_id == gebruiker_id,
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
            .first()
        )
        if not koppeling:
            return

        aantal_actief = (
            self.db.query(Lidmaatschap)
            .filter(
                Lidmaatschap.gebruiker_id == gebruiker_id,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
            .count()
        )
        if aantal_actief <= 1:
            raise ValueError("Kan het laatste lidmaatschap van een gebruiker niet verwijderen.")

        koppeling.is_actief = False
        koppeling.verwijderd_op = datetime.utcnow()
        koppeling.verwijderd_door_id = verwijderd_door_id
        self.db.commit()
        logger.info("Lid %d gedeactiveerd uit team %d", gebruiker_id, team_id)

    def haal_ex_leden(self, team_id: int) -> list[Lidmaatschap]:
        """Geeft inactieve Lidmaatschap-records voor dit team (voormalige leden)."""
        return (
            self.db.query(Lidmaatschap)
            .filter(
                Lidmaatschap.team_id == team_id,
                Lidmaatschap.is_actief == False,
            )
            .all()
        )
