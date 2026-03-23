"""Instellingen router — groepsspecifieke app-instellingen."""
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol, haal_csrf_token, verifieer_csrf, haal_actieve_locatie_id
from api.sjablonen import sjablonen
from models.audit_log import AuditLog
from models.gebruiker import Gebruiker
from models.instelling import INSTELLING_SLEUTELS
from services.instelling_service import InstellingService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instellingen", tags=["instellingen"])


def _log(db: Session, gebruiker_id: int, locatie_id: int, actie: str) -> None:
    try:
        db.add(AuditLog(gebruiker_id=gebruiker_id, locatie_id=locatie_id, actie=actie,
                        doel_type="Instelling"))
        db.commit()
    except Exception as exc:
        logger.warning("Audit log mislukt (%s): %s", actie, exc)


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


@router.get("", response_class=HTMLResponse)
def toon_instellingen(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    waarden = InstellingService(db).haal_alle(actieve_locatie_id)
    return sjablonen.TemplateResponse(
        "pages/instellingen/lijst.html",
        _context(
            request, gebruiker,
            waarden=waarden,
            sleutel_meta=INSTELLING_SLEUTELS,
            csrf_token=csrf_token,
            bericht=request.query_params.get("bericht"),
            fout=request.query_params.get("fout"),
        ),
    )


@router.post("/{sleutel:path}")
def sla_instelling_op(
    sleutel: str,
    waarde: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    try:
        InstellingService(db).sla_op(actieve_locatie_id, sleutel, waarde, gebruiker.id)
    except ValueError:
        return RedirectResponse(url="/instellingen?fout=instelling_onbekend", status_code=303)
    except Exception:
        logger.exception("Fout bij opslaan instelling %s", sleutel)
        return RedirectResponse(url="/instellingen?fout=instelling_mislukt", status_code=303)
    _log(db, gebruiker.id, actieve_locatie_id, "instelling.opslaan")
    return RedirectResponse(url="/instellingen?bericht=instelling_opgeslagen", status_code=303)
