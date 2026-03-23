"""
BackupService — automatische en handmatige PostgreSQL-backups.

Backup strategie:
- Dagelijks:    backup_dagelijks_YYYYMMDD.dump     (1 per dag)
- Wekelijks:    backup_wekelijks_YYYY_WNN.dump     (1 per week)
- Maandelijks:  backup_maandelijks_YYYYMM.dump     (1 per maand)
- Handmatig:    backup_handmatig_YYYYMMDD_HHMMSS.dump
- Pre-restore:  backup_pre_restore_YYYYMMDD_HHMMSS.dump  (automatisch vóór restore/merge)

Opslag: /backups volume (geconfigureerd in docker-compose.yml).
Formaat: PostgreSQL custom format (pg_dump -F c) — compact en supports selective restore.

Vereiste: postgresql-client geïnstalleerd in de app-container (zie Dockerfile).
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))

_DAGELIJKS_PREFIX = "backup_dagelijks_"
_WEKELIJKS_PREFIX = "backup_wekelijks_"
_MAANDELIJKS_PREFIX = "backup_maandelijks_"
_HANDMATIG_PREFIX = "backup_handmatig_"
_PRE_RESTORE_PREFIX = "backup_pre_restore_"

# Bewaarbeleid: hoeveel backups bewaren per type
BEWAAR_DAGELIJKS = 30
BEWAAR_WEKELIJKS = 12
BEWAAR_MAANDELIJKS = 12


def _pg_params() -> dict[str, str]:
    """
    Lees PostgreSQL-verbindingsparameters uit DATABASE_URL.

    Returns:
        Dict met host, port, user, password, dbname.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    # Normaliseer psycopg2-dialect naar standaard postgresql://
    url = database_url.replace("postgresql+psycopg2://", "postgresql://")
    parsed = urlparse(url)
    return {
        "host":     parsed.hostname or "db",
        "port":     str(parsed.port or 5432),
        "user":     parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname":   parsed.path.lstrip("/") or "planningtool",
    }


