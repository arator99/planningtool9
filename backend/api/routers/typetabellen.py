"""Typetabellen beheer — roostersjablonen per locatie (Fase 8)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import haal_csrf_token, haal_db, verifieer_csrf, vereiste_rol
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from models.gebruiker import Gebruiker
from models.planning import Shiftcode
from services.typetabel_service import TypetabelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/typetabellen", tags=["typetabellen"])

DAG_NAMEN = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


# ------------------------------------------------------------------ #
# Overzicht                                                           #
# ------------------------------------------------------------------ #

@router.get("", response_class=HTMLResponse)
def lijst(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    svc = TypetabelService(db, gebruiker.locatie_id)
    tabellen = svc.haal_alle()
    return sjablonen.TemplateResponse(
        "pages/typetabellen/lijst.html",
        _context(
            request, gebruiker,
            tabellen=tabellen,
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
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    csrf_token: str = Depends(haal_csrf_token),
):
    return sjablonen.TemplateResponse(
        "pages/typetabellen/formulier.html",
        _context(request, gebruiker, typetabel=None, csrf_token=csrf_token),
    )


@router.post("/nieuw", response_class=HTMLResponse)
def maak_nieuw(
    request: Request,
    naam: str = Form(...),
    aantal_weken: int = Form(...),
    beschrijving: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        svc = TypetabelService(db, gebruiker.locatie_id)
        tt = svc.maak(naam, aantal_weken, gebruiker.id, beschrijving)
        db.commit()
        return RedirectResponse(f"/typetabellen/{tt.uuid}/grid?bericht=Typetabel+aangemaakt", status_code=303)
    except ValueError as fout:
        db.rollback()
        csrf_token = request.cookies.get("csrf_token", "")
        return sjablonen.TemplateResponse(
            "pages/typetabellen/formulier.html",
            _context(request, gebruiker, typetabel=None, fout=str(fout), csrf_token=csrf_token),
            status_code=422,
        )


# ------------------------------------------------------------------ #
# Bewerken (naam/beschrijving)                                        #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/bewerken", response_class=HTMLResponse)
def bewerken_formulier(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        tt = TypetabelService(db, gebruiker.locatie_id).haal_op_uuid(uuid)
    except ValueError as fout:
        return RedirectResponse(f"/typetabellen?fout={fout}", status_code=303)
    return sjablonen.TemplateResponse(
        "pages/typetabellen/formulier.html",
        _context(request, gebruiker, typetabel=tt, csrf_token=csrf_token),
    )


@router.post("/{uuid}/bewerken", response_class=HTMLResponse)
def bewerk_opslaan(
    uuid: str,
    request: Request,
    naam: str = Form(...),
    aantal_weken: int = Form(...),
    beschrijving: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        svc = TypetabelService(db, gebruiker.locatie_id)
        tt = svc.update(uuid, naam, aantal_weken, beschrijving)
        db.commit()
        return RedirectResponse(f"/typetabellen/{tt.uuid}/grid?bericht=Wijzigingen+opgeslagen", status_code=303)
    except ValueError as fout:
        db.rollback()
        csrf_token = request.cookies.get("csrf_token", "")
        svc2 = TypetabelService(db, gebruiker.locatie_id)
        try:
            tt = svc2.haal_op_uuid(uuid)
        except ValueError:
            tt = None
        return sjablonen.TemplateResponse(
            "pages/typetabellen/formulier.html",
            _context(request, gebruiker, typetabel=tt, fout=str(fout), csrf_token=csrf_token),
            status_code=422,
        )


# ------------------------------------------------------------------ #
# Grid bewerken                                                       #
# ------------------------------------------------------------------ #

@router.get("/{uuid}/grid", response_class=HTMLResponse)
def toon_grid(
    uuid: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    try:
        svc = TypetabelService(db, gebruiker.locatie_id)
        tt = svc.haal_op_uuid(uuid)
    except ValueError as fout:
        return RedirectResponse(f"/typetabellen?fout={fout}", status_code=303)

    grid_dict = svc.bouw_grid_dict(tt)
    # Bouw een 2D lijst voor het template: grid[week_idx][dag_idx] = code | ""
    grid = [
        [grid_dict.get((w + 1, d), "") or "" for d in range(7)]
        for w in range(tt.aantal_weken)
    ]

    beschikbare_codes = (
        db.query(Shiftcode)
        .filter(
            Shiftcode.verwijderd_op.is_(None),
        )
        .filter(
            (Shiftcode.locatie_id == gebruiker.locatie_id) | (Shiftcode.locatie_id.is_(None))
        )
        .order_by(Shiftcode.code)
        .all()
    )

    return sjablonen.TemplateResponse(
        "pages/typetabellen/grid.html",
        _context(
            request, gebruiker,
            typetabel=tt,
            grid=grid,
            dag_namen=DAG_NAMEN,
            beschikbare_codes=beschikbare_codes,
            bericht=request.query_params.get("bericht"),
            fout=request.query_params.get("fout"),
            csrf_token=csrf_token,
        ),
    )


@router.post("/{uuid}/grid/cel", response_class=HTMLResponse)
def update_cel(
    uuid: str,
    request: Request,
    week: int = Form(...),
    dag: int = Form(...),
    shift_code: Optional[str] = Form(None),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    """HTMX endpoint: update één cel, retourneert alleen de bijgewerkte cel."""
    try:
        svc = TypetabelService(db, gebruiker.locatie_id)
        svc.update_cel(uuid, week, dag, shift_code)
        db.commit()
        code = shift_code.strip().upper() if shift_code and shift_code.strip() else ""
        return HTMLResponse(
            f'<input type="text" name="shift_code" value="{code}" maxlength="10" '
            f'class="w-full text-center uppercase border-0 bg-transparent focus:outline-none text-sm" '
            f'hx-post="/typetabellen/{uuid}/grid/cel" hx-include="[name=\'week_{week}_{dag}\']" '
            f'hx-trigger="change" hx-swap="outerHTML" hx-target="this">'
        )
    except ValueError as fout:
        db.rollback()
        return HTMLResponse(f'<span class="text-gevaar text-xs">{fout}</span>', status_code=422)


# ------------------------------------------------------------------ #
# Activeren / kopiëren / verwijderen                                  #
# ------------------------------------------------------------------ #

@router.post("/{uuid}/activeer", response_class=HTMLResponse)
def activeer(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        TypetabelService(db, gebruiker.locatie_id).stel_actief(uuid)
        db.commit()
        return RedirectResponse("/typetabellen?bericht=Typetabel+geactiveerd", status_code=303)
    except ValueError as fout:
        db.rollback()
        return RedirectResponse(f"/typetabellen?fout={fout}", status_code=303)


@router.post("/{uuid}/kopieer", response_class=HTMLResponse)
def kopieer(
    uuid: str,
    nieuwe_naam: str = Form(...),
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        tt = TypetabelService(db, gebruiker.locatie_id).kopieer(uuid, nieuwe_naam, gebruiker.id)
        db.commit()
        return RedirectResponse(f"/typetabellen/{tt.uuid}/grid?bericht=Kopie+aangemaakt", status_code=303)
    except ValueError as fout:
        db.rollback()
        return RedirectResponse(f"/typetabellen?fout={fout}", status_code=303)


@router.post("/{uuid}/verwijder", response_class=HTMLResponse)
def verwijder(
    uuid: str,
    gebruiker: Gebruiker = Depends(vereiste_rol("beheerder")),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    try:
        TypetabelService(db, gebruiker.locatie_id).verwijder(uuid, gebruiker.id)
        db.commit()
        return RedirectResponse("/typetabellen?bericht=Typetabel+verwijderd", status_code=303)
    except ValueError as fout:
        db.rollback()
        return RedirectResponse(f"/typetabellen?fout={fout}", status_code=303)
