"""Beheer HR router — super_beheerder: CRUD voor nationale HR-defaults."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from models.hr import ERNST_NIVEAUS, RICHTINGEN
from services.hr_service import HRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beheer/hr-nationaal", tags=["beheer-hr"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


@router.get("", response_class=HTMLResponse)
def overzicht(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("super_beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    regels = HRService(db).haal_alle_nationale_regels()

    gegroepeerd: dict[str, list] = {}
    for r in regels:
        gegroepeerd.setdefault(r.ernst_niveau, []).append(r)

    return sjablonen.TemplateResponse(
        "pages/beheer/hr_nationaal.html",
        _context(
            request, gebruiker,
            gegroepeerd=gegroepeerd,
            ernst_niveaus=ERNST_NIVEAUS,
            bericht=request.query_params.get("bericht"),
            fout=maak_vertaler(gebruiker.taal)(request.query_params.get("fout", "")) or None,
            csrf_token=csrf_token,
        ),
    )


@router.get("/nieuw", response_class=HTMLResponse)
def nieuw_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("super_beheerder")),
    csrf_token: str = Depends(haal_csrf_token),
):
    return sjablonen.TemplateResponse(
        "pages/beheer/hr_nationaal_formulier.html",
        _context(
            request, gebruiker,
            regel=None,
            ernst_niveaus=ERNST_NIVEAUS,
            richtingen=RICHTINGEN,
            csrf_token=csrf_token,
        ),
    )


@router.post("")
def maak_aan(
    code: str = Form(...),
    naam: str = Form(...),
    waarde: int = Form(...),
    ernst_niveau: str = Form("WARNING"),
    richting: str = Form("max"),
    eenheid: Optional[str] = Form(None),
    beschrijving: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_rol("super_beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        HRService(db).maak_nationale_regel(
            code=code.upper().strip(),
            naam=naam,
            waarde=waarde,
            ernst_niveau=ernst_niveau,
            richting=richting,
            eenheid=eenheid or None,
            beschrijving=beschrijving or None,
        )
    except ValueError as fout:
        return RedirectResponse(
            url=f"/beheer/hr-nationaal/nieuw?fout={fout}", status_code=303
        )
    return RedirectResponse(url="/beheer/hr-nationaal?bericht=Regel+aangemaakt", status_code=303)


@router.get("/{uuid}/bewerk", response_class=HTMLResponse)
def bewerk_formulier(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("super_beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        regel = HRService(db).haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/hr-nationaal?fout=fout.niet_gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/beheer/hr_nationaal_formulier.html",
        _context(
            request, gebruiker,
            regel=regel,
            ernst_niveaus=ERNST_NIVEAUS,
            richtingen=RICHTINGEN,
            fout=maak_vertaler(gebruiker.taal)(request.query_params.get("fout", "")) or None,
            csrf_token=csrf_token,
        ),
    )


@router.post("/{uuid}/bewerk")
def bewerk(
    uuid: str,
    naam: str = Form(...),
    waarde: int = Form(...),
    ernst_niveau: str = Form("WARNING"),
    richting: str = Form("max"),
    eenheid: Optional[str] = Form(None),
    beschrijving: Optional[str] = Form(None),
    is_actief: bool = Form(False),
    gebruiker: Gebruiker = Depends(vereiste_rol("super_beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = HRService(db)
    try:
        regel = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/hr-nationaal?fout=fout.niet_gevonden", status_code=303)
    try:
        svc.bewerk_nationale_regel(
            regel_id=regel.id,
            naam=naam,
            waarde=waarde,
            ernst_niveau=ernst_niveau,
            richting=richting,
            eenheid=eenheid or None,
            beschrijving=beschrijving or None,
            is_actief=is_actief,
        )
    except ValueError as fout:
        return RedirectResponse(
            url=f"/beheer/hr-nationaal/{uuid}/bewerk?fout={fout}", status_code=303
        )
    return RedirectResponse(url="/beheer/hr-nationaal?bericht=Regel+bijgewerkt", status_code=303)
