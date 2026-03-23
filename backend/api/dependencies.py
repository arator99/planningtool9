import logging

from fastapi import Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from database import SessieKlasse
from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol, ROLLEN
from services.auth_service import AuthService
from services.domein.csrf_domein import genereer_csrf_token, verifieer_csrf_token


def haal_db():
    """FastAPI dependency: geeft een database sessie en sluit deze na gebruik."""
    db = SessieKlasse()
    try:
        yield db
    finally:
        db.close()


def haal_huidige_gebruiker(
    request: Request,
    db: Session = Depends(haal_db),
) -> Gebruiker:
    """
    FastAPI dependency: leest het JWT token uit de httpOnly cookie
    en geeft de ingelogde gebruiker terug.
    """
    token = request.cookies.get("toegangs_token")
    logger.debug("Cookies aanwezig: %s", list(request.cookies.keys()))
    if not token:
        logger.warning("Geen 'toegangs_token' cookie gevonden bij %s", request.url.path)
        raise HTTPException(status_code=401, detail="Niet ingelogd")
    try:
        return AuthService(db).verifieer_token(token)
    except ValueError as fout:
        logger.error("Token verificatie mislukt: %s", fout)
        raise HTTPException(status_code=401, detail=str(fout)) from fout


def vereiste_login(gebruiker: Gebruiker = Depends(haal_huidige_gebruiker)) -> Gebruiker:
    """FastAPI dependency: elke ingelogde gebruiker, ongeacht rol."""
    return gebruiker


