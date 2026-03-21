"""Account router — persoonlijke instellingen voor de ingelogde gebruiker."""
import json
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler

_WACHTWOORD_FOUT_SLEUTELS = frozenset({
    "geen_match", "huidig_onjuist", "te_zwak",
})
from api.dependencies import haal_db, vereiste_login, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from services.auth_service import AuthService

_SHIFT_TYPES = ("vroeg", "laat", "nacht")
_TOEGESTANE_RANGEN = ("1", "2", "3", "")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account", tags=["account"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


@router.get("/wachtwoord", response_class=HTMLResponse)
def wachtwoord_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_login),
    csrf_token: str = Depends(haal_csrf_token),
):
    t = maak_vertaler(gebruiker.taal)
    fout_sleutel = request.query_params.get("fout")
    fout = t(f"account.wachtwoord.fout.{fout_sleutel}") if fout_sleutel in _WACHTWOORD_FOUT_SLEUTELS else None
    return sjablonen.TemplateResponse(
        "pages/account/wachtwoord.html",
        _context(request, gebruiker,
                 csrf_token=csrf_token,
                 fout=fout,
                 bericht=request.query_params.get("bericht")),
    )


@router.post("/thema")
def thema_wijzigen(
    thema: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    if thema not in ("light", "dark", "systeem"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"fout": "ongeldig thema"})
    gebruiker.thema = thema
    db.commit()
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=200, content={"thema": thema})


@router.post("/taal")
def taal_wijzigen(
    taal: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    if taal not in ("nl", "fr", "en"):
        return RedirectResponse(url="/dashboard", status_code=303)
    gebruiker.taal = taal
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/wachtwoord")
def wachtwoord_wijzigen(
    huidig_wachtwoord: str = Form(...),
    nieuw_wachtwoord: str = Form(...),
    nieuw_wachtwoord_bevestig: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    if nieuw_wachtwoord != nieuw_wachtwoord_bevestig:
        return RedirectResponse(url="/account/wachtwoord?fout=geen_match", status_code=303)
    try:
        AuthService(db).wijzig_wachtwoord(gebruiker.id, huidig_wachtwoord, nieuw_wachtwoord)
    except ValueError as fout:
        # Vaste foutsleutels voorkomen dat exception-tekst in URL-logs terechtkomt.
        sleutel = "huidig_wachtwoord_onjuist" if "onjuist" in str(fout) else "wachtwoord_te_zwak"
        return RedirectResponse(url=f"/account/wachtwoord?fout={sleutel}", status_code=303)
    return RedirectResponse(url="/account/wachtwoord?bericht=Wachtwoord+succesvol+gewijzigd.", status_code=303)


@router.get("/voorkeuren", response_class=HTMLResponse)
def voorkeuren_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_login),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        opgeslagen = json.loads(gebruiker.shift_voorkeuren or "{}")
    except (ValueError, TypeError):
        opgeslagen = {}
    return sjablonen.TemplateResponse(
        "pages/account/voorkeuren.html",
        _context(request, gebruiker,
                 csrf_token=csrf_token,
                 shift_types=_SHIFT_TYPES,
                 voorkeuren=opgeslagen,
                 fout=request.query_params.get("fout"),
                 bericht=request.query_params.get("bericht")),
    )


@router.post("/voorkeuren")
def voorkeuren_opslaan(
    request: Request,
    voorkeur_vroeg: str = Form(""),
    voorkeur_laat: str = Form(""),
    voorkeur_nacht: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    # Valideer: alleen toegestane waarden
    invoer = {"vroeg": voorkeur_vroeg, "laat": voorkeur_laat, "nacht": voorkeur_nacht}
    for shift_type, rang in invoer.items():
        if rang not in _TOEGESTANE_RANGEN:
            return RedirectResponse(url="/account/voorkeuren?fout=ongeldig_formaat", status_code=303)

    # Sla alleen niet-lege voorkeuren op
    schoon = {k: v for k, v in invoer.items() if v}
    gebruiker.shift_voorkeuren = json.dumps(schoon)
    db.commit()
    return RedirectResponse(url="/account/voorkeuren?bericht=voorkeuren_opgeslagen", status_code=303)
