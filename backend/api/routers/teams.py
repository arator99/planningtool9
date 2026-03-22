import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import haal_csrf_token, haal_db, verifieer_csrf, vereiste_rol, haal_actieve_locatie_id, vereiste_beheerder_of_hoger
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from models.audit_log import AuditLog
from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol
from services.team_service import TeamService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])


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
def lijst(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    teams = TeamService(db).haal_alle(actieve_locatie_id)
    # Leden per team laden voor weergave in de lijst
    team_ids = [t.id for t in teams]
    rollen = (
        db.query(GebruikerRol)
        .filter(
            GebruikerRol.scope_id.in_(team_ids),
            GebruikerRol.rol.in_(["teamlid", "planner"]),
            GebruikerRol.is_actief == True,
        )
        .all()
    ) if team_ids else []
    from models.gebruiker import Gebruiker as G
    gebruiker_ids = {r.gebruiker_id for r in rollen}
    gebruikers_map = {
        g.id: g for g in db.query(G).filter(G.id.in_(gebruiker_ids), G.is_actief == True).all()
    } if gebruiker_ids else {}
    leden_per_team: dict[int, list] = {t.id: [] for t in teams}
    for r in rollen:
        if r.gebruiker_id in gebruikers_map:
            leden_per_team[r.scope_id].append(gebruikers_map[r.gebruiker_id])
    return sjablonen.TemplateResponse(
        "pages/teams/lijst.html",
        _context(request, gebruiker, teams=teams,
                 leden_per_team=leden_per_team,
                 bericht=request.query_params.get("bericht"),
                 fout=maak_vertaler(gebruiker.taal)(request.query_params.get("fout", "")) or None,
                 csrf_token=csrf_token),
    )


# ------------------------------------------------------------------ #
# Aanmaken                                                             #
# ------------------------------------------------------------------ #

@router.get("/nieuw", response_class=HTMLResponse)
def nieuw_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    csrf_token: str = Depends(haal_csrf_token),
):
    return sjablonen.TemplateResponse(
        "pages/teams/formulier.html",
        _context(request, gebruiker, team=None, csrf_token=csrf_token),
    )


@router.post("")
def maak_aan(
    naam: str = Form(...),
    code: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        team = TeamService(db).maak_aan(
            naam=naam.strip(),
            code=code.upper().strip(),
            locatie_id=gebruiker.locatie_id,
        )
    except ValueError as fout:
        logger.warning("Team aanmaken mislukt: %s", fout)
        return RedirectResponse(url="/teams/nieuw?fout=fout.aanmaken_mislukt", status_code=303)
    return RedirectResponse(url=f"/teams/{team.uuid}/leden", status_code=303)


# ------------------------------------------------------------------ #
# Bewerken                                                             #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/bewerk", response_class=HTMLResponse)
def bewerk_formulier(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        team = TeamService(db).haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/teams?fout=fout.niet_gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/teams/formulier.html",
        _context(request, gebruiker, team=team, csrf_token=csrf_token),
    )


@router.post("/{uuid}/bewerk")
def bewerk(
    uuid: str,
    naam: str = Form(...),
    code: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = TeamService(db)
    try:
        team = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/teams?fout=fout.niet_gevonden", status_code=303)
    svc.bewerk(team, naam=naam.strip(), code=code.upper().strip())
    return RedirectResponse(url="/teams?bericht=Team+opgeslagen", status_code=303)


# ------------------------------------------------------------------ #
# Leden beheren                                                        #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/leden", response_class=HTMLResponse)
def leden(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = TeamService(db)
    try:
        team = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/teams", status_code=303)

    rollen, gekoppelde_ids = svc.haal_leden(team.id)
    alle_gebruikers = svc.haal_gebruikers_voor_locatie(gebruiker.locatie_id)

    return sjablonen.TemplateResponse(
        "pages/teams/leden.html",
        _context(
            request,
            gebruiker,
            team=team,
            alle_gebruikers=alle_gebruikers,
            gekoppelde_ids=gekoppelde_ids,
            bericht=request.query_params.get("bericht"),
            fout=maak_vertaler(gebruiker.taal)(request.query_params.get("fout", "")) or None,
            csrf_token=csrf_token,
        ),
    )


@router.post("/{uuid}/leden/{lid_gebruiker_id}")
def voeg_lid_toe(
    uuid: str,
    lid_gebruiker_id: int,
    is_reserve: bool = Form(False),
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = TeamService(db)
    try:
        team = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/teams?fout=fout.niet_gevonden", status_code=303)
    try:
        svc.voeg_lid_toe(team.id, lid_gebruiker_id, is_reserve)
    except Exception as fout:
        logger.warning("Lid toevoegen mislukt: %s", fout)
        return RedirectResponse(url=f"/teams/{uuid}/leden?fout=fout.niet_gevonden", status_code=303)
    return RedirectResponse(url=f"/teams/{uuid}/leden?bericht=Lid+toegevoegd", status_code=303)


@router.post("/{uuid}/leden/{lid_gebruiker_id}/verwijder")
def verwijder_lid(
    uuid: str,
    lid_gebruiker_id: int,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = TeamService(db)
    try:
        team = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/teams?fout=fout.niet_gevonden", status_code=303)
    svc.verwijder_lid(team.id, lid_gebruiker_id, verwijderd_door_id=gebruiker.id)
    db.add(AuditLog(
        gebruiker_id=gebruiker.id,
        team_id=team.id,
        locatie_id=gebruiker.locatie_id,
        actie="team.lid_verwijderd",
        doel_type="GebruikerRol",
        doel_id=lid_gebruiker_id,
    ))
    db.commit()
    return RedirectResponse(url=f"/teams/{uuid}/leden?bericht=Lid+verwijderd", status_code=303)
