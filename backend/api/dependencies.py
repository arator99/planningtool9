import logging

from fastapi import Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from database import SessieKlasse
from models.gebruiker import Gebruiker
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
    een van de opgegeven rollen heeft.
    """
    def _controleer(gebruiker: Gebruiker = Depends(haal_huidige_gebruiker)) -> Gebruiker:
        if gebruiker.rol not in rollen:
            raise HTTPException(status_code=403, detail="Onvoldoende rechten")
        return gebruiker
    return _controleer
