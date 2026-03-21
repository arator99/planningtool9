"""ADV beheer — toekenning en overzicht van arbeidsduurverkorting (Fase 8)."""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import haal_csrf_token, haal_db, verifieer_csrf, vereiste_rol
from services.domein.csrf_domein import genereer_csrf_token
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from models.audit_log import AuditLog
from models.gebruiker import Gebruiker
from services.adv_service import AdvService
from services.gebruiker_service import GebruikerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verlof/adv", tags=["adv"])

ADV_TYPE_LABELS = {
    "dag_per_week": "Dag per week",
    "week_per_5_weken": "Week per 5 weken",
}
DAG_NAMEN = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag"]


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


def _log(db: Session, gebruiker_id: int, locatie_id: int, actie: str, doel_id: Optional[int] = None) -> None:
    try:
        db.add(AuditLog(
            gebruiker_id=gebruiker_id, locatie_id=locatie_id,
            actie=actie, doel_type="AdvToekenning", doel_id=doel_id,
        ))
        db.commit()
    except Exception as exc:
        logger.warning("Audit log mislukt (%s): %s", actie, exc)


# ------------------------------------------------------------------ #
# Overzicht                                                           #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def lijst(
    request: Request,
    gebruiker_uuid: Optional[str] = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = AdvService(db, gebruiker.locatie_id)
    filter_uid: Optional[int] = None
    filter_gebruiker = None

    if gebruiker_uuid:
        try:
            filter_gebruiker = GebruikerService(db).haal_op_uuid(gebruiker_uuid)
            filter_uid = filter_gebruiker.id
        except ValueError:
            pass

    toekenningen = svc.haal_alle(gebruiker_id=filter_uid)
    teamleden = GebruikerService(db).haal_actieve_medewerkers(gebruiker.locatie_id)

    return sjablonen.TemplateResponse(
        "pages/adv/lijst.html",
        _context(
            request, gebruiker,
            toekenningen=toekenningen,
            teamleden=teamleden,
            filter_gebruiker=filter_gebruiker,
            filter_gebruiker_uuid=gebruiker_uuid,
            adv_type_labels=ADV_TYPE_LABELS,
            dag_namen=DAG_NAMEN,
            bericht=request.query_params.get("bericht"),
            fout=request.query_params.get("fout"),
            csrf_token=csrf_token,
        ),
    )


# ------------------------------------------------------------------ #
# Nieuw                                                               #
# ------------------------------------------------------------------ #

