"""
Beheer Database router — super_beheerder only.

Biedt drie functies:
  GET/POST /beheer/database/backups       — overzicht + handmatige backup
  GET      /beheer/database/backups/{naam}/download — download backup-bestand
  POST     /beheer/database/backups/{naam}/verwijder — verwijder backup
  GET/POST /beheer/database/restore       — restore vanuit backup
  GET      /beheer/database/export        — download JSON-export
  GET/POST /beheer/database/import        — voorvertoning + merge
  POST     /beheer/database/import/uitvoeren — merge uitvoeren
"""

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import haal_csrf_token, haal_db, verifieer_csrf, vereiste_super_beheerder
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from models.gebruiker import Gebruiker
from services.backup_service import BACKUP_DIR, BackupService
from services.database_export_service import DatabaseExportService
from services.database_import_service import DatabaseImportService
from services.sqlite_import_service import SqliteImportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beheer/database", tags=["beheer-database"])

_MAX_UPLOAD_MB = 200


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {
        "request": request,
        "gebruiker": gebruiker,
        "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"),
        **extra,
    }


# ─────────────────────────────────────── Backups — overzicht ──────── #

@router.get("", response_class=HTMLResponse)
@router.get("/backups", response_class=HTMLResponse)
def backups_overzicht(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    csrf_token: str = Depends(haal_csrf_token),
):
    """Overzicht van alle backups met statistieken."""
    backups = BackupService.lijst_backups()
    stats = BackupService.statistieken()
    return sjablonen.TemplateResponse(
        "pages/beheer/database.html",
        _context(
            request, gebruiker,
            actief_tabblad="backups",
            backups=backups,
            stats=stats,
            csrf_token=csrf_token,
            bericht=request.query_params.get("bericht"),
            fout=request.query_params.get("fout"),
        ),
    )


@router.post("/backups/maak")
def maak_handmatige_backup(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    _csrf: None = Depends(verifieer_csrf),
    label: str = Form(""),
):
    """Maak een handmatige backup aan."""
    backup_pad = BackupService.maak_handmatige_backup(label=label)
    if backup_pad:
        return RedirectResponse(
            url="/beheer/database/backups?bericht=backup.gemaakt",
            status_code=303,
        )
    return RedirectResponse(
        url="/beheer/database/backups?fout=backup.mislukt",
        status_code=303,
    )


@router.get("/backups/{naam}/download")
def download_backup(
    naam: str,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
):
    """Download een backup-bestand."""
    # Path traversal beveiliging
    if "/" in naam or "\\" in naam or ".." in naam:
        return RedirectResponse(url="/beheer/database/backups?fout=backup.ongeldig_pad", status_code=303)

    pad = BACKUP_DIR / naam
    if not pad.exists() or not naam.endswith(".dump"):
        return RedirectResponse(url="/beheer/database/backups?fout=backup.niet_gevonden", status_code=303)

    return FileResponse(
        path=str(pad),
        filename=naam,
        media_type="application/octet-stream",
    )


@router.post("/backups/{naam}/verwijder")
def verwijder_backup(
    naam: str,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    _csrf: None = Depends(verifieer_csrf),
):
    """Verwijder een backup-bestand."""
    succes, bericht = BackupService.verwijder_backup(naam)
    if succes:
        return RedirectResponse(url="/beheer/database/backups?bericht=backup.verwijderd", status_code=303)
    logger.warning("Backup verwijderen mislukt: %s", bericht)
    return RedirectResponse(url="/beheer/database/backups?fout=backup.verwijder_mislukt", status_code=303)


# ──────────────────────────────────────────── Restore ─────────────── #

@router.get("/restore", response_class=HTMLResponse)
def restore_pagina(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    csrf_token: str = Depends(haal_csrf_token),
):
    """Restore-pagina: upload een backup om de database te herstellen."""
    backups = BackupService.lijst_backups()
    return sjablonen.TemplateResponse(
        "pages/beheer/database.html",
        _context(
            request, gebruiker,
            actief_tabblad="restore",
            backups=backups,
            csrf_token=csrf_token,
            bericht=request.query_params.get("bericht"),
            fout=request.query_params.get("fout"),
        ),
    )


