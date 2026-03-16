"""Dashboard router — startpagina na inloggen."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from api.dependencies import haal_huidige_gebruiker, haal_csrf_token, haal_db, haal_primaire_team_id, heeft_rol_in_locatie
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from services.notitie_service import NotitieService
from services.verlof_service import VerlofService
from services.planning_service import PlanningService

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    gebruiker=Depends(haal_huidige_gebruiker),
    csrf_token: str = Depends(haal_csrf_token),
    db=Depends(haal_db),
):
    team_id = haal_primaire_team_id(gebruiker.id, db)
    ongelezen = NotitieService(db).haal_ongelezen_totaal(gebruiker.id, gebruiker.rollen, gebruiker.locatie_id)
    komende_shifts = PlanningService(db).haal_komende_shifts(gebruiker.id, team_id)

    locatie_id = gebruiker.locatie_id
    is_behandelaar = heeft_rol_in_locatie(gebruiker.id, locatie_id, ("beheerder", "planner", "hr", "super_beheerder"), db)
    is_beheerder    = heeft_rol_in_locatie(gebruiker.id, locatie_id, ("beheerder", "super_beheerder"), db)
    kan_planning    = heeft_rol_in_locatie(gebruiker.id, locatie_id, ("beheerder", "planner"), db)
    kan_hr          = heeft_rol_in_locatie(gebruiker.id, locatie_id, ("beheerder", "hr"), db)
    kan_rapporten   = heeft_rol_in_locatie(gebruiker.id, locatie_id, ("beheerder", "planner", "hr"), db)

    pending_verlof = VerlofService(db).haal_pending_count(locatie_id) if is_behandelaar else 0

    return sjablonen.TemplateResponse(
        "pages/dashboard.html",
        {
            "request": request,
            "gebruiker": gebruiker,
            "t": maak_vertaler(gebruiker.taal or "nl"),
            "csrf_token": csrf_token,
            "ongelezen_notities": ongelezen,
            "komende_shifts": komende_shifts,
            "pending_verlof": pending_verlof,
            "is_behandelaar": is_behandelaar,
            "is_beheerder": is_beheerder,
            "kan_planning": kan_planning,
            "kan_hr": kan_hr,
            "kan_rapporten": kan_rapporten,
        },
    )
