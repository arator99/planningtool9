import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import haal_csrf_token, haal_db, verifieer_csrf, vereiste_rol
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from models.gebruiker import Gebruiker
from models.groep import GebruikerGroep, Groep, GroepConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/groepen", tags=["groepen"])


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
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    groepen = db.query(Groep).order_by(Groep.naam).all()
    return sjablonen.TemplateResponse(
        "pages/groepen/lijst.html",
        _context(request, gebruiker, groepen=groepen, csrf_token=csrf_token),
    )


# ------------------------------------------------------------------ #
# Aanmaken                                                             #
# ------------------------------------------------------------------ #

@router.get("/nieuw", response_class=HTMLResponse)
def nieuw_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    csrf_token: str = Depends(haal_csrf_token),
):
    return sjablonen.TemplateResponse(
        "pages/groepen/formulier.html",
        _context(request, gebruiker, groep=None, csrf_token=csrf_token),
    )


@router.post("", response_class=HTMLResponse)
def maak_aan(
    request: Request,
    naam: str = Form(...),
    code: str = Form(...),
    beschrijving: str = Form(""),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    code = code.upper().strip()
    naam = naam.strip()

    if db.query(Groep).filter(Groep.naam == naam).first():
        return RedirectResponse(url="/groepen/nieuw?fout=naam_bestaat", status_code=303)
    if db.query(Groep).filter(Groep.code == code).first():
        return RedirectResponse(url="/groepen/nieuw?fout=code_bestaat", status_code=303)

    groep = Groep(naam=naam, code=code, beschrijving=beschrijving or None, is_actief=True)
    db.add(groep)
    db.flush()
    config = GroepConfig(groep_id=groep.id)
    db.add(config)
    db.commit()
    logger.info("Groep aangemaakt: %s (%s) door gebruiker %s", naam, code, gebruiker.id)
    return RedirectResponse(url=f"/groepen/{groep.id}/leden", status_code=303)


# ------------------------------------------------------------------ #
# Leden beheren                                                        #
# ------------------------------------------------------------------ #

@router.get("/{groep_id}/leden", response_class=HTMLResponse)
def leden(
    groep_id: int,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    groep = db.query(Groep).filter(Groep.id == groep_id).first()
    if not groep:
        return RedirectResponse(url="/groepen", status_code=303)

    # Huidige koppelingen
    koppelingen = (
        db.query(GebruikerGroep)
        .filter(GebruikerGroep.groep_id == groep_id)
        .all()
    )
    gekoppelde_ids = {k.gebruiker_id: k for k in koppelingen}

    # Alle actieve gebruikers in dezelfde primaire groep
    alle_gebruikers = (
        db.query(Gebruiker)
        .filter(Gebruiker.is_actief == True)
        .order_by(Gebruiker.volledige_naam)
        .all()
    )

    return sjablonen.TemplateResponse(
        "pages/groepen/leden.html",
        _context(
            request,
            gebruiker,
            groep=groep,
            alle_gebruikers=alle_gebruikers,
            gekoppelde_ids=gekoppelde_ids,
            csrf_token=csrf_token,
        ),
    )


@router.post("/{groep_id}/leden/{lid_gebruiker_id}", response_class=HTMLResponse)
def voeg_lid_toe(
    groep_id: int,
    lid_gebruiker_id: int,
    request: Request,
    is_reserve: bool = Form(False),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    lid = db.query(Gebruiker).filter(Gebruiker.id == lid_gebruiker_id).first()
    if not lid:
        return RedirectResponse(url=f"/groepen/{groep_id}/leden?fout=gebruiker_niet_gevonden", status_code=303)

    bestaand = (
        db.query(GebruikerGroep)
        .filter(GebruikerGroep.gebruiker_id == lid_gebruiker_id, GebruikerGroep.groep_id == groep_id)
        .first()
    )
    if bestaand:
        # Update is_reserve indien gewijzigd
        bestaand.is_reserve = is_reserve
    else:
        koppeling = GebruikerGroep(gebruiker_id=lid_gebruiker_id, groep_id=groep_id, is_reserve=is_reserve)
        db.add(koppeling)

    db.commit()
    logger.info("Lid %s toegevoegd aan groep %s (reserve=%s)", lid_gebruiker_id, groep_id, is_reserve)
    return RedirectResponse(url=f"/groepen/{groep_id}/leden", status_code=303)


@router.post("/{groep_id}/leden/{lid_gebruiker_id}/verwijder", response_class=HTMLResponse)
def verwijder_lid(
    groep_id: int,
    lid_gebruiker_id: int,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    koppeling = (
        db.query(GebruikerGroep)
        .filter(GebruikerGroep.gebruiker_id == lid_gebruiker_id, GebruikerGroep.groep_id == groep_id)
        .first()
    )
    if koppeling:
        db.delete(koppeling)
        db.commit()
        logger.info("Lid %s verwijderd uit groep %s", lid_gebruiker_id, groep_id)
    return RedirectResponse(url=f"/groepen/{groep_id}/leden", status_code=303)
