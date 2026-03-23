"""Logboek router — audit trail voor beheerders."""
import logging
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from api.dependencies import haal_db, vereiste_beheerder_of_hoger, haal_actieve_locatie_id
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from models.audit_log import AuditLog
from models.gebruiker import Gebruiker
from models.lidmaatschap import Lidmaatschap
from models.team import Team

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/logboek", tags=["logboek"])

_PAGINA_GROOTTE = 50

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
    "adv.aanmaken",
    "adv.bewerken",
    "adv.verwijderen",
    "adv.activeren",
    "typetabel.aanmaken",
    "typetabel.bewerken",
    "typetabel.verwijderen",
    "typetabel.activeren",
    "aankondiging.aanmaken",
    "aankondiging.bewerken",
    "aankondiging.activeren",
    "aankondiging.deactiveren",
    "aankondiging.verwijderen",
    "locatie.aanmaken",
    "locatie.bewerken",
    "locatie.deactiveren",
    "hr.override.opslaan",
    "hr.override.verwijderd",
    "hr.rode_lijn.opslaan",
    "instelling.opslaan",
    "verlof.saldo.aanpassen",
    "verlof.jaar_overdracht",
    "verlof.1_mei_verval",
]


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


@router.get("", response_class=HTMLResponse)
def toon_logboek(
    request: Request,
    pagina: int = Query(1, ge=1),
    actie: str = Query(""),
    van_datum: Optional[date] = Query(None),
    tot_datum: Optional[date] = Query(None),
    filter_gebruiker_id: Optional[int] = Query(None),
    gebruiker: Gebruiker = Depends(vereiste_beheerder_of_hoger),
    db: Session = Depends(haal_db),
    actieve_locatie_id: int = Depends(haal_actieve_locatie_id),
):
    offset = (pagina - 1) * _PAGINA_GROOTTE

    query = db.query(AuditLog).filter(AuditLog.locatie_id == actieve_locatie_id)

    if actie and actie in _BEKENDE_ACTIES:
        query = query.filter(AuditLog.actie == actie)

    if van_datum:
        query = query.filter(AuditLog.tijdstip >= datetime.combine(van_datum, time.min))

    if tot_datum:
        query = query.filter(AuditLog.tijdstip <= datetime.combine(tot_datum, time.max))

    if filter_gebruiker_id:
        query = query.filter(AuditLog.gebruiker_id == filter_gebruiker_id)

    totaal = query.count()
    entries = (
        query
        .order_by(AuditLog.tijdstip.desc())
        .offset(offset)
        .limit(_PAGINA_GROOTTE)
        .all()
    )

    # Gebruikersnamen voor de weergave
    gebruiker_ids = {e.gebruiker_id for e in entries if e.gebruiker_id}
    gebruikers_map: dict[int, str] = {}
    if gebruiker_ids:
        rijen = (
            db.query(Gebruiker.id, Gebruiker.volledige_naam, Gebruiker.gebruikersnaam)
            .filter(Gebruiker.id.in_(gebruiker_ids))
            .all()
        )
        gebruikers_map = {r.id: (r.volledige_naam or r.gebruikersnaam) for r in rijen}

    # Dropdown: alle medewerkers van de locatie
    alle_medewerkers = (
        db.query(Gebruiker.id, Gebruiker.volledige_naam, Gebruiker.gebruikersnaam)
        .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
        .join(Team, Team.id == Lidmaatschap.team_id)
        .filter(
            Team.locatie_id == actieve_locatie_id,
            Lidmaatschap.is_actief == True,
            Lidmaatschap.verwijderd_op == None,
            Gebruiker.is_actief == True,
        )
        .distinct()
        .order_by(Gebruiker.volledige_naam)
        .all()
    )

    totaal_paginas = max(1, (totaal + _PAGINA_GROOTTE - 1) // _PAGINA_GROOTTE)

    return sjablonen.TemplateResponse(
        "pages/logboek/lijst.html",
        _context(
            request,
            gebruiker,
            entries=entries,
            gebruikers_map=gebruikers_map,
            alle_medewerkers=alle_medewerkers,
            huidige_pagina=pagina,
            totaal_paginas=totaal_paginas,
            totaal=totaal,
            actie_filter=actie,
            van_datum_filter=van_datum,
            tot_datum_filter=tot_datum,
            filter_gebruiker_id=filter_gebruiker_id,
            bekende_acties=_BEKENDE_ACTIES,
        ),
    )
