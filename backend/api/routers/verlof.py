import logging
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from typing import Optional

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_login, vereiste_rol, haal_csrf_token, verifieer_csrf, heeft_rol_in_locatie
from services.planning_service import PlanningService
from api.sjablonen import sjablonen
from models.gebruiker import Gebruiker
from services.gebruiker_service import GebruikerService
from services.verlof_service import VerlofService, BEHANDELAAR_ROLLEN
from services.verlof_saldo_service import VerlofSaldoService
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verlof", tags=["verlof"])


def _log(db: Session, gebruiker_id: int, locatie_id: int, actie: str, doel_id: int | None = None, doel_type: str = "VerlofAanvraag") -> None:
    try:
        db.add(AuditLog(gebruiker_id=gebruiker_id, locatie_id=locatie_id, actie=actie,
                        doel_type=doel_type, doel_id=doel_id))
        db.commit()
    except Exception as exc:
        logger.warning("Audit log mislukt (%s): %s", actie, exc)


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


# ------------------------------------------------------------------ #
# Overzicht                                                            #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def toon_verlof(
    request: Request,
    status_filter: str = "alle",
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = VerlofService(db)
    is_behandelaar = heeft_rol_in_locatie(gebruiker.id, gebruiker.locatie_id, tuple(BEHANDELAAR_ROLLEN), db)

    alle_aanvragen = svc.haal_alle(gebruiker.locatie_id) if is_behandelaar else svc.haal_eigen(gebruiker.id)
    verlofcodes = svc.haal_verlofcodes()

    if status_filter != "alle":
        aanvragen = [a for a in alle_aanvragen if a.status == status_filter]
    else:
        aanvragen = alle_aanvragen

    aantallen = {
        "alle": len(alle_aanvragen),
        "pending": sum(1 for a in alle_aanvragen if a.status == "pending"),
        "goedgekeurd": sum(1 for a in alle_aanvragen if a.status == "goedgekeurd"),
        "geweigerd": sum(1 for a in alle_aanvragen if a.status == "geweigerd"),
    }

    bericht = request.query_params.get("bericht")
    fout = request.query_params.get("fout")

    return sjablonen.TemplateResponse(
        "pages/verlof/lijst.html",
        _context(request, gebruiker,
                 aanvragen=aanvragen,
                 verlofcodes=verlofcodes,
                 is_behandelaar=is_behandelaar,
                 status_filter=status_filter,
                 aantallen=aantallen,
                 bericht=bericht,
                 fout=fout,
                 csrf_token=csrf_token),
    )


# ------------------------------------------------------------------ #
# Nieuwe aanvraag                                                      #
# ------------------------------------------------------------------ #

@router.get("/nieuw", response_class=HTMLResponse)
def toon_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = VerlofService(db)
    is_behandelaar = heeft_rol_in_locatie(gebruiker.id, gebruiker.locatie_id, tuple(BEHANDELAAR_ROLLEN), db)
    medewerkers = []
    if is_behandelaar:
        medewerkers = GebruikerService(db).haal_actieve_medewerkers(gebruiker.locatie_id)
    saldo_overzicht = VerlofSaldoService(db).bereken_overzicht(
        gebruiker.id, date.today().year
    )
    return sjablonen.TemplateResponse(
        "pages/verlof/formulier.html",
        _context(request, gebruiker,
                 verlofcodes=svc.haal_verlofcodes(),
                 is_behandelaar=is_behandelaar,
                 medewerkers=medewerkers,
                 saldo=saldo_overzicht,
                 fouten=[],
                 csrf_token=csrf_token),
    )


