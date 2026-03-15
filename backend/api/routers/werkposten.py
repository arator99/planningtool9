import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from services.werkpost_service import WerkpostService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/werkposten", tags=["werkposten"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


# ------------------------------------------------------------------ #
# Overzicht                                                            #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def lijst(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    werkposten = WerkpostService(db).haal_alle(gebruiker.groep_id, ook_inactief=True)
    bericht = request.query_params.get("bericht")
    fout = request.query_params.get("fout")
    return sjablonen.TemplateResponse(
        "pages/werkposten/lijst.html",
        _context(request, gebruiker,
                 werkposten=werkposten,
                 bericht=bericht,
                 fout=fout,
                 csrf_token=csrf_token),
    )


# ------------------------------------------------------------------ #
# Nieuw                                                                #
# ------------------------------------------------------------------ #

@router.get("/nieuw", response_class=HTMLResponse)
def nieuw_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    csrf_token: str = Depends(haal_csrf_token),
):
    return sjablonen.TemplateResponse(
        "pages/werkposten/formulier.html",
        _context(request, gebruiker,
                 bewerk_modus=False,
                 wp=None,
                 csrf_token=csrf_token),
    )


@router.post("/nieuw")
def maak_aan(
    naam: str = Form(...),
    beschrijving: str = Form(""),
    telt_als_werkdag: str = Form(""),
    reset_12u_rust: str = Form(""),
    breekt_werk_reeks: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        WerkpostService(db).maak_aan(
            groep_id=gebruiker.groep_id,
            naam=naam,
            beschrijving=beschrijving or None,
            telt_als_werkdag=bool(telt_als_werkdag),
            reset_12u_rust=bool(reset_12u_rust),
            breekt_werk_reeks=bool(breekt_werk_reeks),
        )
    except ValueError as fout:
        logger.warning("Werkpost aanmaken mislukt: %s", fout)
        return RedirectResponse(url="/werkposten/nieuw?fout=aanmaken_mislukt", status_code=303)
    return RedirectResponse(url="/werkposten?bericht=Werkpost+aangemaakt", status_code=303)


# ------------------------------------------------------------------ #
# Bewerken                                                             #
# ------------------------------------------------------------------ #

@router.get("/{werkpost_id}/bewerk", response_class=HTMLResponse)
def bewerk_formulier(
    werkpost_id: int,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    wp = WerkpostService(db).haal_op_id(werkpost_id, gebruiker.groep_id)
    if not wp:
        return RedirectResponse(url="/werkposten?fout=niet_gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/werkposten/formulier.html",
        _context(request, gebruiker,
                 bewerk_modus=True,
                 wp=wp,
                 csrf_token=csrf_token),
    )


@router.post("/{werkpost_id}/bewerk")
def bewerk(
    werkpost_id: int,
    naam: str = Form(...),
    beschrijving: str = Form(""),
    telt_als_werkdag: str = Form(""),
    reset_12u_rust: str = Form(""),
    breekt_werk_reeks: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        WerkpostService(db).bewerk(
            werkpost_id=werkpost_id,
            groep_id=gebruiker.groep_id,
            naam=naam,
            beschrijving=beschrijving or None,
            telt_als_werkdag=bool(telt_als_werkdag),
            reset_12u_rust=bool(reset_12u_rust),
            breekt_werk_reeks=bool(breekt_werk_reeks),
        )
    except ValueError as fout:
        logger.warning("Werkpost bewerken mislukt: %s", fout)
        return RedirectResponse(url=f"/werkposten/{werkpost_id}/bewerk?fout=bewerken_mislukt", status_code=303)
    return RedirectResponse(url="/werkposten?bericht=Werkpost+opgeslagen", status_code=303)


# ------------------------------------------------------------------ #
# Deactiveren / Activeren                                              #
# ------------------------------------------------------------------ #

@router.post("/{werkpost_id}/deactiveer")
def deactiveer(
    werkpost_id: int,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        WerkpostService(db).deactiveer(werkpost_id, gebruiker.groep_id)
    except ValueError as fout:
        logger.warning("Werkpost deactiveren mislukt: %s", fout)
        return RedirectResponse(url="/werkposten?fout=actie_mislukt", status_code=303)
    return RedirectResponse(url="/werkposten?bericht=Werkpost+gedeactiveerd", status_code=303)


@router.post("/{werkpost_id}/activeer")
def activeer(
    werkpost_id: int,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        WerkpostService(db).activeer(werkpost_id, gebruiker.groep_id)
    except ValueError as fout:
        logger.warning("Werkpost activeren mislukt: %s", fout)
        return RedirectResponse(url="/werkposten?fout=actie_mislukt", status_code=303)
    return RedirectResponse(url="/werkposten?bericht=Werkpost+geactiveerd", status_code=303)