@router.get("/nieuw", response_class=HTMLResponse)
def nieuw_formulier(
    request: Request,
    voor_uuid: Optional[str] = None,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    voor_gebruiker = None
    if voor_uuid:
        try:
            voor_gebruiker = GebruikerService(db).haal_op_uuid(voor_uuid)
        except ValueError:
            pass

    teamleden = GebruikerService(db).haal_actieve_medewerkers(gebruiker.locatie_id)
    return sjablonen.TemplateResponse(
        "pages/adv/formulier.html",
        _context(
            request, gebruiker,
            toekenning=None,
            voor_gebruiker=voor_gebruiker,
            teamleden=teamleden,
            adv_type_labels=ADV_TYPE_LABELS,
            dag_namen=DAG_NAMEN,
            csrf_token=csrf_token,
        ),
    )


@router.post("/nieuw", response_class=HTMLResponse)
def maak_nieuw(
    request: Request,
    voor_gebruiker_uuid: str = Form(...),
    adv_type: str = Form(...),
    dag_van_week: Optional[int] = Form(None),
    start_datum: date = Form(...),
    eind_datum: Optional[date] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        voor = GebruikerService(db).haal_op_uuid(voor_gebruiker_uuid)
        t = AdvService(db, gebruiker.locatie_id).maak(
            gebruiker_id=voor.id,
            adv_type=adv_type,
            dag_van_week=dag_van_week,
            start_datum=start_datum,
            aangemaakt_door_id=gebruiker.id,
            eind_datum=eind_datum,
        )
        db.commit()
        _log(db, gebruiker.id, gebruiker.locatie_id, "adv_aangemaakt", t.id)
        return RedirectResponse(
            f"/verlof/adv?gebruiker_uuid={voor_gebruiker_uuid}&bericht=ADV-toekenning+aangemaakt",
            status_code=303,
        )
    except ValueError as fout:
        db.rollback()
        csrf_token = genereer_csrf_token(str(gebruiker.id))
        teamleden = GebruikerService(db).haal_actieve_medewerkers(gebruiker.locatie_id)
        try:
            voor_gebruiker = GebruikerService(db).haal_op_uuid(voor_gebruiker_uuid)
        except ValueError:
            voor_gebruiker = None
        return sjablonen.TemplateResponse(
            "pages/adv/formulier.html",
            _context(
                request, gebruiker,
                toekenning=None,
                voor_gebruiker=voor_gebruiker,
                teamleden=teamleden,
                adv_type_labels=ADV_TYPE_LABELS,
                dag_namen=DAG_NAMEN,
                fout=str(fout),
                csrf_token=csrf_token,
            ),
            status_code=422,
        )


# ------------------------------------------------------------------ #
# Bewerken                                                            #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/bewerken", response_class=HTMLResponse)
def bewerken_formulier(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        t = AdvService(db, gebruiker.locatie_id).haal_op_uuid(uuid)
    except ValueError as fout:
        return RedirectResponse(f"/verlof/adv?fout={fout}", status_code=303)

    teamleden = GebruikerService(db).haal_actieve_medewerkers(gebruiker.locatie_id)
    return sjablonen.TemplateResponse(
        "pages/adv/formulier.html",
        _context(
            request, gebruiker,
            toekenning=t,
            voor_gebruiker=t.gebruiker,
            teamleden=teamleden,
            adv_type_labels=ADV_TYPE_LABELS,
            dag_namen=DAG_NAMEN,
            csrf_token=csrf_token,
        ),
    )


@router.post("/{uuid}/bewerken", response_class=HTMLResponse)
def bewerk_opslaan(
    uuid: str,
    request: Request,
    adv_type: str = Form(...),
    dag_van_week: Optional[int] = Form(None),
    start_datum: date = Form(...),
    eind_datum: Optional[date] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        svc = AdvService(db, gebruiker.locatie_id)
        t = svc.update(uuid, adv_type, dag_van_week, start_datum, eind_datum)
        db.commit()
        _log(db, gebruiker.id, gebruiker.locatie_id, "adv_bijgewerkt", t.id)
        return RedirectResponse("/verlof/adv?bericht=ADV-toekenning+bijgewerkt", status_code=303)
    except ValueError as fout:
        db.rollback()
        csrf_token = genereer_csrf_token(str(gebruiker.id))
        try:
            t = AdvService(db, gebruiker.locatie_id).haal_op_uuid(uuid)
            voor_gebruiker = t.gebruiker
        except ValueError:
            t = None
            voor_gebruiker = None
        teamleden = GebruikerService(db).haal_actieve_medewerkers(gebruiker.locatie_id)
        return sjablonen.TemplateResponse(
            "pages/adv/formulier.html",
            _context(
                request, gebruiker,
                toekenning=t,
                voor_gebruiker=voor_gebruiker,
                teamleden=teamleden,
                adv_type_labels=ADV_TYPE_LABELS,
                dag_namen=DAG_NAMEN,
                fout=str(fout),
                csrf_token=csrf_token,
            ),
            status_code=422,
        )


# ------------------------------------------------------------------ #
# Deactiveren / activeren / verwijderen                               #
# ------------------------------------------------------------------ #

@router.post("/{uuid}/deactiveer", response_class=HTMLResponse)
def deactiveer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        AdvService(db, gebruiker.locatie_id).deactiveer(uuid)
        db.commit()
        return RedirectResponse("/verlof/adv?bericht=ADV-toekenning+gedeactiveerd", status_code=303)
    except ValueError as fout:
        db.rollback()
        return RedirectResponse(f"/verlof/adv?fout={fout}", status_code=303)


@router.post("/{uuid}/activeer", response_class=HTMLResponse)
def activeer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        AdvService(db, gebruiker.locatie_id).activeer(uuid)
        db.commit()
        return RedirectResponse("/verlof/adv?bericht=ADV-toekenning+geactiveerd", status_code=303)
    except ValueError as fout:
        db.rollback()
        return RedirectResponse(f"/verlof/adv?fout={fout}", status_code=303)


@router.post("/{uuid}/verwijder", response_class=HTMLResponse)
def verwijder(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "planner")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        AdvService(db, gebruiker.locatie_id).verwijder(uuid, gebruiker.id)
        db.commit()
        _log(db, gebruiker.id, gebruiker.locatie_id, "adv_verwijderd")
        return RedirectResponse("/verlof/adv?bericht=ADV-toekenning+verwijderd", status_code=303)
    except ValueError as fout:
        db.rollback()
        return RedirectResponse(f"/verlof/adv?fout={fout}", status_code=303)
