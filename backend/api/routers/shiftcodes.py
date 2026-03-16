import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from services.shiftcode_service import ShiftcodeService, SHIFT_TYPES, DAG_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shiftcodes", tags=["shiftcodes"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


@router.get("", response_class=HTMLResponse)
def lijst(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = ShiftcodeService(db)
    shiftcodes = svc.haal_alle(gebruiker.locatie_id)
    werkposten = svc.haal_werkposten(gebruiker.locatie_id)

    # Groepeer per shift_type voor overzicht
    gegroepeerd: dict[str, list] = {}
    for sc in shiftcodes:
        key = sc.shift_type or "overig"
        gegroepeerd.setdefault(key, []).append(sc)

    bericht = request.query_params.get("bericht")
    fout = request.query_params.get("fout")

    return sjablonen.TemplateResponse(
        "pages/shiftcodes/lijst.html",
        _context(request, gebruiker,
                 gegroepeerd=gegroepeerd,
                 werkposten=werkposten,
                 shift_types=SHIFT_TYPES,
                 dag_types=DAG_TYPES,
                 bericht=bericht,
                 fout=fout,
                 csrf_token=csrf_token),
    )


@router.get("/nieuw", response_class=HTMLResponse)
def nieuw_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = ShiftcodeService(db)
    return sjablonen.TemplateResponse(
        "pages/shiftcodes/formulier.html",
        _context(request, gebruiker,
                 sc=None,
                 werkposten=svc.haal_werkposten(gebruiker.locatie_id),
                 shift_types=SHIFT_TYPES,
                 dag_types=DAG_TYPES,
                 csrf_token=csrf_token),
    )


@router.post("/nieuw")
def maak_aan(
    code: str = Form(...),
    shift_type: str = Form(""),
    dag_type: str = Form(""),
    start_uur: str = Form(""),
    eind_uur: str = Form(""),
    werkpost_id: Optional[int] = Form(None),
    is_kritisch: bool = Form(False),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        ShiftcodeService(db).maak_aan(
            locatie_id=gebruiker.locatie_id,
            code=code,
            shift_type=shift_type,
            dag_type=dag_type,
            start_uur=start_uur,
            eind_uur=eind_uur,
            werkpost_id=werkpost_id,
            is_kritisch=is_kritisch,
        )
    except ValueError as fout:
        return RedirectResponse(url=f"/shiftcodes/nieuw?fout={fout}", status_code=303)
    return RedirectResponse(url="/shiftcodes?bericht=Shiftcode+aangemaakt", status_code=303)


@router.get("/{uuid}/bewerk", response_class=HTMLResponse)
def bewerk_formulier(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = ShiftcodeService(db)
    try:
        sc = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/shiftcodes?fout=Niet+gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/shiftcodes/formulier.html",
        _context(request, gebruiker,
                 sc=sc,
                 werkposten=svc.haal_werkposten(gebruiker.locatie_id),
                 shift_types=SHIFT_TYPES,
                 dag_types=DAG_TYPES,
                 csrf_token=csrf_token),
    )


@router.post("/{uuid}/bewerk")
def sla_bewerking_op(
    uuid: str,
    shift_type: str = Form(""),
    dag_type: str = Form(""),
    start_uur: str = Form(""),
    eind_uur: str = Form(""),
    werkpost_id: Optional[int] = Form(None),
    is_kritisch: bool = Form(False),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = ShiftcodeService(db)
    try:
        sc = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/shiftcodes?fout=Niet+gevonden", status_code=303)
    try:
        svc.bewerk(
            shiftcode_id=sc.id,
            locatie_id=gebruiker.locatie_id,
            shift_type=shift_type,
            dag_type=dag_type,
            start_uur=start_uur,
            eind_uur=eind_uur,
            werkpost_id=werkpost_id,
            is_kritisch=is_kritisch,
        )
    except ValueError as fout:
        return RedirectResponse(url=f"/shiftcodes/{uuid}/bewerk?fout={fout}", status_code=303)
    return RedirectResponse(url="/shiftcodes?bericht=Shiftcode+bijgewerkt", status_code=303)


@router.post("/{uuid}/verwijder")
def verwijder(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = ShiftcodeService(db)
    try:
        sc = svc.haal_op_uuid(uuid)
        svc.verwijder(sc.id, gebruiker.locatie_id)
    except ValueError as fout:
        return RedirectResponse(url=f"/shiftcodes?fout={fout}", status_code=303)
    return RedirectResponse(url="/shiftcodes?bericht=Shiftcode+verwijderd", status_code=303)
