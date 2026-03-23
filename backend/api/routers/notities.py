"""Notities router — mailboxhiërarchie per rol/scope."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, haal_actieve_locatie_id, vereiste_login, haal_csrf_token, verifieer_csrf
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol, GebruikerRolType
from models.lidmaatschap import Lidmaatschap
from models.notitie import PRIORITEITEN
from models.team import Team
from models.locatie import Locatie
from services.notitie_service import NotitieService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notities", tags=["notities"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


def _haal_rollen(gebruiker_id: int, db: Session) -> list[GebruikerRol]:
    """Haal actieve rollen op voor de gebruiker."""
    return (
        db.query(GebruikerRol)
        .filter(
            GebruikerRol.gebruiker_id == gebruiker_id,
            GebruikerRol.is_actief == True,
        )
        .all()
    )


def _medewerkers(db: Session, locatie_id: int | None, eigen_id: int) -> list[Gebruiker]:
    if not locatie_id:
        return []
    return (
        db.query(Gebruiker)
        .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
        .join(Team, Team.id == Lidmaatschap.team_id)
        .filter(
            Team.locatie_id == locatie_id,
            Lidmaatschap.is_actief == True,
            Lidmaatschap.verwijderd_op == None,
            Gebruiker.is_actief == True,
            Gebruiker.id != eigen_id,
        )
        .distinct()
        .order_by(Gebruiker.volledige_naam)
        .all()
    )


def _bouw_stuur_opties(
    gebruiker: Gebruiker,
    admin_rollen: list[GebruikerRol],
    locatie_id: int | None,
    db: Session,
) -> list[dict]:
    """
    Bouw de lijst van mogelijke bestemmingen voor het stuurformulier.
    Elke optie: {'type': 'mailbox'|'gebruiker', 'label': str, 'naar_rol': str|None,
                 'naar_scope_id': int|None}

    Team-rollen (teamlid/planner) worden bepaald via Lidmaatschap.
    Admin-rollen (beheerder/hr) via GebruikerRol.
    """
    opties = []

    # Team-gebaseerde opties via Lidmaatschap
    lidmaatschappen = (
        db.query(Lidmaatschap)
        .filter(
            Lidmaatschap.gebruiker_id == gebruiker.id,
            Lidmaatschap.is_actief == True,
            Lidmaatschap.verwijderd_op == None,
        )
        .all()
    )
    for lid in lidmaatschappen:
        team = db.query(Team).filter(Team.id == lid.team_id).first()
        team_naam = team.naam if team else str(lid.team_id)

        # Elk lid kan naar de planners mailbox van zijn team sturen
        opties.append({
            "type": "mailbox",
            "label": f"Planners — {team_naam}",
            "naar_rol": "planners",
            "naar_scope_id": lid.team_id,
        })

        # Planners kunnen ook naar de beheerders mailbox van hun locatie
        if lid.is_planner and locatie_id:
            locatie = db.query(Locatie).filter(Locatie.id == locatie_id).first()
            locatie_naam = locatie.naam if locatie else str(locatie_id)
            opties.append({
                "type": "mailbox",
                "label": f"Beheerders — {locatie_naam}",
                "naar_rol": "beheerders",
                "naar_scope_id": locatie_id,
            })

    # Admin-rollen via GebruikerRol
    for rol_record in admin_rollen:
        if not rol_record.is_actief:
            continue
        rol_waarde = rol_record.rol.value if isinstance(rol_record.rol, GebruikerRolType) else str(rol_record.rol)
        if rol_waarde == "beheerder":
            opties.append({
                "type": "mailbox",
                "label": "Super-beheerders",
                "naar_rol": "super_beheerders",
                "naar_scope_id": rol_record.scope_locatie_id,
            })

    # Dedupliceer op (naar_rol, naar_scope_id)
    seen: set[tuple] = set()
    uniek: list[dict] = []
    for opt in opties:
        key = (opt["naar_rol"], opt["naar_scope_id"])
        if key not in seen:
            seen.add(key)
            uniek.append(opt)
    return uniek


def _verrijk_mailboxen(
    mailboxen: list[dict],
    db: Session,
) -> list[dict]:
    """Voeg leesbare labels toe aan mailboxen (team/locatienamen opzoeken)."""
    teams_cache: dict[int, Team] = {}
    locaties_cache: dict[int, Locatie] = {}

    for mailbox in mailboxen:
        rol = mailbox["rol"]
        scope_id = mailbox["scope_id"]

        if rol == "planners":
            if scope_id not in teams_cache:
                teams_cache[scope_id] = db.query(Team).filter(Team.id == scope_id).first()
            team = teams_cache[scope_id]
            mailbox["display_label"] = team.naam if team else str(scope_id)
            mailbox["display_code"] = team.code if team else ""
        elif rol == "beheerders":
            if scope_id not in locaties_cache:
                locaties_cache[scope_id] = db.query(Locatie).filter(Locatie.id == scope_id).first()
            locatie = locaties_cache[scope_id]
            mailbox["display_label"] = locatie.naam if locatie else str(scope_id)
            mailbox["display_code"] = locatie.code if locatie else ""
        else:
            mailbox["display_label"] = "Nationaal"
            mailbox["display_code"] = "NAT"

    return mailboxen


@router.get("", response_class=HTMLResponse)
def inbox(
    request: Request,
    tab: str = "persoonlijk",
    gebruiker: Gebruiker = Depends(vereiste_login),
    actieve_locatie_id: int | None = Depends(haal_actieve_locatie_id),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = NotitieService(db)
    admin_rollen = _haal_rollen(gebruiker.id, db)
    alle_inboxen = svc.haal_alle_inboxen(gebruiker.id, admin_rollen, actieve_locatie_id)
    mailboxen = _verrijk_mailboxen(alle_inboxen["mailboxen"], db)
    verzonden = svc.haal_verzonden(gebruiker.id, actieve_locatie_id)

    return sjablonen.TemplateResponse(
        "pages/notities/lijst.html",
        _context(
            request,
            gebruiker,
            persoonlijk=alle_inboxen["persoonlijk"],
            mailboxen=mailboxen,
            verzonden=verzonden,
            medewerkers=_medewerkers(db, actieve_locatie_id, gebruiker.id),
            stuur_opties=_bouw_stuur_opties(gebruiker, admin_rollen, actieve_locatie_id, db),
            prioriteiten=PRIORITEITEN,
            actieve_tab=tab,
            bericht=request.query_params.get("bericht"),
            fout=maak_vertaler(gebruiker.taal)(request.query_params.get("fout", "")) or None,
            csrf_token=csrf_token,
        ),
    )


@router.post("/stuur")
def stuur(
    naar_type: str = Form(...),         # 'gebruiker' | 'mailbox'
    naar_gebruiker_id: Optional[int] = Form(None),
    naar_rol: Optional[str] = Form(None),
    naar_scope_id: Optional[int] = Form(None),
    bericht: str = Form(...),
    prioriteit: str = Form("normaal"),
    gebruiker: Gebruiker = Depends(vereiste_login),
    actieve_locatie_id: int | None = Depends(haal_actieve_locatie_id),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = NotitieService(db)
    try:
        if naar_type == "gebruiker" and naar_gebruiker_id:
            svc.stuur_naar_gebruiker(
                van_id=gebruiker.id,
                naar_gebruiker_id=naar_gebruiker_id,
                locatie_id=actieve_locatie_id,
                bericht=bericht,
                prioriteit=prioriteit,
            )
        elif naar_type == "mailbox" and naar_rol and naar_scope_id:
            svc.stuur_naar_mailbox(
                van_id=gebruiker.id,
                naar_rol=naar_rol,
                naar_scope_id=naar_scope_id,
                locatie_id=actieve_locatie_id,
                bericht=bericht,
                prioriteit=prioriteit,
            )
        else:
            return RedirectResponse(url="/notities?fout=fout.bestemming_ongeldig", status_code=303)
    except ValueError as fout:
        logger.warning("Notitie sturen mislukt: %s", fout)
        return RedirectResponse(url="/notities?fout=fout.actie_mislukt", status_code=303)
    return RedirectResponse(url="/notities?bericht=Bericht+verzonden", status_code=303)


@router.post("/{uuid}/gelezen")
def markeer_gelezen(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        NotitieService(db).markeer_gelezen(uuid, gebruiker.id)
    except ValueError:
        pass
    return RedirectResponse(url="/notities", status_code=303)


@router.post("/alles-gelezen")
def alles_gelezen(
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    NotitieService(db).markeer_alles_gelezen(gebruiker.id, None)
    return RedirectResponse(url="/notities?bericht=Alles+gemarkeerd+als+gelezen", status_code=303)


@router.get("/ongelezen-aantal", response_class=HTMLResponse)
def ongelezen_aantal(
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
):
    """HTMX fragment: badge met ongelezen notities of leeg."""
    admin_rollen = _haal_rollen(gebruiker.id, db)
    aantal = NotitieService(db).haal_ongelezen_totaal(
        gebruiker.id, admin_rollen, None
    )
    if aantal > 0:
        return HTMLResponse(
            f'<span class="inline-flex items-center justify-center w-4 h-4 text-xs font-bold '
            f'text-white bg-red-500 rounded-full">{aantal}</span>'
        )
    return HTMLResponse("")


@router.post("/{uuid}/verwijder")
def verwijder(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        NotitieService(db).verwijder(uuid, gebruiker.id)
    except ValueError as fout:
        logger.warning("Notitie verwijderen mislukt (uuid=%s): %s", uuid, fout)
        return RedirectResponse(url="/notities?tab=verzonden&fout=fout.actie_mislukt", status_code=303)
    return RedirectResponse(url="/notities?tab=verzonden&bericht=Verwijderd", status_code=303)