def haal_csrf_token(
    request: Request,
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> str:
    """FastAPI dependency: genereert een vers CSRF-token voor gebruik in GET-handlers."""
    return genereer_csrf_token(str(gebruiker.id))


def verifieer_csrf(
    request: Request,
    csrf_token: str = Form(None),
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> None:
    """FastAPI dependency: valideert het CSRF-token bij POST-handlers."""
    if not csrf_token or not verifieer_csrf_token(csrf_token, str(gebruiker.id)):
        logger.warning("CSRF-validatie mislukt voor gebruiker %s op %s", gebruiker.id, request.url.path)
        raise HTTPException(status_code=403, detail="Ongeldige of ontbrekende CSRF-token")


def _actieve_rollen(gebruiker: Gebruiker) -> set[str]:
    """Geeft de set van actieve rolnamen van een gebruiker op basis van GebruikerRol."""
    return {r.rol for r in gebruiker.rollen if r.is_actief}


def haal_actieve_locatie_id(
    request: Request,
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> int:
    """Geeft de actief geselecteerde locatie_id.
    Super_beheerder kan via cookie een andere locatie kiezen;
    alle andere gebruikers krijgen altijd hun eigen locatie_id."""
    if "super_beheerder" not in _actieve_rollen(gebruiker):
        return gebruiker.locatie_id
    cookie_val = request.cookies.get("locatie_context")
    if cookie_val:
        try:
            return int(cookie_val)
        except (ValueError, TypeError):
            pass
    return gebruiker.locatie_id


def vereiste_rol(*rollen: str):
    """
    FastAPI dependency factory: controleert of de ingelogde gebruiker
    minstens één van de opgegeven rollen heeft (via GebruikerRol).
    """
    def _controleer(gebruiker: Gebruiker = Depends(haal_huidige_gebruiker)) -> Gebruiker:
        if not _actieve_rollen(gebruiker).intersection(rollen):
            raise HTTPException(status_code=403, detail="Onvoldoende rechten")
        return gebruiker
    return _controleer


def vereiste_super_beheerder(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: enkel super_beheerder."""
    if "super_beheerder" not in _actieve_rollen(gebruiker):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_beheerder_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: beheerder of super_beheerder."""
    if not _actieve_rollen(gebruiker).intersection({"beheerder", "super_beheerder"}):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_planner_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: planner, hr, beheerder of super_beheerder."""
    if not _actieve_rollen(gebruiker).intersection({"planner", "hr", "beheerder", "super_beheerder"}):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_hr_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: hr, beheerder of super_beheerder."""
    if not _actieve_rollen(gebruiker).intersection({"hr", "beheerder", "super_beheerder"}):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def heeft_rol_in_team(
    gebruiker_id: int,
    team_id: int,
    rollen: tuple[str, ...],
    db: Session,
) -> bool:
    """
    Controleer of een gebruiker een van de opgegeven rollen heeft met scope team_id.

    Args:
        gebruiker_id: De te controleren gebruiker.
        team_id: De scope (team).
        rollen: Tuple van geaccepteerde rollen.
        db: Database sessie.

    Returns:
        True als een actieve GebruikerRol gevonden wordt.
    """
    return db.query(GebruikerRol).filter(
        GebruikerRol.gebruiker_id == gebruiker_id,
        GebruikerRol.scope_id == team_id,
        GebruikerRol.rol.in_(rollen),
        GebruikerRol.is_actief == True,
    ).first() is not None


def haal_primaire_team_id(gebruiker_id: int, db: Session) -> int | None:
    """
    Geeft het eerste actieve team-ID van een gebruiker.
    - planner/teamlid: via GebruikerRol.scope_id (= team_id)
    - beheerder/super_beheerder: eerste team van hun locatie als fallback
    """
    from models.team import Team

    rol = db.query(GebruikerRol).filter(
        GebruikerRol.gebruiker_id == gebruiker_id,
        GebruikerRol.rol.in_(["teamlid", "planner"]),
        GebruikerRol.is_actief == True,
    ).first()
    if rol:
        return rol.scope_id

    # Beheerder/super_beheerder: geen teamrol — neem eerste team van hun locatie
    beheer_rol = db.query(GebruikerRol).filter(
        GebruikerRol.gebruiker_id == gebruiker_id,
        GebruikerRol.rol.in_(["beheerder", "super_beheerder"]),
        GebruikerRol.is_actief == True,
    ).first()
    if beheer_rol:
        gebruiker = db.query(Gebruiker).filter(Gebruiker.id == gebruiker_id).first()
        if gebruiker and gebruiker.locatie_id:
            team = db.query(Team).filter(
                Team.locatie_id == gebruiker.locatie_id,
                Team.is_actief == True,
            ).first()
            return team.id if team else None
    return None


def haal_planner_team_ids(gebruiker_id: int, db: Session) -> list[int]:
    """
    Geeft de team_ids waarvoor een gebruiker actief planner is.
    Filtert op echte teams (scope_id moet bestaan in de teams-tabel).
    """
    from models.team import Team

    planner_scope_ids = [
        r.scope_id
        for r in db.query(GebruikerRol).filter(
            GebruikerRol.gebruiker_id == gebruiker_id,
            GebruikerRol.rol == "planner",
            GebruikerRol.is_actief == True,
        ).all()
    ]
    if not planner_scope_ids:
        return []
    return [
        t.id for t in db.query(Team).filter(
            Team.id.in_(planner_scope_ids),
            Team.is_actief == True,
        ).all()
    ]


def heeft_rol_in_locatie(
    gebruiker_id: int,
    locatie_id: int,
    rollen: tuple[str, ...],
    db: Session,
) -> bool:
    """
    Controleer of een gebruiker een van de opgegeven rollen heeft met scope locatie_id.

    Args:
        gebruiker_id: De te controleren gebruiker.
        locatie_id: De scope (locatie).
        rollen: Tuple van geaccepteerde rollen.
        db: Database sessie.

    Returns:
        True als een actieve GebruikerRol gevonden wordt.
    """
    return db.query(GebruikerRol).filter(
        GebruikerRol.gebruiker_id == gebruiker_id,
        GebruikerRol.scope_id == locatie_id,
        GebruikerRol.rol.in_(rollen),
        GebruikerRol.is_actief == True,
    ).first() is not None