@router.post("/restore/vanuit/{naam}")
def restore_vanuit_backup(
    naam: str,
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    _csrf: None = Depends(verifieer_csrf),
):
    """Herstel de database vanuit een bestaande backup in de backupmap."""
    if "/" in naam or "\\" in naam or ".." in naam:
        return RedirectResponse(url="/beheer/database/restore?fout=backup.ongeldig_pad", status_code=303)

    pad = BACKUP_DIR / naam
    succes, bericht = BackupService.herstel_backup(pad)
    if succes:
        logger.info("Restore door %s vanuit %s", gebruiker.gebruikersnaam, naam)
        return RedirectResponse(url="/beheer/database/restore?bericht=restore.gelukt", status_code=303)
    logger.error("Restore mislukt door %s: %s", gebruiker.gebruikersnaam, bericht)
    return RedirectResponse(url="/beheer/database/restore?fout=restore.mislukt", status_code=303)


@router.post("/restore/upload")
async def restore_vanuit_upload(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    _csrf: None = Depends(verifieer_csrf),
    bestand: UploadFile = File(...),
):
    """Herstel de database vanuit een geüpload dump-bestand."""
    if not bestand.filename or not bestand.filename.endswith(".dump"):
        return RedirectResponse(url="/beheer/database/restore?fout=restore.ongeldig_bestand", status_code=303)

    # Controleer bestandsgrootte
    inhoud = await bestand.read()
    grootte_mb = len(inhoud) / (1024 * 1024)
    if grootte_mb > _MAX_UPLOAD_MB:
        return RedirectResponse(url="/beheer/database/restore?fout=restore.te_groot", status_code=303)

    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tmp:
        tmp.write(inhoud)
        tmp_pad = Path(tmp.name)

    try:
        succes, bericht = BackupService.herstel_backup(tmp_pad)
    finally:
        tmp_pad.unlink(missing_ok=True)

    if succes:
        logger.info("Upload-restore door %s (%s MB)", gebruiker.gebruikersnaam, round(grootte_mb, 1))
        return RedirectResponse(url="/beheer/database/restore?bericht=restore.gelukt", status_code=303)
    logger.error("Upload-restore mislukt door %s: %s", gebruiker.gebruikersnaam, bericht)
    return RedirectResponse(url="/beheer/database/restore?fout=restore.mislukt", status_code=303)


# ────────────────────────────────────────── Export (JSON) ─────────── #

@router.get("/export")
def exporteer_database(
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    db: Session = Depends(haal_db),
):
    """Download de volledige database als JSON-exportbestand."""
    import tempfile
    from datetime import datetime

    tijdstip = datetime.now().strftime("%Y%m%d_%H%M%S")
    bestandsnaam = f"database_export_{tijdstip}.json"

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as tmp:
        tmp_pad = Path(tmp.name)

    try:
        DatabaseExportService(db).exporteer_naar_bestand(tmp_pad)
        logger.info("Export door %s: %s", gebruiker.gebruikersnaam, bestandsnaam)
        return FileResponse(
            path=str(tmp_pad),
            filename=bestandsnaam,
            media_type="application/json",
            background=None,
        )
    except Exception as fout:
        tmp_pad.unlink(missing_ok=True)
        logger.error("Export mislukt: %s", fout, exc_info=True)
        return RedirectResponse(url="/beheer/database/backups?fout=export.mislukt", status_code=303)


# ─────────────────────────────────────── Import / Merge ───────────── #

@router.get("/import", response_class=HTMLResponse)
def import_pagina(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    csrf_token: str = Depends(haal_csrf_token),
):
    """Import/merge pagina: upload een JSON-exportbestand."""
    return sjablonen.TemplateResponse(
        "pages/beheer/database.html",
        _context(
            request, gebruiker,
            actief_tabblad="import",
            voorvertoning=None,
            sqlite_voorvertoning=None,
            csrf_token=csrf_token,
            bericht=request.query_params.get("bericht"),
            fout=request.query_params.get("fout"),
        ),
    )


