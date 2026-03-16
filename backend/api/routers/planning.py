import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from i18n import maak_vertaler
from api.dependencies import haal_db, haal_primaire_team_id, heeft_rol_in_team, vereiste_rol, haal_csrf_token, verifieer_csrf, vereiste_login
from api.rate_limiter import limiter
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from services.gebruiker_service import GebruikerService
from services.planning_service import PlanningService
from services.suggestie_service import SuggestieService
from services.validatie_service import ValidatieService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planning", tags=["planning"])


def _huidige_maand() -> tuple[int, int]:
    nu = datetime.now()
    return nu.year, nu.month


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


# ------------------------------------------------------------------ #
# Maandoverzicht                                                       #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def toon_maandplanning(
    request: Request,
    jaar: Optional[int] = None,
    maand: Optional[int] = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    huidig_jaar, huidige_maand = _huidige_maand()
    jaar = jaar or huidig_jaar
    maand = maand or huidige_maand

    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return RedirectResponse(url="/?fout=geen_team", status_code=303)

    grid_data = PlanningService(db).haal_maandgrid(team_id, jaar, maand)
    reserves = GebruikerService(db).haal_reserves(team_id)
    return sjablonen.TemplateResponse(
        "pages/planning/maand.html",
        _context(
            request, gebruiker,
            csrf_token=csrf_token,
            bericht=request.query_params.get("bericht"),
            batch_aantal=request.query_params.get("aantal"),
            fout=request.query_params.get("fout"),
            reserves=reserves,
            **grid_data,
        ),
    )


# ------------------------------------------------------------------ #
# Mijn Planning (read-only, alle rollen)                              #
# ------------------------------------------------------------------ #

@router.get("/mijn", response_class=HTMLResponse)
def toon_mijn_planning(
    request: Request,
    jaar: Optional[int] = None,
    maand: Optional[int] = None,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
):
    huidig_jaar, huidige_maand = _huidige_maand()
    jaar = jaar or huidig_jaar
    maand = maand or huidige_maand

    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return RedirectResponse(url="/?fout=geen_team", status_code=303)

    data = PlanningService(db).haal_eigen_planning(gebruiker.id, team_id, jaar, maand)
    return sjablonen.TemplateResponse(
        "pages/planning/mijn_planning.html",
        _context(request, gebruiker, **data),
    )


# ------------------------------------------------------------------ #
# Cel opslaan (HTMX, geen DOM swap)                                   #
# ------------------------------------------------------------------ #

