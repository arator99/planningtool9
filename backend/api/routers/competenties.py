import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, verifieer_csrf, haal_actieve_locatie_id
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from services.competentie_service import CompetentieService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/competenties", tags=["competenties"])


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
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    competenties = CompetentieService(db).haal_alle(actieve_locatie_id, ook_inactief=True)
    bericht = request.query_params.get("bericht")
    fout = request.query_params.get("fout")
    return sjablonen.TemplateResponse(
        "pages/competenties/lijst.html",
        _context(request, gebruiker,
                 competenties=competenties,
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
        "pages/competenties/formulier.html",
        _context(request, gebruiker,
                 bewerk_modus=False,
                 comp=None,
                 csrf_token=csrf_token),
    )


@router.post("/nieuw")
def maak_aan(
    naam: str = Form(...),
    beschrijving: str = Form(""),
    categorie: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    try:
        CompetentieService(db).maak_aan(
            locatie_id=actieve_locatie_id,
            naam=naam,
            beschrijving=beschrijving or None,
            categorie=categorie or None,
        )
    except ValueError as fout:
        logger.warning("Competentie aanmaken mislukt: %s", fout)
        return RedirectResponse(url="/competenties/nieuw?fout=aanmaken_mislukt", status_code=303)
    return RedirectResponse(url="/competenties?bericht=Competentie+aangemaakt", status_code=303)


# ------------------------------------------------------------------ #
# Bewerken                                                             #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/bewerk", response_class=HTMLResponse)
def bewerk_formulier(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        comp = CompetentieService(db).haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/competenties?fout=niet_gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/competenties/formulier.html",
        _context(request, gebruiker,
                 bewerk_modus=True,
                 comp=comp,
                 csrf_token=csrf_token),
    )


@router.post("/{uuid}/bewerk")
def bewerk(
    uuid: str,
    naam: str = Form(...),
    beschrijving: str = Form(""),
    categorie: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    svc = CompetentieService(db)
    try:
        comp = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/competenties?fout=niet_gevonden", status_code=303)
    try:
        svc.bewerk(
            competentie_id=comp.id,
            locatie_id=actieve_locatie_id,
            naam=naam,
            beschrijving=beschrijving or None,
            categorie=categorie or None,
        )
    except ValueError as fout:
        logger.warning("Competentie bewerken mislukt: %s", fout)
        return RedirectResponse(url=f"/competenties/{uuid}/bewerk?fout=bewerken_mislukt", status_code=303)
    return RedirectResponse(url="/competenties?bericht=Competentie+opgeslagen", status_code=303)


# ------------------------------------------------------------------ #
# Deactiveren                                                          #
# ------------------------------------------------------------------ #

@router.post("/{uuid}/deactiveer")
def deactiveer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    svc = CompetentieService(db)
    try:
        comp = svc.haal_op_uuid(uuid)
        svc.deactiveer(comp.id, actieve_locatie_id)
    except ValueError as fout:
        logger.warning("Competentie deactiveren mislukt: %s", fout)
        return RedirectResponse(url="/competenties?fout=actie_mislukt", status_code=303)
    return RedirectResponse(url="/competenties?bericht=Competentie+gedeactiveerd", status_code=303)