@router.post("/import/voorvertoning", response_class=HTMLResponse)
async def import_voorvertoning(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    _csrf: None = Depends(verifieer_csrf),
    csrf_token: str = Depends(haal_csrf_token),
    bestand: UploadFile = File(...),
):
    """Analyseer een JSON-exportbestand en toon een samenvatting vóór import."""
    if not bestand.filename or not bestand.filename.endswith(".json"):
        return sjablonen.TemplateResponse(
            "pages/beheer/database.html",
            _context(
                request, gebruiker,
                actief_tabblad="import",
                voorvertoning=None,
                sqlite_voorvertoning=None,
                csrf_token=csrf_token,
                fout="import.ongeldig_bestand",
            ),
        )

    inhoud = await bestand.read()
    grootte_mb = len(inhoud) / (1024 * 1024)
    if grootte_mb > _MAX_UPLOAD_MB:
        return sjablonen.TemplateResponse(
            "pages/beheer/database.html",
            _context(
                request, gebruiker,
                actief_tabblad="import",
                voorvertoning=None,
                sqlite_voorvertoning=None,
                csrf_token=csrf_token,
                fout="import.te_groot",
            ),
        )

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="wb") as tmp:
        tmp.write(inhoud)
        tmp_pad = Path(tmp.name)

    try:
        voorvertoning = DatabaseImportService.voorvertoning(tmp_pad)
        # Sla tijdelijk bestand op in de temp-map met vaste naam voor de daadwerkelijke import
        import_tijdelijk = Path(tempfile.gettempdir()) / f"import_pending_{gebruiker.id}.json"
        shutil.copy(tmp_pad, import_tijdelijk)
    except ValueError as fout:
        tmp_pad.unlink(missing_ok=True)
        return sjablonen.TemplateResponse(
            "pages/beheer/database.html",
            _context(
                request, gebruiker,
                actief_tabblad="import",
                voorvertoning=None,
                sqlite_voorvertoning=None,
                csrf_token=csrf_token,
                fout="import.ongeldig_formaat",
            ),
        )
    finally:
        tmp_pad.unlink(missing_ok=True)

    return sjablonen.TemplateResponse(
        "pages/beheer/database.html",
        _context(
            request, gebruiker,
            actief_tabblad="import",
            voorvertoning=voorvertoning,
            sqlite_voorvertoning=None,
            csrf_token=csrf_token,
        ),
    )


@router.post("/import/uitvoeren")
def import_uitvoeren(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    _csrf: None = Depends(verifieer_csrf),
):
    """Voer de merge uit op basis van het eerder geüploade JSON-bestand."""
    import tempfile
    import_tijdelijk = Path(tempfile.gettempdir()) / f"import_pending_{gebruiker.id}.json"

    if not import_tijdelijk.exists():
        return RedirectResponse(url="/beheer/database/import?fout=import.geen_bestand", status_code=303)

    try:
        resultaat = DatabaseImportService.merge(import_tijdelijk)
        import_tijdelijk.unlink(missing_ok=True)
        logger.info(
            "Merge door %s: %s nieuw, %s overgeslagen, %s fouten",
            gebruiker.gebruikersnaam,
            resultaat.totaal_nieuw(),
            resultaat.totaal_overgeslagen(),
            len(resultaat.fouten),
        )
        return RedirectResponse(
            url="/beheer/database/import?bericht=import.gelukt",
            status_code=303,
        )
    except Exception as fout:
        import_tijdelijk.unlink(missing_ok=True)
        logger.error("Merge mislukt door %s: %s", gebruiker.gebruikersnaam, fout, exc_info=True)
        return RedirectResponse(url="/beheer/database/import?fout=import.mislukt", status_code=303)


# ─────────────────────────────────── SQLite import (v0.7 databases) ─ #