@router.post("/cel/{gebruiker_uuid}/{datum_str}")
def sla_cel_op(
    gebruiker_uuid: str,
    datum_str: str = Path(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    shift_code: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    """Sla een shift op. Geeft 204 terug zodat HTMX de DOM niet aanpast."""
    try:
        datum = date.fromisoformat(datum_str)
    except ValueError:
        return Response(status_code=422)
    try:
        doel = GebruikerService(db).haal_op_uuid(gebruiker_uuid)
    except ValueError:
        return Response(status_code=404)
    code = shift_code.strip() or None
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return Response(status_code=403)
    try:
        if code:
            PlanningService(db).sla_shift_op(doel.id, team_id, datum, code)
        else:
            PlanningService(db).verwijder_shift(doel.id, team_id, datum)
    except ValueError as fout:
        logger.warning("Cel opslaan mislukt: %s", fout)
        return Response(status_code=422)
    return Response(status_code=204)


# ------------------------------------------------------------------ #
# Publiceren / concept                                                 #
# ------------------------------------------------------------------ #

@router.post("/publiceer")
def publiceer(
    jaar: int = Form(...),
    maand: int = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return RedirectResponse(url=f"/planning?jaar={jaar}&maand={maand}&fout=geen_team", status_code=303)
    PlanningService(db).publiceer_maand(team_id, jaar, maand)
    return RedirectResponse(url=f"/planning?jaar={jaar}&maand={maand}", status_code=303)


@router.post("/concept")
def zet_concept(
    jaar: int = Form(...),
    maand: int = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return RedirectResponse(url=f"/planning?jaar={jaar}&maand={maand}&fout=geen_team", status_code=303)
    PlanningService(db).zet_terug_naar_concept(team_id, jaar, maand)
    return RedirectResponse(url=f"/planning?jaar={jaar}&maand={maand}", status_code=303)


# ------------------------------------------------------------------ #
# HR Validatie (HTMX fragment)                                        #
# ------------------------------------------------------------------ #

@router.get("/valideer", response_class=HTMLResponse)
def valideer_maand(
    request: Request,
    jaar: int,
    maand: int,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    """Draai alle HR validators en geef een HTMX fragment terug."""
    team_id = haal_primaire_team_id(gebruiker.id, db)
    fouten = ValidatieService(db).valideer_maand(team_id, gebruiker.locatie_id, jaar, maand) if team_id else []
    return sjablonen.TemplateResponse(
        "pages/planning/_validatie_paneel.html",
        _context(request, gebruiker, fouten=fouten, jaar=jaar, maand=maand, csrf_token=csrf_token),
    )


# ------------------------------------------------------------------ #
# Suggestie (HTMX fragment)                                           #
# ------------------------------------------------------------------ #

@router.get("/suggestie/{gebruiker_uuid}/{datum_str}", response_class=HTMLResponse)
def toon_suggesties(
    request: Request,
    gebruiker_uuid: str,
    datum_str: str = Path(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    """HTMX fragment: gescoorde shiftcode-suggesties voor één cel."""
    try:
        datum = date.fromisoformat(datum_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="Ongeldige datum")
    try:
        doel = GebruikerService(db).haal_op_uuid(gebruiker_uuid)
    except ValueError:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")

    team_id = haal_primaire_team_id(gebruiker.id, db)
    suggesties = SuggestieService(db).haal_shiftcode_suggesties(
        team_id=team_id,
        locatie_id=gebruiker.locatie_id,
        gebruiker_id=doel.id,
        datum=datum,
    ) if team_id else []
    return sjablonen.TemplateResponse(
        "pages/planning/_suggestie_paneel.html",
        _context(
            request,
            gebruiker,
            suggesties=suggesties,
            gebruiker_uuid=gebruiker_uuid,
            datum_str=datum_str,
            csrf_token=csrf_token,
        ),
    )


@router.post("/auto-invullen")
def auto_invullen(
    request: Request,
    gebruiker_uuid: str = Form(...),
    datum_str: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    """Pas de beste suggestie toe voor één cel. Geeft 204 terug."""
    try:
        datum = date.fromisoformat(datum_str)
    except ValueError:
        return Response(status_code=422)
    try:
        doel = GebruikerService(db).haal_op_uuid(gebruiker_uuid)
    except ValueError:
        return Response(status_code=404)
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return Response(status_code=403)
    try:
        SuggestieService(db).auto_invullen(
            team_id=team_id,
            locatie_id=gebruiker.locatie_id,
            gebruiker_id=doel.id,
            datum=datum,
        )
    except ValueError as fout:
        logger.warning("Auto-invullen mislukt: %s", fout)
        return Response(status_code=422)
    return Response(status_code=204)


@router.post("/batch-auto")
@limiter.limit("2/minute")
def batch_auto_invullen(
    request: Request,
    jaar: int = Form(...),
    maand: int = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    """Batch auto-invullen voor de hele maand op basis van historiek."""
    team_id = haal_primaire_team_id(gebruiker.id, db)
    if not team_id:
        return RedirectResponse(
            url=f"/planning?jaar={jaar}&maand={maand}&fout=geen_team",
            status_code=303,
        )
    try:
        toegepast = SuggestieService(db).batch_auto_invullen(
            team_id=team_id,
            locatie_id=gebruiker.locatie_id,
            jaar=jaar,
            maand=maand,
        )
    except Exception as fout:
        logger.error("Batch auto-invullen mislukt: %s", fout)
        return RedirectResponse(
            url=f"/planning?jaar={jaar}&maand={maand}&fout=batch_mislukt",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/planning?jaar={jaar}&maand={maand}&bericht=batch_klaar&aantal={toegepast}",
        status_code=303,
    )


@router.post("/override", response_class=HTMLResponse)
def maak_override(
    request: Request,
    gebruiker_uuid: str = Form(...),
    datum_str: str = Form(...),
    regel_code: str = Form(...),
    reden: str = Form(...),
    jaar: int = Form(...),
    maand: int = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
    csrf_token: str = Depends(haal_csrf_token),
):
    """Sla een planneroverride op voor een CRITICAL overtreding."""
    try:
        datum = date.fromisoformat(datum_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="Ongeldige datum")
    if regel_code not in ValidatieService(db).haal_validator_codes():
        raise HTTPException(status_code=422, detail="Onbekende regel_code")

    try:
        doel = GebruikerService(db).haal_op_uuid(gebruiker_uuid)
    except ValueError:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")

    team_id = haal_primaire_team_id(gebruiker.id, db)
    if team_id:
        if not heeft_rol_in_team(doel.id, team_id, ("teamlid", "planner"), db):
            raise HTTPException(status_code=403, detail="Gebruiker behoort niet tot dit team")
        try:
            ValidatieService(db).maak_override(
                team_id=team_id,
                gebruiker_id=doel.id,
                datum=datum,
                regel_code=regel_code,
                reden=reden,
                goedgekeurd_door_id=gebruiker.id,
            )
        except ValueError as fout:
            logger.warning("Override mislukt: %s", fout)
    # Hervalideer en geef bijgewerkt paneel terug
    fouten = ValidatieService(db).valideer_maand(team_id, gebruiker.locatie_id, jaar, maand) if team_id else []
    return sjablonen.TemplateResponse(
        "pages/planning/_validatie_paneel.html",
        _context(request, gebruiker, fouten=fouten, jaar=jaar, maand=maand, csrf_token=csrf_token),
    )


# ------------------------------------------------------------------ #
# Reserve beschikbaarheid (HTMX fragment)                              #
# ------------------------------------------------------------------ #

@router.get("/reserve/{reserve_uuid}/beschikbaarheid", response_class=HTMLResponse)
def reserve_beschikbaarheid(
    reserve_uuid: str,
    request: Request,
    jaar: Optional[int] = None,
    maand: Optional[int] = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
):
    """HTMX fragment: shifts van een reserve over alle teams voor de opgegeven maand."""
    if jaar is None or maand is None:
        nu = datetime.now()
        jaar = jaar or nu.year
        maand = maand or nu.month

    from datetime import date as date_type
    import calendar

    datum_van = date_type(jaar, maand, 1)
    datum_tot = date_type(jaar, maand, calendar.monthrange(jaar, maand)[1])

    try:
        reserve = GebruikerService(db).haal_op_uuid(reserve_uuid)
    except ValueError:
        return HTMLResponse("")

    bezetting = GebruikerService(db).haal_reserve_bezetting(reserve.id, datum_van, datum_tot)

    return sjablonen.TemplateResponse(
        "pages/planning/_reserve_beschikbaarheid.html",
        _context(request, gebruiker, reserve=reserve, bezetting=bezetting, jaar=jaar, maand=maand),
    )
