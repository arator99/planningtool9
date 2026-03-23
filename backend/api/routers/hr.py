"""HR router — beheerder: nationale defaults bekijken + lokale overrides instellen."""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, verifieer_csrf, haal_actieve_locatie_id
from api.sjablonen import sjablonen
from models.audit_log import AuditLog
from models.gebruiker import Gebruiker
from models.hr import ERNST_NIVEAUS
from services.hr_service import HRService

logger = logging.getLogger(__name__)


def _log(db: Session, gebruiker_id: int, locatie_id: int, actie: str, doel_id: int | None = None) -> None:
    try:
        db.add(AuditLog(gebruiker_id=gebruiker_id, locatie_id=locatie_id, actie=actie,
                        doel_type="HRRegel", doel_id=doel_id))
        db.commit()
    except Exception as exc:
        logger.warning("Audit log mislukt (%s): %s", actie, exc)

router = APIRouter(prefix="/hr", tags=["hr"])


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


@router.get("", response_class=HTMLResponse)
def overzicht(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder", "hr")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    svc = HRService(db)
    nationale_regels = svc.haal_alle_nationale_regels()
    overrides = {
        o.nationale_regel_id: o
        for o in svc.haal_overrides_voor_locatie(actieve_locatie_id)
    }
    rode_lijn = svc.haal_rode_lijn_config()

    # Bouw gecombineerde weergave: nationale regel + eventuele lokale override
    regels_met_override = []
    for regel in nationale_regels:
        override = overrides.get(regel.id)
        regels_met_override.append({
            "regel": regel,
            "override": override,
            "effectieve_waarde": override.waarde if override else regel.waarde,
            "heeft_override": override is not None,
        })

    # Groepeer op ernst-niveau
    gegroepeerd: dict[str, list] = {}
    for item in regels_met_override:
        niveau = item["regel"].ernst_niveau
        gegroepeerd.setdefault(niveau, []).append(item)

    return sjablonen.TemplateResponse(
        "pages/hr/lijst.html",
        _context(
            request, gebruiker,
            gegroepeerd=gegroepeerd,
            ernst_niveaus=ERNST_NIVEAUS,
            rode_lijn=rode_lijn,
            actieve_locatie_id=actieve_locatie_id,
            bericht=request.query_params.get("bericht"),
            fout=maak_vertaler(gebruiker.taal)(request.query_params.get("fout", "")) or None,
            csrf_token=csrf_token,
        ),
    )


@router.get("/{uuid}/override", response_class=HTMLResponse)
def override_formulier(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    svc = HRService(db)
    try:
        regel = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/hr?fout=fout.niet_gevonden", status_code=303)
    override = svc.haal_override(regel.id, actieve_locatie_id)
    return sjablonen.TemplateResponse(
        "pages/hr/override_formulier.html",
        _context(
            request, gebruiker,
            regel=regel,
            override=override,
            csrf_token=csrf_token,
        ),
    )


@router.post("/{uuid}/override")
def sla_override_op(
    uuid: str,
    waarde: int = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    svc = HRService(db)
    try:
        regel = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/hr?fout=fout.niet_gevonden", status_code=303)
    try:
        svc.sla_override_op(
            nationale_regel_id=regel.id,
            locatie_id=actieve_locatie_id,
            waarde=waarde,
        )
    except ValueError as fout:
        logger.warning("Override opslaan mislukt (uuid=%s): %s", uuid, fout)
        return RedirectResponse(
            url=f"/hr/{uuid}/override?fout=fout.validatie_mislukt", status_code=303
        )
    _log(db, gebruiker.id, actieve_locatie_id, "hr.override.opslaan", regel.id)
    return RedirectResponse(url="/hr?bericht=Override+opgeslagen", status_code=303)


@router.post("/{uuid}/override/verwijder")
def verwijder_override(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    svc = HRService(db)
    try:
        regel = svc.haal_op_uuid(uuid)
    except ValueError:
        return RedirectResponse(url="/hr?fout=fout.niet_gevonden", status_code=303)
    svc.verwijder_override(regel.id, actieve_locatie_id)
    _log(db, gebruiker.id, actieve_locatie_id, "hr.override.verwijderd", regel.id)
    return RedirectResponse(url="/hr?bericht=Override+verwijderd", status_code=303)


@router.post("/rode-lijn")
def sla_rode_lijn_op(
    referentie_datum: date = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    try:
        HRService(db).sla_rode_lijn_config_op(referentie_datum)
    except ValueError as fout:
        logger.warning("Rode lijn opslaan mislukt: %s", fout)
        return RedirectResponse(url="/hr?fout=fout.bewerken_mislukt", status_code=303)
    _log(db, gebruiker.id, actieve_locatie_id, "hr.rode_lijn.opslaan")
    return RedirectResponse(url="/hr?bericht=Rode+lijn+opgeslagen", status_code=303)
