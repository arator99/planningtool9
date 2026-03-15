import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_login, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from models.notitie import PRIORITEITEN
from services.notitie_service import NotitieService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notities", tags=["notities"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


def _medewerkers(db: Session, groep_id: int, eigen_id: int) -> list[Gebruiker]:
    return (
        db.query(Gebruiker)
        .filter(Gebruiker.groep_id == groep_id, Gebruiker.is_actief == True, Gebruiker.id != eigen_id)
        .order_by(Gebruiker.volledige_naam)
        .all()
    )


@router.get("", response_class=HTMLResponse)
def inbox(
    request: Request,
    tab: str = "inbox",
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = NotitieService(db)
    return sjablonen.TemplateResponse(
        "pages/notities/lijst.html",
        _context(request, gebruiker,
                 inbox=svc.haal_inbox(gebruiker.id, gebruiker.groep_id),
                 verzonden=svc.haal_verzonden(gebruiker.id, gebruiker.groep_id),
                 medewerkers=_medewerkers(db, gebruiker.groep_id, gebruiker.id),
                 prioriteiten=PRIORITEITEN,
                 actieve_tab=tab,
                 bericht=request.query_params.get("bericht"),
                 fout=request.query_params.get("fout"),
                 csrf_token=csrf_token),
    )


@router.post("/stuur")
def stuur(
    bericht: str = Form(...),
    naar_id: Optional[int] = Form(None),
    prioriteit: str = Form("normaal"),
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        NotitieService(db).stuur(gebruiker.id, gebruiker.groep_id, bericht, naar_id, prioriteit)
    except ValueError as fout:
        return RedirectResponse(url=f"/notities?fout={fout}", status_code=303)
    return RedirectResponse(url="/notities?bericht=Bericht+verzonden", status_code=303)


@router.post("/{notitie_id}/gelezen")
def markeer_gelezen(
    notitie_id: int,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    NotitieService(db).markeer_gelezen(notitie_id, gebruiker.id, gebruiker.groep_id)
    return RedirectResponse(url="/notities", status_code=303)


@router.post("/alles-gelezen")
def alles_gelezen(
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    NotitieService(db).markeer_alles_gelezen(gebruiker.id, gebruiker.groep_id)
    return RedirectResponse(url="/notities?bericht=Alles+gemarkeerd+als+gelezen", status_code=303)


@router.get("/ongelezen-aantal", response_class=HTMLResponse)
def ongelezen_aantal(
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
):
    """HTMX fragment: badge met ongelezen notities of leeg."""
    aantal = NotitieService(db).haal_ongelezen_aantal(gebruiker.id, gebruiker.groep_id)
    if aantal > 0:
        return HTMLResponse(f'<span class="inline-flex items-center justify-center w-4 h-4 text-xs font-bold text-white bg-red-500 rounded-full">{aantal}</span>')
    return HTMLResponse("")


@router.post("/{notitie_id}/verwijder")
def verwijder(
    notitie_id: int,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        NotitieService(db).verwijder(notitie_id, gebruiker.id, gebruiker.groep_id)
    except ValueError as fout:
        return RedirectResponse(url=f"/notities?tab=verzonden&fout={fout}", status_code=303)
    return RedirectResponse(url="/notities?tab=verzonden&bericht=Verwijderd", status_code=303)
