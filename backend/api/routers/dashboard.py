"""Dashboard router — startpagina na inloggen."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from api.dependencies import haal_huidige_gebruiker, haal_csrf_token, haal_db, haal_primaire_team_id, haal_actieve_locatie_id, _heeft_actief_planner_lidmaatschap
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
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    team_id = haal_primaire_team_id(gebruiker.id, db)
    ongelezen = NotitieService(db).haal_ongelezen_totaal(gebruiker.id, gebruiker.rollen, actieve_locatie_id)
    komende_shifts = PlanningService(db).haal_komende_shifts(gebruiker.id, team_id)

    actieve_rollen  = {r.rol for r in gebruiker.rollen if r.is_actief}
    is_planner      = _heeft_actief_planner_lidmaatschap(gebruiker)
    is_super        = "super_beheerder" in actieve_rollen
    is_beheerder    = bool(actieve_rollen & {"beheerder", "super_beheerder"})
    kan_hr          = bool(actieve_rollen & {"beheerder", "hr"})
    kan_planning    = is_planner or is_beheerder
    is_behandelaar  = bool(actieve_rollen & {"beheerder", "hr", "super_beheerder"}) or is_planner
    kan_rapporten   = kan_planning or kan_hr

    pending_verlof = VerlofService(db).haal_pending_count(actieve_locatie_id) if is_behandelaar else 0

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
            "is_super": is_super,
        },
    )
