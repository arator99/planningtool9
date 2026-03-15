import logging
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from models.hr import ERNST_NIVEAUS
from services.hr_service import HRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr", tags=["hr"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


@router.get("", response_class=HTMLResponse)
def overzicht(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "hr")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = HRService(db)
    regels = svc.haal_alle_regels(gebruiker.groep_id)
    rode_lijn = svc.haal_rode_lijn(gebruiker.groep_id)

    gegroepeerd = {}
    for r in regels:
        gegroepeerd.setdefault(r.ernst_niveau, []).append(r)

    return sjablonen.TemplateResponse(
        "pages/hr/lijst.html",
        _context(request, gebruiker,
                 gegroepeerd=gegroepeerd,
                 ernst_niveaus=ERNST_NIVEAUS,
                 rode_lijn=rode_lijn,
                 bericht=request.query_params.get("bericht"),
                 fout=request.query_params.get("fout"),
                 csrf_token=csrf_token),
    )


@router.get("/{regel_id}/bewerk", response_class=HTMLResponse)
def bewerk_formulier(
    regel_id: int,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "hr")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    regel = HRService(db).haal_regel(regel_id, gebruiker.groep_id)
    if not regel:
        return RedirectResponse(url="/hr?fout=Niet+gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/hr/formulier.html",
        _context(request, gebruiker, regel=regel, ernst_niveaus=ERNST_NIVEAUS, csrf_token=csrf_token),
    )


@router.post("/{regel_id}/bewerk")
def sla_op(
    regel_id: int,
    waarde: Optional[int] = Form(None),
    waarde_extra: str = Form(""),
    ernst_niveau: str = Form("WARNING"),
    is_actief: bool = Form(False),
    beschrijving: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "hr")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        HRService(db).bewerk_regel(
            regel_id=regel_id,
            groep_id=gebruiker.groep_id,
            waarde=waarde,
            waarde_extra=waarde_extra,
            ernst_niveau=ernst_niveau,
            is_actief=is_actief,
            beschrijving=beschrijving,
        )
    except ValueError as fout:
        return RedirectResponse(url=f"/hr/{regel_id}/bewerk?fout={fout}", status_code=303)
    return RedirectResponse(url="/hr?bericht=Regel+bijgewerkt", status_code=303)


@router.post("/{regel_id}/activeer")
def activeer(
    regel_id: int,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "hr")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        HRService(db).activeer(regel_id, gebruiker.groep_id)
    except ValueError as fout:
        return RedirectResponse(url=f"/hr?fout={fout}", status_code=303)
    return RedirectResponse(url="/hr?bericht=Regel+geactiveerd", status_code=303)


@router.post("/{regel_id}/deactiveer")
def deactiveer(
    regel_id: int,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "hr")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        HRService(db).deactiveer(regel_id, gebruiker.groep_id)
    except ValueError as fout:
        return RedirectResponse(url=f"/hr?fout={fout}", status_code=303)
    return RedirectResponse(url="/hr?bericht=Regel+gedeactiveerd", status_code=303)


@router.post("/rode-lijn")
def sla_rode_lijn_op(
    start_datum: date = Form(...),
    interval_dagen: int = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        HRService(db).sla_rode_lijn_op(gebruiker.groep_id, start_datum, interval_dagen)
    except ValueError as fout:
        return RedirectResponse(url=f"/hr?fout={fout}", status_code=303)
    return RedirectResponse(url="/hr?bericht=Rode+lijn+opgeslagen", status_code=303)