def _pg_dump(bestemming: Path) -> bool:
    """
    Voer pg_dump uit en sla op als PostgreSQL custom-format dump.

    Args:
        bestemming: Pad naar het doelbestand.

    Returns:
        True bij succes, False bij fout.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    params = _pg_params()
    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]

    commando = [
        "pg_dump",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "--no-owner",
        "--no-acl",
        "-F", "c",           # custom format
        "-f", str(bestemming),
    ]

    try:
        resultaat = subprocess.run(
            commando,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if resultaat.returncode != 0:
            logger.error("pg_dump mislukt: %s", resultaat.stderr)
            return False
        return True
    except FileNotFoundError:
        logger.error("pg_dump niet gevonden. Installeer postgresql-client in de app-container.")
        return False
    except subprocess.TimeoutExpired:
        logger.error("pg_dump timeout (>300s)")
        return False
    except Exception as fout:
        logger.error("pg_dump fout: %s", fout, exc_info=True)
        return False


def _pg_restore(bron: Path) -> bool:
    """
    Voer pg_restore uit om een backup te herstellen.

    Vervangt de volledige database (--clean --if-exists).

    Args:
        bron: Pad naar het te herstellen dump-bestand.

    Returns:
        True bij succes, False bij fout.
    """
    params = _pg_params()
    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]

    commando = [
        "pg_restore",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        str(bron),
    ]

    try:
        resultaat = subprocess.run(
            commando,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if resultaat.returncode != 0:
            # pg_restore retourneert soms exitcode != 0 bij niet-kritische warnings
            if resultaat.stderr and "error" in resultaat.stderr.lower():
                logger.error("pg_restore fout: %s", resultaat.stderr)
                return False
            logger.warning("pg_restore warnings: %s", resultaat.stderr)
        return True
    except FileNotFoundError:
        logger.error("pg_restore niet gevonden. Installeer postgresql-client in de app-container.")
        return False
    except subprocess.TimeoutExpired:
        logger.error("pg_restore timeout (>600s)")
        return False
    except Exception as fout:
        logger.error("pg_restore fout: %s", fout, exc_info=True)
        return False


def _opruimen(prefix: str, max_bewaren: int) -> None:
    """
    Verwijder oudste backups van een bepaald type als het maximum bereikt is.

    Args:
        prefix:      Bestandsnaam-prefix (bijv. 'backup_dagelijks_').
        max_bewaren: Maximum aantal te bewaren backups van dit type.
    """
    bestanden = sorted(BACKUP_DIR.glob(f"{prefix}*.dump"))
    te_verwijderen = bestanden[:max(0, len(bestanden) - max_bewaren)]
    for bestand in te_verwijderen:
        try:
            bestand.unlink()
            logger.info("Oud backup verwijderd: %s", bestand.name)
        except Exception as fout:
            logger.warning("Kon %s niet verwijderen: %s", bestand.name, fout)


# ──────────────────────────────────────────────── publieke methodes ── #

class BackupService:
    """Service voor automatische en handmatige PostgreSQL-backups."""

    # ── Automatisch (bij startup) ────────────────────────────────────── #

    @classmethod
    def voer_automatische_backups_uit(cls) -> tuple[bool, bool, bool]:
        """
        Controleer bij startup of de dagelijkse/wekelijkse/maandelijkse backup
        al bestaat en maak die aan als dat niet zo is.

        Returns:
            Tuple (dagelijks_gemaakt, wekelijks_gemaakt, maandelijks_gemaakt).
        """
        nu = datetime.now()
        dagelijks = cls._maak_dagelijkse_backup(nu)
        wekelijks = cls._maak_wekelijkse_backup(nu)
        maandelijks = cls._maak_maandelijkse_backup(nu)
        return dagelijks, wekelijks, maandelijks

    @classmethod
    def _maak_dagelijkse_backup(cls, nu: datetime) -> bool:
        """Maak dagelijkse backup als die nog niet bestaat voor vandaag."""
        naam = f"{_DAGELIJKS_PREFIX}{nu.strftime('%Y%m%d')}.dump"
        pad = BACKUP_DIR / naam
        if pad.exists():
            logger.debug("Dagelijkse backup bestaat al: %s", naam)
            return False
        succes = _pg_dump(pad)
        if succes:
            grootte = pad.stat().st_size / (1024 * 1024)
            logger.info("Dagelijkse backup aangemaakt: %s (%.1f MB)", naam, grootte)
            _opruimen(_DAGELIJKS_PREFIX, BEWAAR_DAGELIJKS)
        return succes

    @classmethod
    def _maak_wekelijkse_backup(cls, nu: datetime) -> bool:
        """Maak wekelijkse backup als die nog niet bestaat voor deze week."""
        week = nu.isocalendar()[1]
        naam = f"{_WEKELIJKS_PREFIX}{nu.year}_W{week:02d}.dump"
        pad = BACKUP_DIR / naam
        if pad.exists():
            logger.debug("Wekelijkse backup bestaat al: %s", naam)
            return False
        succes = _pg_dump(pad)
        if succes:
            grootte = pad.stat().st_size / (1024 * 1024)
            logger.info("Wekelijkse backup aangemaakt: %s (%.1f MB)", naam, grootte)
            _opruimen(_WEKELIJKS_PREFIX, BEWAAR_WEKELIJKS)
        return succes

    @classmethod
    def _maak_maandelijkse_backup(cls, nu: datetime) -> bool:
        """Maak maandelijkse backup als die nog niet bestaat voor deze maand."""
        naam = f"{_MAANDELIJKS_PREFIX}{nu.strftime('%Y%m')}.dump"
        pad = BACKUP_DIR / naam
        if pad.exists():
            logger.debug("Maandelijkse backup bestaat al: %s", naam)
            return False
        succes = _pg_dump(pad)
        if succes:
            grootte = pad.stat().st_size / (1024 * 1024)
            logger.info("Maandelijkse backup aangemaakt: %s (%.1f MB)", naam, grootte)
            _opruimen(_MAANDELIJKS_PREFIX, BEWAAR_MAANDELIJKS)
        return succes

    # ── Handmatig (via GUI) ──────────────────────────────────────────── #

    @classmethod
    def maak_handmatige_backup(cls, label: str = "") -> Optional[Path]:
        """
        Maak een handmatige backup met optioneel label in de bestandsnaam.

        Args:
            label: Optioneel label (bijv. 'voor_import'). Ongeldige tekens worden verwijderd.

        Returns:
            Path naar het aangemaakte backup-bestand, of None bij fout.
        """
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if label:
            schoon = "".join(c for c in label if c.isalnum() or c in "_-")[:50]
            naam = f"{_HANDMATIG_PREFIX}{timestamp}_{schoon}.dump"
        else:
            naam = f"{_HANDMATIG_PREFIX}{timestamp}.dump"

        pad = BACKUP_DIR / naam
        succes = _pg_dump(pad)
        if succes:
            grootte = pad.stat().st_size / (1024 * 1024)
            logger.info("Handmatige backup aangemaakt: %s (%.1f MB)", naam, grootte)
            return pad
        if pad.exists():
            pad.unlink()  # Verwijder leeg/corrupt bestand
        return None

    @classmethod
    def maak_pre_restore_backup(cls) -> Optional[Path]:
        """
        Maak een pre-restore backup vóór een destructieve actie (restore of merge).

        Returns:
            Path naar het backup-bestand, of None bij fout.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        naam = f"{_PRE_RESTORE_PREFIX}{timestamp}.dump"
        pad = BACKUP_DIR / naam
        succes = _pg_dump(pad)
        if succes:
            logger.info("Pre-restore backup aangemaakt: %s", naam)
            # Pre-restore backups: bewaar laatste 7
            _opruimen(_PRE_RESTORE_PREFIX, 7)
            return pad
        if pad.exists():
            pad.unlink()
        return None

    # ── Restore ─────────────────────────────────────────────────────── #

    @classmethod
    def herstel_backup(cls, backup_pad: Path) -> tuple[bool, str]:
        """
        Herstel de database vanuit een backup-bestand.

        Maakt eerst automatisch een pre-restore backup.

        Args:
            backup_pad: Pad naar het backup-bestand (.dump).

        Returns:
            Tuple (succes: bool, bericht: str).
        """
        if not backup_pad.exists():
            return False, f"Backup-bestand niet gevonden: {backup_pad.name}"

        logger.info("Herstel gestart vanuit: %s", backup_pad.name)

        pre_backup = cls.maak_pre_restore_backup()
        if pre_backup is None:
            return False, "Kon geen pre-restore backup aanmaken. Herstel afgebroken."

        succes = _pg_restore(backup_pad)
        if succes:
            logger.info("Database hersteld vanuit: %s", backup_pad.name)
            return True, f"Database hersteld vanuit {backup_pad.name}. Pre-restore backup: {pre_backup.name}"
        return False, f"Herstel mislukt voor {backup_pad.name}. Pre-restore backup beschikbaar: {pre_backup.name}"

    # ── Overzicht ───────────────────────────────────────────────────── #

    @classmethod
    def lijst_backups(cls) -> list[dict]:
        """
        Geef een gesorteerde lijst van alle backup-bestanden (nieuwste eerst).

        Returns:
            Lijst van dicts met: naam, pad, type, grootte_mb, aangemaakt_op.
        """
        if not BACKUP_DIR.exists():
            return []

        resultaat = []
        for bestand in BACKUP_DIR.glob("*.dump"):
            naam = bestand.name
            stat = bestand.stat()
            backup_type = (
                "dagelijks"   if naam.startswith(_DAGELIJKS_PREFIX) else
                "wekelijks"   if naam.startswith(_WEKELIJKS_PREFIX) else
                "maandelijks" if naam.startswith(_MAANDELIJKS_PREFIX) else
                "pre_restore" if naam.startswith(_PRE_RESTORE_PREFIX) else
                "handmatig"
            )
            resultaat.append({
                "naam":         naam,
                "pad":          str(bestand),
                "type":         backup_type,
                "grootte_mb":   round(stat.st_size / (1024 * 1024), 2),
                "aangemaakt_op": datetime.fromtimestamp(stat.st_ctime),
            })

        return sorted(resultaat, key=lambda x: x["aangemaakt_op"], reverse=True)

    @classmethod
    def verwijder_backup(cls, bestandsnaam: str) -> tuple[bool, str]:
        """
        Verwijder een specifiek backup-bestand.

        Args:
            bestandsnaam: Alleen de bestandsnaam (geen pad), bijv. 'backup_dagelijks_20260322.dump'.

        Returns:
            Tuple (succes: bool, bericht: str).
        """
        # Beveilig tegen path traversal
        if "/" in bestandsnaam or "\\" in bestandsnaam or ".." in bestandsnaam:
            return False, "Ongeldig bestandsnaam."
        if not bestandsnaam.endswith(".dump"):
            return False, "Alleen .dump bestanden kunnen verwijderd worden."

        pad = BACKUP_DIR / bestandsnaam
        if not pad.exists():
            return False, f"Backup niet gevonden: {bestandsnaam}"

        try:
            pad.unlink()
            logger.info("Backup verwijderd: %s", bestandsnaam)
            return True, f"Backup {bestandsnaam} verwijderd."
        except Exception as fout:
            logger.error("Kon %s niet verwijderen: %s", bestandsnaam, fout)
            return False, f"Verwijderen mislukt: {fout}"

    @classmethod
    def statistieken(cls) -> dict:
        """
        Geef statistieken over de backups.

        Returns:
            Dict met aantallen en totale grootte per type.
        """
        stats: dict[str, dict] = {
            "dagelijks":   {"aantal": 0, "grootte_mb": 0.0},
            "wekelijks":   {"aantal": 0, "grootte_mb": 0.0},
            "maandelijks": {"aantal": 0, "grootte_mb": 0.0},
            "handmatig":   {"aantal": 0, "grootte_mb": 0.0},
            "pre_restore": {"aantal": 0, "grootte_mb": 0.0},
            "totaal_mb":   0.0,
        }
        for backup in cls.lijst_backups():
            t = backup["type"]
            if t in stats:
                stats[t]["aantal"] += 1
                stats[t]["grootte_mb"] += backup["grootte_mb"]
            stats["totaal_mb"] += backup["grootte_mb"]
        return stats
