"""Rapporten router — planningsoverzichten, CSV en Excel exports."""
import logging
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session
from typing import Optional

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, haal_primaire_team_id, haal_actieve_locatie_id
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from services.rapport_service import RapportService
from services.balans_service import BalansService
from services.excel_export_service import ExcelExportService
from services.validatie_service import ValidatieService
from services.planning_service import MAAND_NAMEN

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rapporten", tags=["rapporten"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


def _huidig_jaar_maand() -> tuple[int, int]:
    vandaag = date.today()
    return vandaag.year, vandaag.month


@router.get("", response_class=HTMLResponse)
def overzicht(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    jaar, maand = _huidig_jaar_maand()
    team_id = haal_primaire_team_id(gebruiker.id, db)
    svc = RapportService(db)
    planning_data = svc.maandplanning_overzicht(team_id, jaar, maand) if team_id else {}
    verlof_data = svc.verlof_overzicht(actieve_locatie_id, jaar)

    jaren = list(range(date.today().year - 2, date.today().year + 2))

    return sjablonen.TemplateResponse(
        "pages/rapporten/index.html",
        _context(
            request,
            gebruiker,
            planning_data=planning_data,
            verlof_data=verlof_data,
            geselecteerd_jaar=jaar,
            geselecteerd_maand=maand,
            maand_namen=MAAND_NAMEN,
            jaren=jaren,
            bericht=request.query_params.get("bericht"),
            fout=request.query_params.get("fout"),
            csrf_token=csrf_token,
        ),
    )


@router.get("/maandplanning", response_class=HTMLResponse)
def maandplanning(
    request: Request,
    jaar: int = None,
    maand: int = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    team_id = haal_primaire_team_id(gebruiker.id, db)
    svc = RapportService(db)
    planning_data = svc.maandplanning_overzicht(team_id, jaar, maand) if team_id else {}
    verlof_data = svc.verlof_overzicht(actieve_locatie_id, jaar)
    jaren = list(range(date.today().year - 2, date.today().year + 2))

    return sjablonen.TemplateResponse(
        "pages/rapporten/index.html",
        _context(
            request,
            gebruiker,
            planning_data=planning_data,
            verlof_data=verlof_data,
            geselecteerd_jaar=jaar,
            geselecteerd_maand=maand,
            maand_namen=MAAND_NAMEN,
            jaren=jaren,
            csrf_token=csrf_token,
        ),
    )


@router.get("/balans", response_class=HTMLResponse)
def balans_overzicht(
    request: Request,
    jaar: int = None,
    maand: int = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    team_id = haal_primaire_team_id(gebruiker.id, db)
    balans_data = BalansService(db).haal_team_balans(team_id, jaar, maand) if team_id else {}
    jaren = list(range(date.today().year - 2, date.today().year + 2))

    return sjablonen.TemplateResponse(
        "pages/rapporten/balans.html",
        _context(
            request,
            gebruiker,
            balans_data=balans_data,
            geselecteerd_jaar=jaar,
            geselecteerd_maand=maand,
            maand_namen=MAAND_NAMEN,
            jaren=jaren,
        ),
    )


@router.get("/maandplanning/csv")
def maandplanning_csv(
    jaar: int = None,
    maand: int = None,
    team_id: Optional[int] = Query(None, description="Filter op team-ID; None = primair team"),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    effectief_team_id = team_id or haal_primaire_team_id(gebruiker.id, db)
    if not effectief_team_id:
        return Response(status_code=403)
    csv_tekst = RapportService(db).maandplanning_csv(effectief_team_id, jaar, maand)
    bestandsnaam = f"planning_{jaar}_{maand:02d}.csv"
    return Response(
        content=csv_tekst.encode("utf-8-sig"),  # BOM voor Excel compatibiliteit
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{bestandsnaam}"'},
    )


@router.get("/maandplanning/excel")
def maandplanning_excel(
    jaar: int = None,
    maand: int = None,
    team_id: Optional[int] = Query(None, description="Filter op team-ID; None = primair team"),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    effectief_team_id = team_id or haal_primaire_team_id(gebruiker.id, db)
    if not effectief_team_id:
        return Response(status_code=403)
    try:
        fouten = ValidatieService(db).valideer_maand(effectief_team_id, actieve_locatie_id, jaar, maand)
        excel_bytes = ExcelExportService(db).genereer_excel(
            effectief_team_id, jaar, maand, fouten=fouten
        )
    except Exception as fout:
        logger.error("Excel export mislukt: %s", fout)
        return Response(status_code=500)

    # Bestandsnaam bevat nooit vrije tekst van de gebruiker
    maand_naam = MAAND_NAMEN.get(maand, str(maand))
    bestandsnaam = f"{maand_naam}_{jaar}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{bestandsnaam}"'},
    )


@router.get("/compliance", response_class=HTMLResponse)
def compliance_rapport(
    request: Request,
    jaar: int = None,
    maand: int = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    team_id = haal_primaire_team_id(gebruiker.id, db)
    fouten = ValidatieService(db).valideer_maand(team_id, actieve_locatie_id, jaar, maand) if team_id else []
    jaren = list(range(date.today().year - 2, date.today().year + 2))

    return sjablonen.TemplateResponse(
        "pages/rapporten/compliance.html",
        _context(
            request, gebruiker,
            fouten=fouten,
            geselecteerd_jaar=jaar,
            geselecteerd_maand=maand,
            maand_namen=MAAND_NAMEN,
            jaren=jaren,
        ),
    )


@router.get("/overrides", response_class=HTMLResponse)
def override_audit(
    request: Request,
    jaar: int = None,
    maand: int = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    team_id = haal_primaire_team_id(gebruiker.id, db)
    overrides = RapportService(db).override_audit(team_id, jaar, maand) if team_id else []
    jaren = list(range(date.today().year - 2, date.today().year + 2))

    return sjablonen.TemplateResponse(
        "pages/rapporten/overrides.html",
        _context(
            request, gebruiker,
            overrides=overrides,
            geselecteerd_jaar=jaar,
            geselecteerd_maand=maand,
            maand_namen=MAAND_NAMEN,
            jaren=jaren,
        ),
    )


@router.get("/medewerkers", response_class=HTMLResponse)
def medewerkers_overzicht(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    medewerkers = RapportService(db).medewerkers_overzicht(actieve_locatie_id)

    return sjablonen.TemplateResponse(
        "pages/rapporten/medewerkers.html",
        _context(request, gebruiker, medewerkers=medewerkers),
    )


@router.get("/uren", response_class=HTMLResponse)
def uren_rapport(
    request: Request,
    jaar: int = None,
    maand: int = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    jaren = list(range(date.today().year - 2, date.today().year + 2))
    data = RapportService(db).uren_rapport(actieve_locatie_id, jaar, maand)

    return sjablonen.TemplateResponse(
        "pages/rapporten/uren.html",
        _context(
            request,
            gebruiker,
            uren_data=data,
            geselecteerd_jaar=jaar,
            geselecteerd_maand=maand,
            maand_namen=MAAND_NAMEN,
            jaren=jaren,
        ),
    )


@router.get("/verlof-maandgrid", response_class=HTMLResponse)
def verlof_maandgrid(
    request: Request,
    jaar: int = None,
    maand: int = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    team_id = haal_primaire_team_id(gebruiker.id, db)
    jaren = list(range(date.today().year - 2, date.today().year + 2))
    grid_data = RapportService(db).verlof_maandgrid(team_id, jaar, maand) if team_id else {}

    return sjablonen.TemplateResponse(
        "pages/rapporten/verlof_maandgrid.html",
        _context(
            request,
            gebruiker,
            grid_data=grid_data,
            geselecteerd_jaar=jaar,
            geselecteerd_maand=maand,
            maand_namen=MAAND_NAMEN,
            jaren=jaren,
        ),
    )
