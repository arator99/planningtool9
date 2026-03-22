import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, verifieer_csrf, vereiste_beheerder_of_hoger, haal_actieve_locatie_id
from api.rate_limiter import limiter
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from models.team import Team
from models.locatie import Locatie
from models.gebruiker_rol import GebruikerRol
from services.gebruiker_service import GebruikerService
from services.competentie_service import CompetentieService
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beheer/gebruikers", tags=["gebruikersbeheer"])


def _log(db: Session, gebruiker_id: int, locatie_id: int, actie: str, doel_id: int | None = None) -> None:
    try:
        db.add(AuditLog(gebruiker_id=gebruiker_id, locatie_id=locatie_id, actie=actie,
                        doel_type="Gebruiker", doel_id=doel_id))
        db.commit()
    except Exception as exc:
        logger.warning("Audit log mislukt (%s): %s", actie, exc)


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    """Basiscontext voor app layout templates."""
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


# ------------------------------------------------------------------ #
# Overzicht                                                            #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def toon_lijst(
    request: Request,
    zoek: str = "",
    rol: str = "",
    status: str = "actief",
    team_id: Optional[int] = None,
    melding: Optional[str] = None,
    fout: Optional[str] = None,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = GebruikerService(db)
    gebruikers = svc.haal_gefilterd(actieve_locatie_id, zoek=zoek, rol=rol, status=status, team_id=team_id)
    totaal_actief = len(svc.haal_actieve_medewerkers(actieve_locatie_id))
    melding_type = "fout" if fout else "ok"
    # Teams en locaties als lookup voor rollen-badges in template
    teams_lijst = db.query(Team).filter(Team.locatie_id == actieve_locatie_id, Team.is_actief == True).order_by(Team.naam).all()
    alle_teams = {t.id: t for t in teams_lijst}
    alle_locaties = {l.id: l for l in db.query(Locatie).all()}
    return sjablonen.TemplateResponse(
        "pages/gebruikers/lijst.html",
        _context(request, gebruiker,
                 gebruikers=gebruikers,
                 totaal_actief=totaal_actief,
                 zoek=zoek,
                 rol=rol,
                 status=status,
                 team_id=team_id,
                 teams_lijst=teams_lijst,
                 melding=fout or melding,
                 melding_type=melding_type,
                 alle_teams=alle_teams,
                 alle_locaties=alle_locaties,
                 csrf_token=csrf_token),
    )


# ------------------------------------------------------------------ #
# Aanmaken                                                             #
# ------------------------------------------------------------------ #

