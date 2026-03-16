"""Logboek router — audit trail voor beheerders."""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from i18n import maak_vertaler
from api.dependencies import haal_db, vereiste_rol
from api.sjablonen import sjablonen
from models.audit_log import AuditLog
from models.gebruiker import Gebruiker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/logboek", tags=["logboek"])

_PAGINA_GROOTTE = 50

# Bekende actie-codes voor het filter-dropdown
_BEKENDE_ACTIES = [
    "shift.opslaan",
    "shift.verwijderen",
    "verlof.goedkeuren",
    "verlof.weigeren",
    "verlof.intrekken",
    "gebruiker.aanmaken",
    "gebruiker.deactiveren",
    "gebruiker.activeren",
    "hr.wijzigen",
    "planning.publiceren",
    "override.aanmaken",
]


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker, "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


@router.get("", response_class=HTMLResponse)
def toon_logboek(
    request: Request,
    pagina: int = 1,
    actie: str = "",
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
):
    pagina = max(1, pagina)
    offset = (pagina - 1) * _PAGINA_GROOTTE

    query = (
        db.query(AuditLog)
        .filter(AuditLog.locatie_id == gebruiker.locatie_id)
    )
    if actie and actie in _BEKENDE_ACTIES:
        query = query.filter(AuditLog.actie == actie)

    totaal = query.count()
    entries = (
        query
        .order_by(AuditLog.tijdstip.desc())
        .offset(offset)
        .limit(_PAGINA_GROOTTE)
        .all()
    )

    # Laad gebruikersnamen voor de entries
    gebruiker_ids = {e.gebruiker_id for e in entries if e.gebruiker_id}
    gebruikers_map: dict[int, str] = {}
    if gebruiker_ids:
        rijen = db.query(Gebruiker.id, Gebruiker.volledige_naam).filter(Gebruiker.id.in_(gebruiker_ids)).all()
        gebruikers_map = {r.id: r.volledige_naam or r[1] for r in rijen}

    totaal_paginas = max(1, (totaal + _PAGINA_GROOTTE - 1) // _PAGINA_GROOTTE)

    return sjablonen.TemplateResponse(
        "pages/logboek/lijst.html",
        _context(
            request, gebruiker,
            entries=entries,
            gebruikers_map=gebruikers_map,
            huidige_pagina=pagina,
            totaal_paginas=totaal_paginas,
            totaal=totaal,
            actie_filter=actie,
            bekende_acties=_BEKENDE_ACTIES,
        ),
    )
