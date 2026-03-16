"""Locaties router — beheer van productielocaties (super_beheerder only)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_super_beheerder, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from services.locatie_service import LocatieService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/beheer/locaties", tags=["locaties"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


# ------------------------------------------------------------------ #
# Overzicht                                                            #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def toon_lijst(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    locaties = LocatieService(db).haal_alle()
    return sjablonen.TemplateResponse(
        "pages/locaties/lijst.html",
        _context(
            request,
            gebruiker,
            locaties=locaties,
            melding=request.query_params.get("melding"),
            fout=request.query_params.get("fout"),
            csrf_token=csrf_token,
        ),
    )


# ------------------------------------------------------------------ #
# Aanmaken                                                             #
# ------------------------------------------------------------------ #

@router.get("/nieuw", response_class=HTMLResponse)
def toon_formulier_nieuw(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    return sjablonen.TemplateResponse(
        "pages/locaties/formulier.html",
        _context(
            request,
            gebruiker,
            bewerk_modus=False,
            locatie=None,
            invoer={},
            fout=None,
            csrf_token=csrf_token,
        ),
    )


@router.post("/nieuw")
def verwerk_aanmaken(
    naam: str = Form(...),
    code: str = Form(...),
    area_label: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    invoer = {"naam": naam, "code": code, "area_label": area_label}
    try:
        LocatieService(db).maak_aan(naam=naam, code=code, area_label=area_label)
    except ValueError as fout:
        return RedirectResponse(
            url=f"/beheer/locaties/nieuw?fout={fout}", status_code=303
        )
    return RedirectResponse(
        url=f"/beheer/locaties?melding={naam}+aangemaakt", status_code=303
    )


# ------------------------------------------------------------------ #
# Bewerken                                                             #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/bewerk", response_class=HTMLResponse)
def toon_formulier_bewerk(
    request: Request,
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        locatie = LocatieService(db).haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/locaties?fout=Locatie+niet+gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/locaties/formulier.html",
        _context(
            request,
            gebruiker,
            bewerk_modus=True,
            locatie=locatie,
            invoer={},
            fout=None,
            csrf_token=csrf_token,
        ),
    )


@router.post("/{uuid}/bewerk")
def verwerk_bewerken(
    uuid: str,
    naam: str = Form(...),
    area_label: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = LocatieService(db)
    try:
        locatie = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/locaties?fout=Locatie+niet+gevonden", status_code=303)
    try:
        svc.bewerk(locatie_id=locatie.id, naam=naam, area_label=area_label)
    except ValueError as fout:
        return RedirectResponse(
            url=f"/beheer/locaties/{uuid}/bewerk?fout={fout}", status_code=303
        )
    return RedirectResponse(
        url=f"/beheer/locaties?melding={naam}+opgeslagen", status_code=303
    )


# ------------------------------------------------------------------ #
# Deactiveren                                                          #
# ------------------------------------------------------------------ #

@router.post("/{uuid}/deactiveer")
def deactiveer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = LocatieService(db)
    try:
        locatie = svc.haal_op_uuid(uuid)
        svc.deactiveer(locatie.id)
    except ValueError as fout:
        return RedirectResponse(url=f"/beheer/locaties?fout={fout}", status_code=303)
    return RedirectResponse(
        url="/beheer/locaties?melding=Locatie+gedeactiveerd", status_code=303
    )