@router.post("/nieuw")
def verwerk_aanvraag(
    request: Request,
    gebruiker_id: Optional[int] = Form(None),
    start_datum: date = Form(...),
    eind_datum: date = Form(...),
    opmerking: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    is_behandelaar = heeft_rol_in_locatie(gebruiker.id, gebruiker.locatie_id, tuple(BEHANDELAAR_ROLLEN), db)
    doel_id = gebruiker_id if (is_behandelaar and gebruiker_id) else gebruiker.id

    try:
        VerlofService(db).maak_aanvraag(
            gebruiker_id=doel_id,
            start_datum=start_datum,
            eind_datum=eind_datum,
            opmerking=opmerking,
            ingediend_door_id=gebruiker.id if doel_id != gebruiker.id else None,
        )
    except ValueError as fout:
        logger.warning("Verlofaanvraag mislukt voor gebruiker %s: %s", gebruiker.id, fout)
        return RedirectResponse(url="/verlof/nieuw?fout=aanvraag_mislukt", status_code=303)

    return RedirectResponse(url="/verlof?bericht=Aanvraag+ingediend", status_code=303)


# ------------------------------------------------------------------ #
# Goedkeuren / weigeren                                               #
# ------------------------------------------------------------------ #

@router.post("/{uuid}/goedkeuren")
def goedkeuren(
    uuid: str,
    code_term: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = VerlofService(db)
    try:
        aanvraag = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/verlof?fout=niet_gevonden", status_code=303)
    try:
        svc.goedkeuren(aanvraag.id, gebruiker.locatie_id, gebruiker.id, code_term or None)
    except ValueError as fout:
        logger.warning("Goedkeuren aanvraag %s mislukt: %s", uuid, fout)
        return RedirectResponse(url="/verlof?fout=actie_mislukt", status_code=303)
    _log(db, gebruiker.id, gebruiker.locatie_id, "verlof.goedkeuren", aanvraag.id)
    return RedirectResponse(url="/verlof?bericht=Aanvraag+goedgekeurd", status_code=303)


@router.post("/{uuid}/weigeren")
def weigeren(
    uuid: str,
    reden: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = VerlofService(db)
    try:
        aanvraag = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/verlof?fout=niet_gevonden", status_code=303)
    try:
        svc.weigeren(aanvraag.id, gebruiker.locatie_id, gebruiker.id, reden)
    except ValueError as fout:
        logger.warning("Weigeren aanvraag %s mislukt: %s", uuid, fout)
        return RedirectResponse(url="/verlof?fout=actie_mislukt", status_code=303)
    _log(db, gebruiker.id, gebruiker.locatie_id, "verlof.weigeren", aanvraag.id)
    return RedirectResponse(url="/verlof?bericht=Aanvraag+geweigerd", status_code=303)


# ------------------------------------------------------------------ #
# Verwijderen (eigen pending)                                          #
# ------------------------------------------------------------------ #

@router.post("/{uuid}/verwijder")
def verwijder(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_login),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = VerlofService(db)
    try:
        aanvraag = svc.haal_op_uuid(uuid)
        svc.verwijder(aanvraag.id, gebruiker.id)
    except ValueError as fout:
        logger.warning("Verwijder aanvraag %s mislukt: %s", uuid, fout)
        return RedirectResponse(url="/verlof?fout=actie_mislukt", status_code=303)
    return RedirectResponse(url="/verlof?bericht=Aanvraag+verwijderd", status_code=303)


# ------------------------------------------------------------------ #
# Bulk goedkeuren                                                      #
# ------------------------------------------------------------------ #

@router.post("/bulk-goedkeuren")
def bulk_goedkeuren(
    aanvraag_ids: list[int] = Form(default=[]),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    svc = VerlofService(db)
    goedgekeurd = 0
    for aanvraag_id in aanvraag_ids:
        try:
            svc.goedkeuren(aanvraag_id, gebruiker.locatie_id, gebruiker.id)
            goedgekeurd += 1
        except ValueError:
            pass
    return RedirectResponse(
        url=f"/verlof?bericht={goedgekeurd}+aanvragen+goedgekeurd&status_filter=pending",
        status_code=303,
    )


# ------------------------------------------------------------------ #
# Verlof maandoverzicht                                               #
# ------------------------------------------------------------------ #

@router.get("/overzicht", response_class=HTMLResponse)
def toon_overzicht(
    request: Request,
    jaar: Optional[int] = None,
    maand: Optional[int] = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
):
    huidig = date.today()
    jaar = jaar or huidig.year
    maand = maand or huidig.month

    data = VerlofService(db).haal_maand_overzicht(gebruiker.locatie_id, jaar, maand)
    navigatie = PlanningService(db).haal_maand_navigatie(jaar, maand)

    return sjablonen.TemplateResponse(
        "pages/verlof/overzicht.html",
        _context(
            request, gebruiker,
            **data,
            jaar=jaar,
            maand=maand,
            **navigatie,
        ),
    )


# ------------------------------------------------------------------ #
# Verlof saldo beheer                                                  #
# ------------------------------------------------------------------ #

@router.get("/saldo", response_class=HTMLResponse)
def toon_saldo_beheer(
    request: Request,
    jaar: Optional[int] = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    huidig_jaar = date.today().year
    jaar = jaar or huidig_jaar
    saldi = VerlofSaldoService(db).haal_alle_saldi(gebruiker.locatie_id, jaar)
    bericht = request.query_params.get("bericht")
    fout = request.query_params.get("fout")

    return sjablonen.TemplateResponse(
        "pages/verlof/saldo_beheer.html",
        _context(request, gebruiker,
                 saldi=saldi,
                 jaar=jaar,
                 huidig_jaar=huidig_jaar,
                 jaren=list(range(huidig_jaar - 2, huidig_jaar + 2)),
                 bericht=bericht,
                 fout=fout,
                 csrf_token=csrf_token),
    )


@router.post("/saldo/aanpassen")
def pas_saldo_aan(
    request: Request,
    gebruiker_id: int = Form(...),
    jaar: int = Form(...),
    veld: str = Form(...),
    nieuwe_waarde: int = Form(...),
    reden: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner", "hr")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        VerlofSaldoService(db).pas_saldo_aan(
            gebruiker_id=gebruiker_id,
            jaar=jaar,
            veld=veld,
            nieuwe_waarde=nieuwe_waarde,
            reden=reden,
            uitgevoerd_door_id=gebruiker.id,
        )
    except ValueError as fout:
        logger.warning("Saldo aanpassen mislukt: %s", fout)
        return RedirectResponse(url=f"/verlof/saldo?jaar={jaar}&fout=saldo_mislukt", status_code=303)
    _log(db, gebruiker.id, gebruiker.locatie_id, "verlof.saldo.aanpassen", doel_type="VerlofSaldo")
    return RedirectResponse(url=f"/verlof/saldo?jaar={jaar}&bericht=Saldo+aangepast", status_code=303)


@router.post("/saldo/jaar-overdracht")
def jaar_overdracht(
    van_jaar: int = Form(...),
    naar_jaar: int = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    stats = VerlofSaldoService(db).voer_jaar_overdracht_uit(
        locatie_id=gebruiker.locatie_id,
        van_jaar=van_jaar,
        naar_jaar=naar_jaar,
        uitgevoerd_door_id=gebruiker.id,
    )
    fouten = stats.get("fouten", [])
    if fouten:
        return RedirectResponse(url=f"/verlof/saldo?jaar={naar_jaar}&fout=jaar_overdracht_deels_mislukt", status_code=303)

    _log(db, gebruiker.id, gebruiker.locatie_id, "verlof.jaar_overdracht", doel_type="VerlofSaldo")
    bericht = (
        f"Overdracht {van_jaar}→{naar_jaar}: "
        f"{stats['aantal_gebruikers']} medewerkers, "
        f"VV {stats['totaal_vv_overgedragen']} dagen, "
        f"KD {stats['totaal_kd_overgedragen']} dagen"
    )
    return RedirectResponse(url=f"/verlof/saldo?jaar={naar_jaar}&bericht={bericht}", status_code=303)


@router.get("/pending-aantal", response_class=HTMLResponse)
def pending_aantal(
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
):
    """HTMX fragment: badge met openstaande verlofaanvragen of leeg."""
    if not gebruiker.locatie_id:
        return HTMLResponse("")
    aantal = VerlofService(db).haal_pending_count(gebruiker.locatie_id)
    if aantal > 0:
        return HTMLResponse(
            f'<span class="inline-flex items-center justify-center w-4 h-4 text-xs font-bold '
            f'text-white bg-orange-500 rounded-full">{aantal}</span>'
        )
    return HTMLResponse("")


@router.post("/saldo/1-mei-verval")
def verval_1_mei(
    jaar: int = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    aantal = VerlofSaldoService(db).verwerk_1_mei_verval(gebruiker.locatie_id, jaar, gebruiker.id)
    _log(db, gebruiker.id, gebruiker.locatie_id, "verlof.1_mei_verval", doel_type="VerlofSaldo")
    bericht = f"1-mei verval verwerkt: {aantal} medewerkers met vervallen overgedragen dagen"
    return RedirectResponse(url=f"/verlof/saldo?jaar={jaar}&bericht={bericht}", status_code=303)
