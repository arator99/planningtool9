"""Rapporten router — planningsoverzichten, CSV en Excel exports."""
import logging
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token
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
):
    jaar, maand = _huidig_jaar_maand()
    svc = RapportService(db)
    planning_data = svc.maandplanning_overzicht(gebruiker.groep_id, jaar, maand)
    verlof_data = svc.verlof_overzicht(gebruiker.groep_id, jaar)

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
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    svc = RapportService(db)
    planning_data = svc.maandplanning_overzicht(gebruiker.groep_id, jaar, maand)
    verlof_data = svc.verlof_overzicht(gebruiker.groep_id, jaar)
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

    balans_data = BalansService(db).haal_team_balans(gebruiker.groep_id, jaar, maand)
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
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    csv_tekst = RapportService(db).maandplanning_csv(gebruiker.groep_id, jaar, maand)
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
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    try:
        fouten = ValidatieService(db).valideer_maand(gebruiker.groep_id, jaar, maand)
        excel_bytes = ExcelExportService(db).genereer_excel(
            gebruiker.groep_id, jaar, maand, fouten=fouten
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
):
    if not jaar or not maand:
        hj, hm = _huidig_jaar_maand()
        jaar = jaar or hj
        maand = maand or hm

    fouten = ValidatieService(db).valideer_maand(gebruiker.groep_id, jaar, maand)
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

    overrides = RapportService(db).override_audit(gebruiker.groep_id, jaar, maand)
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
):
    medewerkers = RapportService(db).medewerkers_overzicht(gebruiker.groep_id)

    return sjablonen.TemplateResponse(
        "pages/rapporten/medewerkers.html",
        _context(request, gebruiker, medewerkers=medewerkers),
    )
