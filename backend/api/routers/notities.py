import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, haal_primaire_team_id, vereiste_login, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from models.notitie import PRIORITEITEN
from services.notitie_service import NotitieService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notities", tags=["notities"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


def _medewerkers(db: Session, locatie_id: int, eigen_id: int) -> list[Gebruiker]:
    return (
        db.query(Gebruiker)
        .filter(Gebruiker.locatie_id == locatie_id, Gebruiker.is_actief == True, Gebruiker.id != eigen_id)
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
    team_id = haal_primaire_team_id(gebruiker.id, db)
    return sjablonen.TemplateResponse(
        "pages/notities/lijst.html",
        _context(request, gebruiker,
                 inbox=svc.haal_inbox(gebruiker.id, team_id) if team_id else [],
                 verzonden=svc.haal_verzonden(gebruiker.id, team_id) if team_id else [],
                 medewerkers=_medewerkers(db, gebruiker.locatie_id, gebruiker.id),
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
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return RedirectResponse(url="/notities?fout=geen_team", status_code=303)
    try:
        NotitieService(db).stuur(gebruiker.id, team_id, bericht, naar_id, prioriteit)
    except ValueError as fout:
        return RedirectResponse(url=f"/notities?fout={fout}", status_code=303)
    return RedirectResponse(url="/notities?bericht=Bericht+verzonden", status_code=303)


@router.post("/{uuid}/gelezen")
def markeer_gelezen(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = NotitieService(db)
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if team_id:
        try:
            notitie = svc.haal_op_uuid(uuid)
            svc.markeer_gelezen(notitie.id, gebruiker.id, team_id)
        except ValueError:
            pass
    return RedirectResponse(url="/notities", status_code=303)


@router.post("/alles-gelezen")
def alles_gelezen(
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if team_id:
        NotitieService(db).markeer_alles_gelezen(gebruiker.id, team_id)
    return RedirectResponse(url="/notities?bericht=Alles+gemarkeerd+als+gelezen", status_code=303)


@router.get("/ongelezen-aantal", response_class=HTMLResponse)
def ongelezen_aantal(
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
):
    """HTMX fragment: badge met ongelezen notities of leeg."""
    team_id = haal_primaire_team_id(gebruiker.id, db)
    aantal = NotitieService(db).haal_ongelezen_aantal(gebruiker.id, team_id) if team_id else 0
    if aantal > 0:
        return HTMLResponse(f'<span class="inline-flex items-center justify-center w-4 h-4 text-xs font-bold text-white bg-red-500 rounded-full">{aantal}</span>')
    return HTMLResponse("")


@router.post("/{uuid}/verwijder")
def verwijder(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = NotitieService(db)
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return RedirectResponse(url="/notities?tab=verzonden&fout=geen_team", status_code=303)
    try:
        notitie = svc.haal_op_uuid(uuid)
        svc.verwijder(notitie.id, gebruiker.id, team_id)
    except ValueError as fout:
        return RedirectResponse(url=f"/notities?tab=verzonden&fout={fout}", status_code=303)
    return RedirectResponse(url="/notities?tab=verzonden&bericht=Verwijderd", status_code=303)