@router.get("/nieuw", response_class=HTMLResponse)
def toon_formulier_nieuw(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    alle_teams = db.query(Team).filter(
        Team.locatie_id == actieve_locatie_id, Team.is_actief == True
    ).order_by(Team.naam).all()
    return sjablonen.TemplateResponse(
        "pages/gebruikers/formulier.html",
        _context(request, gebruiker, bewerk_modus=False, invoer={}, fout=None,
                 csrf_token=csrf_token, alle_teams=alle_teams),
    )


@router.post("/nieuw")
def verwerk_aanmaken(
    request: Request,
    gebruikersnaam: str = Form(...),
    wachtwoord: str = Form(...),
    volledige_naam: str = Form(...),
    voornaam: str = Form(""),
    achternaam: str = Form(""),
    rol: str = Form(...),
    team_id: Optional[int] = Form(None),
    startweek_typedienst: Optional[str] = Form(None),
    is_reserve: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    startweek = int(startweek_typedienst) if startweek_typedienst else None
    invoer = {
        "gebruikersnaam": gebruikersnaam, "volledige_naam": volledige_naam,
        "voornaam": voornaam, "achternaam": achternaam, "rol": rol,
        "startweek_typedienst": startweek_typedienst, "is_reserve": is_reserve,
    }
    try:
        GebruikerService(db).maak_aan(
            locatie_id=actieve_locatie_id,
            gebruikersnaam=gebruikersnaam,
            wachtwoord=wachtwoord,
            volledige_naam=volledige_naam,
            rol=rol,
            voornaam=voornaam or None,
            achternaam=achternaam or None,
            team_id=team_id,
            is_reserve=bool(is_reserve),
            startweek_typedienst=startweek,
        )
    except ValueError as fout:
        alle_teams = db.query(Team).filter(
            Team.locatie_id == actieve_locatie_id, Team.is_actief == True
        ).order_by(Team.naam).all()
        return sjablonen.TemplateResponse(
            "pages/gebruikers/formulier.html",
            _context(request, gebruiker, bewerk_modus=False, invoer=invoer, fout=str(fout),
                     alle_teams=alle_teams),
            status_code=422,
        )
    return RedirectResponse(
        url=f"/beheer/gebruikers?melding={gebruikersnaam}+aangemaakt", status_code=303
    )


# ------------------------------------------------------------------ #
# Bewerken                                                             #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/bewerk", response_class=HTMLResponse)
def toon_formulier_bewerk(
    request: Request,
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = GebruikerService(db)
    try:
        bewerkt = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/gebruikers?fout=Gebruiker+niet+gevonden", status_code=303)
    comp_svc = CompetentieService(db)
    alle_competenties = comp_svc.haal_alle(bewerkt.locatie_id)
    gekoppelde_ids = {k.competentie_id for k in comp_svc.haal_koppelingen(bewerkt.id)}

    alle_teams = db.query(Team).filter(
        Team.locatie_id == bewerkt.locatie_id, Team.is_actief == True
    ).order_by(Team.naam).all()
    team_rollen = {
        r.scope_id: r
        for r in db.query(GebruikerRol).filter(
            GebruikerRol.gebruiker_id == bewerkt.id,
            GebruikerRol.rol.in_(["teamlid", "planner"]),
        ).all()
    }
    alle_locaties = db.query(Locatie).filter(Locatie.is_actief == True).order_by(Locatie.naam).all() \
        if gebruiker.rol == "super_beheerder" else []

    return sjablonen.TemplateResponse(
        "pages/gebruikers/formulier.html",
        _context(request, gebruiker, bewerk_modus=True, bewerkt_gebruiker=bewerkt,
                 invoer={}, fout=None, csrf_token=csrf_token,
                 alle_competenties=alle_competenties,
                 gekoppelde_ids=gekoppelde_ids,
                 alle_teams=alle_teams,
                 team_rollen=team_rollen,
                 alle_locaties=alle_locaties),
    )


@router.post("/{uuid}/bewerk")
def verwerk_bewerken(
    request: Request,
    uuid: str,
    gebruikersnaam: str = Form(...),
    volledige_naam: str = Form(...),
    voornaam: str = Form(""),
    achternaam: str = Form(""),
    rol: str = Form(...),
    startweek_typedienst: Optional[str] = Form(None),
    competentie_ids: list[int] = Form(default=[]),
    nieuwe_locatie_id: Optional[int] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    service = GebruikerService(db)
    try:
        bewerkt = service.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/gebruikers?fout=Gebruiker+niet+gevonden", status_code=303)

    startweek = int(startweek_typedienst) if startweek_typedienst else None
    # super_beheerder mag locatie wijzigen; anderen krijgen de huidige locatie
    locatie_wijziging = nieuwe_locatie_id if gebruiker.rol == "super_beheerder" else None
    invoer = {
        "gebruikersnaam": gebruikersnaam, "volledige_naam": volledige_naam,
        "voornaam": voornaam, "achternaam": achternaam, "rol": rol,
        "startweek_typedienst": startweek_typedienst,
    }
    try:
        service.bewerk(
            gebruiker_id=bewerkt.id,
            locatie_id=bewerkt.locatie_id,
            gebruikersnaam=gebruikersnaam,
            volledige_naam=volledige_naam,
            rol=rol,
            voornaam=voornaam or None,
            achternaam=achternaam or None,
            startweek_typedienst=startweek,
            nieuwe_locatie_id=locatie_wijziging,
        )
    except ValueError as fout:
        comp_svc = CompetentieService(db)
        alle_locaties = db.query(Locatie).filter(Locatie.is_actief == True).order_by(Locatie.naam).all() \
            if gebruiker.rol == "super_beheerder" else []
        return sjablonen.TemplateResponse(
            "pages/gebruikers/formulier.html",
            _context(request, gebruiker, bewerk_modus=True, bewerkt_gebruiker=bewerkt,
                     invoer=invoer, fout=str(fout),
                     alle_competenties=comp_svc.haal_alle(bewerkt.locatie_id),
                     gekoppelde_ids=set(competentie_ids),
                     alle_locaties=alle_locaties),
            status_code=422,
        )

    CompetentieService(db).stel_koppelingen_in(
        gebruiker_id=bewerkt.id,
        locatie_id=bewerkt.locatie_id,
        competentie_ids=competentie_ids,
        niveaus={},
        geldig_tot={},
    )
    return RedirectResponse(
        url=f"/beheer/gebruikers?melding={volledige_naam}+opgeslagen", status_code=303
    )


# ------------------------------------------------------------------ #
# Activeer / Deactiveer                                                #
# ------------------------------------------------------------------ #

@router.post("/{uuid}/deactiveer")
def deactiveer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = GebruikerService(db)
    try:
        bewerkt = svc.haal_op_uuid(uuid)
        svc.deactiveer(bewerkt.id, bewerkt.locatie_id, uitvoerder_id=gebruiker.id)
    except ValueError as fout:
        logger.warning("Deactiveer gebruiker %s mislukt: %s", uuid, fout)
        return RedirectResponse(url="/beheer/gebruikers?fout=actie_mislukt", status_code=303)
    _log(db, gebruiker.id, gebruiker.locatie_id, "gebruiker.deactiveren", bewerkt.id)
    return RedirectResponse(url="/beheer/gebruikers?melding=Gebruiker+gedeactiveerd", status_code=303)


@router.post("/{uuid}/activeer")
def activeer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = GebruikerService(db)
    try:
        bewerkt = svc.haal_op_uuid(uuid)
        svc.activeer(bewerkt.id, bewerkt.locatie_id)
    except ValueError as fout:
        logger.warning("Activeer gebruiker %s mislukt: %s", uuid, fout)
        return RedirectResponse(url="/beheer/gebruikers?fout=actie_mislukt", status_code=303)
    _log(db, gebruiker.id, gebruiker.locatie_id, "gebruiker.activeren", bewerkt.id)
    return RedirectResponse(url="/beheer/gebruikers?melding=Gebruiker+geactiveerd", status_code=303)


# ------------------------------------------------------------------ #
# Wachtwoord reset                                                     #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/wachtwoord", response_class=HTMLResponse)
def toon_wachtwoord_formulier(
    request: Request,
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        bewerkt = GebruikerService(db).haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/gebruikers?fout=Gebruiker+niet+gevonden", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/gebruikers/wachtwoord.html",
        _context(request, gebruiker, bewerkt_gebruiker=bewerkt, fout=None, csrf_token=csrf_token),
    )


@router.post("/{uuid}/wachtwoord")
@limiter.limit("10/minute")
def verwerk_wachtwoord_reset(
    request: Request,
    uuid: str,
    nieuw_wachtwoord: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    service = GebruikerService(db)
    try:
        bewerkt = service.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/beheer/gebruikers?fout=Gebruiker+niet+gevonden", status_code=303)
    try:
        service.reset_wachtwoord(bewerkt.id, bewerkt.locatie_id, nieuw_wachtwoord)
    except ValueError as fout:
        return sjablonen.TemplateResponse(
            "pages/gebruikers/wachtwoord.html",
            _context(request, gebruiker, bewerkt_gebruiker=bewerkt, fout=str(fout)),
            status_code=422,
        )
    return RedirectResponse(
        url="/beheer/gebruikers?melding=Wachtwoord+succesvol+gereset", status_code=303
    )
