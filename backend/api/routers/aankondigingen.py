"""Aankondigingen router — systeemberichten beheer (super_beheerder) + publieke partial."""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_csrf_token, haal_db, verifieer_csrf, vereiste_login, vereiste_super_beheerder
from api.sjablonen import sjablonen
from models.aankondiging import AANKONDIGING_SJABLONEN
from models.gebruiker import Gebruiker
from services.aankondiging_service import AankondigingService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["aankondigingen"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


def _parse_dt(waarde: Optional[str]) -> Optional[datetime]:
    """Zet datetime-local string om naar datetime, of None als leeg."""
    if not waarde:
        return None
    try:
        return datetime.fromisoformat(waarde)
    except ValueError:
        return None


# ------------------------------------------------------------------ #
# Publieke partial — geladen via HTMX op elke pagina                  #
# ------------------------------------------------------------------ #

@router.get("/aankondigingen/actief-partial", response_class=HTMLResponse, include_in_schema=False)
def actief_partial(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
):
    """Retourneert de actieve aankondigingen als HTML-partial (voor HTMX in app-layout)."""
    aankondigingen = AankondigingService(db).haal_actief()
    if not aankondigingen:
        return HTMLResponse("")
    return sjablonen.TemplateResponse(
        "components/aankondiging_banner.html",
        {
            "request": request,
            "aankondigingen": aankondigingen,
            "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        },
    )


# ------------------------------------------------------------------ #
# Beheer (super_beheerder only)                                        #
# ------------------------------------------------------------------ #

@router.get("/beheer/aankondigingen", response_class=HTMLResponse)
def toon_lijst(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    aankondigingen = AankondigingService(db).haal_alle()
    return sjablonen.TemplateResponse(
        "pages/aankondigingen/lijst.html",
        _context(request, gebruiker,
                 aankondigingen=aankondigingen,
                 melding=request.query_params.get("melding"),
                 fout=request.query_params.get("fout"),
                 csrf_token=csrf_token),
    )


@router.get("/beheer/aankondigingen/nieuw", response_class=HTMLResponse)
def toon_formulier_nieuw(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    csrf_token: str = Depends(haal_csrf_token),
):
    return sjablonen.TemplateResponse(
        "pages/aankondigingen/formulier.html",
        _context(request, gebruiker,
                 bewerk_modus=False,
                 aankondiging=None,
                 sjablonen_lijst=AANKONDIGING_SJABLONEN,
                 invoer={},
                 fout=None,
                 csrf_token=csrf_token),
    )


@router.post("/beheer/aankondigingen/nieuw")
def verwerk_aanmaken(
    request: Request,
    sjabloon: str = Form("onderhoud_gepland"),
    extra_info: Optional[str] = Form(None),
    ernst: str = Form("info"),
    type: str = Form("banner"),
    gepland_van: Optional[str] = Form(None),
    gepland_tot: Optional[str] = Form(None),
    is_actief: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        AankondigingService(db).maak_aan(
            sjabloon=sjabloon,
            extra_info=extra_info,
            ernst=ernst,
            type=type,
            gepland_van=_parse_dt(gepland_van),
            gepland_tot=_parse_dt(gepland_tot),
            is_actief=bool(is_actief),
            aangemaakt_door_id=gebruiker.id,
        )
    except ValueError as fout:
        return sjablonen.TemplateResponse(
            "pages/aankondigingen/formulier.html",
            _context(request, gebruiker,
                     bewerk_modus=False,
                     aankondiging=None,
                     sjablonen_lijst=AANKONDIGING_SJABLONEN,
                     invoer={"sjabloon": sjabloon, "extra_info": extra_info, "ernst": ernst,
                             "type": type, "gepland_van": gepland_van, "gepland_tot": gepland_tot},
                     fout=str(fout),
                     csrf_token=request.cookies.get("csrf_token", "")),
            status_code=422,
        )
    return RedirectResponse(url="/beheer/aankondigingen?melding=Aankondiging+aangemaakt", status_code=303)


@router.get("/beheer/aankondigingen/{uuid}/bewerk", response_class=HTMLResponse)
def toon_formulier_bewerk(
    request: Request,
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        aankondiging = AankondigingService(db).haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/aankondigingen?fout=Niet+gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/aankondigingen/formulier.html",
        _context(request, gebruiker,
                 bewerk_modus=True,
                 aankondiging=aankondiging,
                 sjablonen_lijst=AANKONDIGING_SJABLONEN,
                 invoer={},
                 fout=None,
                 csrf_token=csrf_token),
    )


@router.post("/beheer/aankondigingen/{uuid}/bewerk")
def verwerk_bewerken(
    request: Request,
    uuid: str,
    sjabloon: str = Form("onderhoud_gepland"),
    extra_info: Optional[str] = Form(None),
    ernst: str = Form("info"),
    type: str = Form("banner"),
    gepland_van: Optional[str] = Form(None),
    gepland_tot: Optional[str] = Form(None),
    is_actief: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = AankondigingService(db)
    try:
        svc.bewerk(
            uuid=uuid,
            sjabloon=sjabloon,
            extra_info=extra_info,
            ernst=ernst,
            type=type,
            gepland_van=_parse_dt(gepland_van),
            gepland_tot=_parse_dt(gepland_tot),
            is_actief=bool(is_actief),
        )
    except ValueError as fout:
        try:
            aankondiging = svc.haal_op_uuid(uuid)
        except ValueError:
            aankondiging = None
        return sjablonen.TemplateResponse(
            "pages/aankondigingen/formulier.html",
            _context(request, gebruiker,
                     bewerk_modus=True,
                     aankondiging=aankondiging,
                     sjablonen_lijst=AANKONDIGING_SJABLONEN,
                     invoer={"sjabloon": sjabloon, "extra_info": extra_info, "ernst": ernst,
                             "type": type, "gepland_van": gepland_van, "gepland_tot": gepland_tot},
                     fout=str(fout),
                     csrf_token=request.cookies.get("csrf_token", "")),
            status_code=422,
        )
    return RedirectResponse(url="/beheer/aankondigingen?melding=Aankondiging+opgeslagen", status_code=303)


@router.post("/beheer/aankondigingen/{uuid}/activeer")
def activeer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        AankondigingService(db).zet_actief(uuid, True)
    except ValueError:
        return RedirectResponse(url="/beheer/aankondigingen?fout=Niet+gevonden", status_code=303)
    return RedirectResponse(url="/beheer/aankondigingen?melding=Aankondiging+geactiveerd", status_code=303)


@router.post("/beheer/aankondigingen/{uuid}/deactiveer")
def deactiveer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        AankondigingService(db).zet_actief(uuid, False)
    except ValueError:
        return RedirectResponse(url="/beheer/aankondigingen?fout=Niet+gevonden", status_code=303)
    return RedirectResponse(url="/beheer/aankondigingen?melding=Aankondiging+gedeactiveerd", status_code=303)


@router.post("/beheer/aankondigingen/{uuid}/verwijder")
def verwijder(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        AankondigingService(db).verwijder(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/aankondigingen?fout=Niet+gevonden", status_code=303)
    return RedirectResponse(url="/beheer/aankondigingen?melding=Aankondiging+verwijderd", status_code=303)
