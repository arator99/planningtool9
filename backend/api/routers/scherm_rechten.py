"""Scherm rechten router — beheerder configureert toegang per route per locatie."""
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import haal_csrf_token, haal_db, verifieer_csrf, vereiste_rol
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from models.gebruiker import Gebruiker
from services.scherm_rechten_service import ALLE_ROLLEN, SCHERM_DEFAULTS, SchermRechtenService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/beheer/rechten", tags=["scherm_rechten"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


@router.get("", response_class=HTMLResponse)
def toon_matrix(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    """Toon de volledige rechtenmatrix voor de beheerder."""
    svc = SchermRechtenService(db, gebruiker.locatie_id)
    matrix = svc.haal_rechten_matrix()

    return sjablonen.TemplateResponse(
        "pages/scherm_rechten/matrix.html",
        _context(
            request,
            gebruiker,
            matrix=matrix,
            scherm_defaults=SCHERM_DEFAULTS,
            alle_rollen=ALLE_ROLLEN,
            csrf_token=csrf_token,
            bericht=request.query_params.get("bericht"),
            fout=request.query_params.get("fout"),
        ),
    )


@router.post("/toggle")
def toggle_toegang(
    route_naam: str = Form(...),
    rol: str = Form(...),
    toegestaan: str = Form(...),
    _csrf: None = Depends(verifieer_csrf),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
):
    """Toggle toegang voor één route+rol combinatie."""
    svc = SchermRechtenService(db, gebruiker.locatie_id)
    try:
        waarde = toegestaan.lower() in ("true", "1", "ja")
        svc.zet_toegang(route_naam, rol, waarde)
    except ValueError as fout:
        logger.warning("Schermrecht toggle mislukt: %s", fout)
        return RedirectResponse(url=f"/beheer/rechten?fout={fout}", status_code=303)

    return RedirectResponse(url="/beheer/rechten", status_code=303)


@router.post("/reset")
def reset_route(
    route_naam: str = Form(...),
    _csrf: None = Depends(verifieer_csrf),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
):
    """Zet alle overrides voor een route terug naar hardcoded defaults."""
    svc = SchermRechtenService(db, gebruiker.locatie_id)
    try:
        if route_naam not in SCHERM_DEFAULTS:
            raise ValueError(f"Onbekende route: {route_naam}")
        aantal = svc.reset_route(route_naam)
        logger.info("Route '%s' gereset: %d overrides verwijderd", route_naam, aantal)
    except ValueError as fout:
        logger.warning("Reset mislukt: %s", fout)
        return RedirectResponse(url=f"/beheer/rechten?fout={fout}", status_code=303)

    return RedirectResponse(url="/beheer/rechten?bericht=reset_klaar", status_code=303)