@router.post("/import/sqlite/voorvertoning", response_class=HTMLResponse)
async def sqlite_import_voorvertoning(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    _csrf: None = Depends(verifieer_csrf),
    csrf_token: str = Depends(haal_csrf_token),
    bestand: UploadFile = File(...),
    doellocatie_code: str = Form(...),
    doellocatie_naam: str = Form(...),
):
    """Analyseer een SQLite .db bestand en toon een samenvatting vóór import."""
    import tempfile

    def _fout_response(fout_code: str):
        return sjablonen.TemplateResponse(
            "pages/beheer/database.html",
            _context(
                request, gebruiker,
                actief_tabblad="import",
                voorvertoning=None,
                sqlite_voorvertoning=None,
                csrf_token=csrf_token,
                fout=fout_code,
            ),
        )

    if not bestand.filename or not bestand.filename.endswith(".db"):
        return _fout_response("sqlite.ongeldig_bestand")

    doellocatie_code = doellocatie_code.strip().upper()
    doellocatie_naam = doellocatie_naam.strip()
    if not doellocatie_code:
        return _fout_response("sqlite.ontbrekende_locatie")

    inhoud = await bestand.read()
    if len(inhoud) / (1024 * 1024) > _MAX_UPLOAD_MB:
        return _fout_response("sqlite.te_groot")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(inhoud)
        tmp_pad = Path(tmp.name)

    tmp_dir = Path(tempfile.gettempdir())
    sqlite_tijdelijk = tmp_dir / f"sqlite_pending_{gebruiker.id}.db"
    sqlite_naam_tijdelijk = tmp_dir / f"sqlite_pending_{gebruiker.id}.naam"
    sqlite_locatie_tijdelijk = tmp_dir / f"sqlite_pending_{gebruiker.id}.locatie"

    try:
        voorvertoning = SqliteImportService.voorvertoning(
            tmp_pad, bestand.filename, doellocatie_code, doellocatie_naam
        )
        shutil.copy(tmp_pad, sqlite_tijdelijk)
        sqlite_naam_tijdelijk.write_text(bestand.filename, encoding="utf-8")
        sqlite_locatie_tijdelijk.write_text(
            f"{doellocatie_code}\n{doellocatie_naam}", encoding="utf-8"
        )
    except Exception as fout:
        logger.error("SQLite voorvertoning mislukt: %s", fout, exc_info=True)
        tmp_pad.unlink(missing_ok=True)
        return _fout_response("sqlite.ongeldig_bestand")
    finally:
        tmp_pad.unlink(missing_ok=True)

    return sjablonen.TemplateResponse(
        "pages/beheer/database.html",
        _context(
            request, gebruiker,
            actief_tabblad="import",
            voorvertoning=None,
            sqlite_voorvertoning=voorvertoning,
            csrf_token=csrf_token,
        ),
    )


@router.post("/import/sqlite/uitvoeren")
def sqlite_import_uitvoeren(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_super_beheerder),
    _csrf: None = Depends(verifieer_csrf),
):
    """Voer de SQLite-import uit op basis van het eerder geüploade .db bestand."""
    import tempfile

    tmp_dir = Path(tempfile.gettempdir())
    sqlite_tijdelijk = tmp_dir / f"sqlite_pending_{gebruiker.id}.db"
    sqlite_naam_tijdelijk = tmp_dir / f"sqlite_pending_{gebruiker.id}.naam"
    sqlite_locatie_tijdelijk = tmp_dir / f"sqlite_pending_{gebruiker.id}.locatie"

    if not sqlite_tijdelijk.exists():
        return RedirectResponse(url="/beheer/database/import?fout=import.geen_bestand", status_code=303)

    bestandsnaam = (
        sqlite_naam_tijdelijk.read_text(encoding="utf-8")
        if sqlite_naam_tijdelijk.exists()
        else sqlite_tijdelijk.name
    )
    locatie_regels = (
        sqlite_locatie_tijdelijk.read_text(encoding="utf-8").splitlines()
        if sqlite_locatie_tijdelijk.exists()
        else []
    )
    doellocatie_code = locatie_regels[0] if locatie_regels else "IMPORT"
    doellocatie_naam = locatie_regels[1] if len(locatie_regels) > 1 else doellocatie_code

    try:
        resultaat = SqliteImportService.importeer(
            sqlite_tijdelijk, bestandsnaam, doellocatie_code, doellocatie_naam
        )
        logger.info(
            "SQLite import door %s (%s → %s): %s nieuw",
            gebruiker.gebruikersnaam, bestandsnaam, doellocatie_code, resultaat.totaal_nieuw(),
        )
        return RedirectResponse(
            url="/beheer/database/import?bericht=sqlite.gelukt",
            status_code=303,
        )
    except Exception as fout:
        logger.error("SQLite import mislukt door %s: %s", gebruiker.gebruikersnaam, fout, exc_info=True)
        return RedirectResponse(url="/beheer/database/import?fout=sqlite.mislukt", status_code=303)
    finally:
        sqlite_tijdelijk.unlink(missing_ok=True)
        sqlite_naam_tijdelijk.unlink(missing_ok=True)
        sqlite_locatie_tijdelijk.unlink(missing_ok=True)
