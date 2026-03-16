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


def vereiste_rol(*rollen: str):
    """
    FastAPI dependency factory: controleert of de ingelogde gebruiker
    een van de opgegeven rollen heeft (denormalized Gebruiker.rol).

    Gebruik voor snelle rol-checks. Voor scopegebonden checks:
    gebruik heeft_rol_in_team() of heeft_rol_in_locatie().
    """
    def _controleer(gebruiker: Gebruiker = Depends(haal_huidige_gebruiker)) -> Gebruiker:
        if gebruiker.rol not in rollen:
            raise HTTPException(status_code=403, detail="Onvoldoende rechten")
        return gebruiker
    return _controleer


def vereiste_super_beheerder(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: enkel super_beheerder."""
    if gebruiker.rol != "super_beheerder":
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_beheerder_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: beheerder of super_beheerder."""
    if gebruiker.rol not in ("beheerder", "super_beheerder"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_planner_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: planner, hr, beheerder of super_beheerder."""
    if gebruiker.rol not in ("planner", "hr", "beheerder", "super_beheerder"):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_hr_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: hr, beheerder of super_beheerder."""
    if gebruiker.rol not in ("hr", "beheerder", "super_beheerder"):
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
    Geeft het eerste actieve team-ID van een gebruiker (planner of teamlid rol).
    Gebruikt als fallback voor het actieve team van een gebruiker totdat
    Fase 4 een expliciete team-selector toevoegt.
    """
    rol = db.query(GebruikerRol).filter(
        GebruikerRol.gebruiker_id == gebruiker_id,
        GebruikerRol.rol.in_(["teamlid", "planner"]),
        GebruikerRol.is_actief == True,
    ).first()
    return rol.scope_id if rol else None


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
