"""
SqliteImportService — importeer een v0.7 SQLite database via de GUI.

Verwerkt een geüpload .db bestand en mergt de inhoud in de bestaande
PostgreSQL database.

De gebruiker kiest expliciet de doellocatie (code + naam). De bestandsnaam
dient enkel als UUID-namespace prefix. Zo kunnen meerdere .db bestanden
(database.PAT.db, database.TO.db) als teams onder één locatie worden
geïmporteerd.

Conflict-strategie: skip bestaande records op uuid of semantische sleutel.
"""

import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

import psycopg2

from services.backup_service import BackupService

logger = logging.getLogger(__name__)

_UUID_NS = uuid.UUID("12345678-1234-5678-1234-567812345678")

ROL_MAPPING: dict[str, str] = {
    "beheerder":   "beheerder",
    "planner":     "planner",
    "hr":          "hr",
    "teamlid":     "teamlid",
    "gebruiker":   "teamlid",
    "admin":       "super_beheerder",
}


# ─────────────────────────────────────────────────────── resultaat ── #

class SqliteImportResultaat:
    """Resultaat van een SQLite-import-operatie."""

    def __init__(self) -> None:
        self.locatie_code: str = ""
        self.nieuw: dict[str, int] = {}
        self.overgeslagen: dict[str, int] = {}
        self.fouten: list[str] = []
        self.pre_backup: Optional[str] = None

    def totaal_nieuw(self) -> int:
        return sum(self.nieuw.values())

    def totaal_overgeslagen(self) -> int:
        return sum(self.overgeslagen.values())


class SqliteVoorvertoning:
    """Samenvatting van wat een SQLite-import zou importeren."""

    def __init__(self) -> None:
        self.bestandsnaam: str = ""
        self.bron_code: str = ""       # afgeleid uit bestandsnaam (PAT, TO, ...)
        self.doellocatie_code: str = ""
        self.doellocatie_naam: str = ""
        self.tabellen: dict[str, dict[str, int]] = {}

    def totaal_nieuw(self) -> int:
        return sum(info["nieuw"] for info in self.tabellen.values())


# ─────────────────────────────────────────────────────── helpers ──── #

def _pg_verbinding() -> psycopg2.extensions.connection:
    """Maak verbinding met PostgreSQL via DATABASE_URL."""
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(url)


def _lees_sqlite(pad: Path) -> sqlite3.Connection:
    """Open een SQLite database met Row factory."""
    db = sqlite3.connect(str(pad))
    db.row_factory = sqlite3.Row
    return db


def _locatie_code_uit_bestandsnaam(pad: Path) -> str:
    """
    Leid locatiecode af uit bestandsnaam.
    'database.PAT.db' → 'PAT', 'database.TO.db' → 'TO', 'mijn_db.db' → 'MIJN_DB'.
    """
    naam = pad.stem
    delen = naam.split(".")
    if len(delen) >= 2:
        return delen[-1].upper()
    return naam.upper()[:20]


def _tabel_bestaat(db: sqlite3.Connection, tabel: str) -> bool:
    """Controleer of een tabel bestaat in SQLite."""
    rij = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabel,)
    ).fetchone()
    return rij is not None


def _kolommen_van(db: sqlite3.Connection, tabel: str) -> set[str]:
    """Geef kolomnamen van een SQLite-tabel als set."""
    try:
        rijen = db.execute(f"PRAGMA table_info({tabel})").fetchall()
        return {r["name"] for r in rijen}
    except Exception:
        return set()


def _genereer_uuid(sleutel: str) -> str:
    """Deterministisch uuid5 op basis van sleutel."""
    return str(uuid.uuid5(_UUID_NS, sleutel))


def _verwerk_wachtwoord(hash_waarde) -> str:
    """Bcrypt hash kan bytes of string zijn in SQLite."""
    if isinstance(hash_waarde, bytes):
        return hash_waarde.decode("utf-8")
    return str(hash_waarde) if hash_waarde else ""


def _haal_of_maak_locatie(cur, code: str, naam: str) -> int:
    """Geef het PostgreSQL-ID van een Locatie op code, of maak er een aan."""
    cur.execute("SELECT id FROM locaties WHERE code = %s", (code,))
    rij = cur.fetchone()
    if rij:
        logger.info("  Locatie gevonden: '%s' (id=%s)", code, rij[0])
        return rij[0]
    locatie_uuid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO locaties (uuid, naam, code, is_actief) VALUES (%s, %s, %s, TRUE) RETURNING id",
        (locatie_uuid, naam, code),
    )
    locatie_id = cur.fetchone()[0]
    logger.info("  Locatie aangemaakt: '%s' (id=%s)", naam, locatie_id)
    return locatie_id


def _haal_of_maak_team(cur, naam: str, code: str, locatie_id: int) -> int:
    """Geef het PostgreSQL-ID van een Team op naam+locatie, of maak er een aan."""
    cur.execute(
        "SELECT id FROM teams WHERE naam = %s AND locatie_id = %s",
        (naam, locatie_id),
    )
    rij = cur.fetchone()
    if rij:
        return rij[0]
    team_uuid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO teams (uuid, naam, code, locatie_id, is_actief) VALUES (%s, %s, %s, %s, TRUE) RETURNING id",
        (team_uuid, naam, code, locatie_id),
    )
    team_id = cur.fetchone()[0]
    cur.execute("INSERT INTO team_configs (team_id, standaard_taal) VALUES (%s, 'nl')", (team_id,))
    logger.info("    Team aangemaakt: '%s' (id=%s)", naam, team_id)
    return team_id


# ────────────────────────────────────────────────── import-functies ── #

def _importeer_teams(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    locatie_code: str,
) -> dict[int, int]:
    """
    Importeer teams/groepen uit SQLite naar PostgreSQL.

    Returns:
        Mapping {sqlite_id: pg_id}.
    """
    tabel = (
        "teams" if _tabel_bestaat(sqlite_db, "teams")
        else "groepen" if _tabel_bestaat(sqlite_db, "groepen")
        else None
    )
    mapping: dict[int, int] = {}
    if tabel:
        kolommen = _kolommen_van(sqlite_db, tabel)
        rijen = sqlite_db.execute(f"SELECT * FROM {tabel}").fetchall()
        for t in rijen:
            naam = t["naam"] if "naam" in kolommen else f"Team {t['id']}"
            code = (
                t["code"] if "code" in kolommen
                else naam[:20].upper().replace(" ", "_")
            )
            pg_team_id = _haal_of_maak_team(cur, naam, code, locatie_id)
            mapping[t["id"]] = pg_team_id
        logger.info("  %s teams verwerkt", len(rijen))
    else:
        pg_team_id = _haal_of_maak_team(cur, locatie_code, locatie_code, locatie_id)
        mapping[1] = pg_team_id
        logger.info("  Geen teams-tabel — standaard team aangemaakt")
    return mapping


def _importeer_werkposten(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    locatie_code: str,
) -> dict[int, int]:
    """
    Importeer werkposten met deduplicatie op naam (case-insensitive).

    Returns:
        Mapping {sqlite_id: pg_id}.
    """
    if not _tabel_bestaat(sqlite_db, "werkposten"):
        return {}
    kolommen = _kolommen_van(sqlite_db, "werkposten")
    rijen = sqlite_db.execute("SELECT * FROM werkposten").fetchall()
    mapping: dict[int, int] = {}
    nieuw = 0
    for rij in rijen:
        naam = rij["naam"] if "naam" in kolommen else f"Werkpost {rij['id']}"
        cur.execute(
            "SELECT id FROM werkposten WHERE LOWER(naam) = %s AND locatie_id = %s",
            (naam.strip().lower(), locatie_id),
        )
        bestaande = cur.fetchone()
        if bestaande:
            mapping[rij["id"]] = bestaande[0]
            continue
        wp_uuid = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO werkposten
               (uuid, locatie_id, naam, beschrijving,
                telt_als_werkdag, reset_12u_rust, breekt_werk_reeks, is_actief)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                wp_uuid, locatie_id, naam,
                rij["beschrijving"] if "beschrijving" in kolommen else None,
                bool(rij["telt_als_werkdag"]) if "telt_als_werkdag" in kolommen else True,
                bool(rij["reset_12u_rust"]) if "reset_12u_rust" in kolommen else False,
                bool(rij["breekt_werk_reeks"]) if "breekt_werk_reeks" in kolommen else False,
                bool(rij["is_actief"]) if "is_actief" in kolommen else True,
            ),
        )
        pg_id = cur.fetchone()[0]
        mapping[rij["id"]] = pg_id
        nieuw += 1
    logger.info("  %s werkposten verwerkt (%s nieuw)", len(rijen), nieuw)
    return mapping


def _importeer_shiftcodes(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    locatie_code: str,
    werkpost_mapping: dict[int, int],
) -> dict[int, int]:
    """
    Importeer shiftcodes met deduplicatie op (locatie_id, code).

    Returns:
        Mapping {sqlite_id: pg_id}.
    """
    tabel = "shift_codes" if _tabel_bestaat(sqlite_db, "shift_codes") else "shiftcodes"
    if not _tabel_bestaat(sqlite_db, tabel):
        return {}
    kolommen = _kolommen_van(sqlite_db, tabel)
    rijen = sqlite_db.execute(f"SELECT * FROM {tabel}").fetchall()
    mapping: dict[int, int] = {}
    nieuw = 0
    for rij in rijen:
        code = rij["code"]
        cur.execute(
            "SELECT id FROM shiftcodes WHERE code = %s AND locatie_id = %s",
            (code, locatie_id),
        )
        bestaande = cur.fetchone()
        if bestaande:
            mapping[rij["id"]] = bestaande[0]
            continue
        sc_uuid = str(uuid.uuid4())
        sqlite_wp_id = rij["werkpost_id"] if "werkpost_id" in kolommen else None
        pg_wp_id = werkpost_mapping.get(sqlite_wp_id) if sqlite_wp_id else None
        cur.execute(
            """INSERT INTO shiftcodes
               (uuid, werkpost_id, locatie_id, dag_type, shift_type, code,
                start_uur, eind_uur, is_kritisch, telt_als_werkdag)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                sc_uuid, pg_wp_id, locatie_id,
                rij["dag_type"] if "dag_type" in kolommen else None,
                rij["shift_type"] if "shift_type" in kolommen else None,
                code,
                rij["start_uur"] if "start_uur" in kolommen else None,
                rij["eind_uur"] if "eind_uur" in kolommen else None,
                bool(rij["is_kritisch"]) if "is_kritisch" in kolommen else False,
                bool(rij["telt_als_werkdag"]) if "telt_als_werkdag" in kolommen else True,
            ),
        )
        pg_id = cur.fetchone()[0]
        mapping[rij["id"]] = pg_id
        nieuw += 1
    logger.info("  %s shiftcodes verwerkt (%s nieuw)", len(rijen), nieuw)
    return mapping


def _importeer_gebruikers(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    locatie_code: str,
) -> dict[int, int]:
    """
    Importeer gebruikers met deduplicatie op gebruikersnaam.

    Returns:
        Mapping {sqlite_id: pg_id}.
    """
    kolommen = _kolommen_van(sqlite_db, "gebruikers")
    rijen = sqlite_db.execute("SELECT * FROM gebruikers").fetchall()
    mapping: dict[int, int] = {}
    nieuw = 0
    for rij in rijen:
        gebruikersnaam = rij["gebruikersnaam"]
        cur.execute("SELECT id FROM gebruikers WHERE gebruikersnaam = %s", (gebruikersnaam,))
        bestaande = cur.fetchone()
        if bestaande:
            mapping[rij["id"]] = bestaande[0]
            continue
        g_uuid = str(uuid.uuid4())
        rol_v7 = rij["rol"] if "rol" in kolommen else "teamlid"
        cur.execute(
            """INSERT INTO gebruikers
               (uuid, gebruikersnaam, gehashed_wachtwoord,
                volledige_naam, voornaam, achternaam,
                rol, locatie_id, startweek_typedienst, shift_voorkeuren,
                thema, taal, totp_actief, totp_geheim,
                is_actief, aangemaakt_op, gedeactiveerd_op, laatste_login)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       'systeem', 'nl', FALSE, NULL,
                       %s, %s, %s, %s)
               RETURNING id""",
            (
                g_uuid, gebruikersnaam,
                _verwerk_wachtwoord(rij["wachtwoord_hash"]),
                rij["volledige_naam"] if "volledige_naam" in kolommen else gebruikersnaam,
                rij["voornaam"] if "voornaam" in kolommen else None,
                rij["achternaam"] if "achternaam" in kolommen else None,
                ROL_MAPPING.get(rol_v7, "teamlid"),
                locatie_id,
                rij["startweek_typedienst"] if "startweek_typedienst" in kolommen else None,
                rij["shift_voorkeuren"] if "shift_voorkeuren" in kolommen else None,
                bool(rij["is_actief"]) if "is_actief" in kolommen else True,
                rij["aangemaakt_op"] if "aangemaakt_op" in kolommen else None,
                rij["gedeactiveerd_op"] if "gedeactiveerd_op" in kolommen else None,
                rij["laatste_login"] if "laatste_login" in kolommen else None,
            ),
        )
        pg_id = cur.fetchone()[0]
        mapping[rij["id"]] = pg_id
        nieuw += 1
    logger.info("  %s gebruikers verwerkt (%s nieuw)", len(rijen), nieuw)
    return mapping


def _importeer_gebruiker_rollen(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    gebruiker_mapping: dict[int, int],
    team_mapping: dict[int, int],
) -> int:
    """
    Maak GebruikerRol records aan op basis van de rol-kolom in de gebruikerstabel.

    Returns:
        Aantal nieuw aangemaakte rollen.
    """
    kolommen = _kolommen_van(sqlite_db, "gebruikers")
    rijen = sqlite_db.execute("SELECT * FROM gebruikers").fetchall()
    eerste_team_id: Optional[int] = next(iter(team_mapping.values())) if team_mapping else None
    aangemaakt = 0
    for rij in rijen:
        pg_gebruiker_id = gebruiker_mapping.get(rij["id"])
        if pg_gebruiker_id is None:
            continue
        rol_v7 = rij["rol"] if "rol" in kolommen else "teamlid"
        rol_v9 = ROL_MAPPING.get(rol_v7, "teamlid")
        scope_id = (
            locatie_id if rol_v9 in ("beheerder", "hr", "super_beheerder")
            else eerste_team_id or locatie_id
        )
        cur.execute(
            """INSERT INTO gebruiker_rollen (gebruiker_id, rol, scope_id, is_reserve, is_actief)
               VALUES (%s, %s, %s, %s, TRUE)
               ON CONFLICT (gebruiker_id, rol, scope_id) DO NOTHING""",
            (pg_gebruiker_id, rol_v9, scope_id,
             bool(rij["is_reserve"]) if "is_reserve" in kolommen else False),
        )
        if cur.rowcount:
            aangemaakt += 1
    logger.info("  %s gebruiker_rollen aangemaakt", aangemaakt)
    return aangemaakt


def _importeer_planning(
    sqlite_db: sqlite3.Connection,
    cur,
    gebruiker_mapping: dict[int, int],
    team_id: int,
) -> int:
    """
    Importeer planningshifts met deduplicatie op (gebruiker_id, datum).

    Returns:
        Aantal geïmporteerde shifts.
    """
    if not _tabel_bestaat(sqlite_db, "planning"):
        return 0
    kolommen = _kolommen_van(sqlite_db, "planning")
    rijen = sqlite_db.execute("SELECT * FROM planning").fetchall()
    aangemaakt = 0
    for rij in rijen:
        pg_gebruiker_id = gebruiker_mapping.get(rij["gebruiker_id"])
        if pg_gebruiker_id is None:
            continue
        plan_uuid = (
            rij["uuid"] if "uuid" in kolommen and rij["uuid"]
            else str(uuid.uuid4())
        )
        cur.execute(
            """INSERT INTO planning
               (uuid, gebruiker_id, team_id, datum, shift_code,
                notitie, notitie_gelezen, status, aangemaakt_op)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (gebruiker_id, datum) DO NOTHING""",
            (
                plan_uuid, pg_gebruiker_id, team_id,
                rij["datum"],
                rij["shift_code"] if "shift_code" in kolommen else None,
                rij["notitie"] if "notitie" in kolommen else None,
                bool(rij["notitie_gelezen"]) if "notitie_gelezen" in kolommen else False,
                (rij["status"] or "concept") if "status" in kolommen else "concept",
                rij["aangemaakt_op"] if "aangemaakt_op" in kolommen else None,
            ),
        )
        aangemaakt += cur.rowcount
    logger.info("  %s planning shifts geïmporteerd (van %s)", aangemaakt, len(rijen))
    return aangemaakt


def _importeer_verlof(
    sqlite_db: sqlite3.Connection,
    cur,
    gebruiker_mapping: dict[int, int],
) -> int:
    """
    Importeer verlofaanvragen met deduplicatie op uuid.

    Returns:
        Aantal geïmporteerde verlofaanvragen.
    """
    tabel = "verlof_aanvragen"
    if not _tabel_bestaat(sqlite_db, tabel):
        return 0
    kolommen = _kolommen_van(sqlite_db, tabel)
    rijen = sqlite_db.execute(f"SELECT * FROM {tabel}").fetchall()
    aangemaakt = 0
    for rij in rijen:
        pg_gebruiker_id = gebruiker_mapping.get(rij["gebruiker_id"])
        if pg_gebruiker_id is None:
            continue
        verlof_uuid = (
            rij["uuid"] if "uuid" in kolommen and rij["uuid"]
            else str(uuid.uuid4())
        )
        cur.execute(
            """INSERT INTO verlof_aanvragen
               (uuid, gebruiker_id, start_datum, eind_datum, aantal_dagen,
                status, toegekende_code_term, opmerking, aangevraagd_op,
                behandeld_op, reden_weigering)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (uuid) DO NOTHING""",
            (
                verlof_uuid, pg_gebruiker_id,
                rij["start_datum"], rij["eind_datum"],
                rij["aantal_dagen"] if "aantal_dagen" in kolommen else 1,
                (rij["status"] or "pending") if "status" in kolommen else "pending",
                rij["toegekende_code_term"] if "toegekende_code_term" in kolommen else None,
                rij["opmerking"] if "opmerking" in kolommen else None,
                rij["aangevraagd_op"] if "aangevraagd_op" in kolommen else None,
                rij["behandeld_op"] if "behandeld_op" in kolommen else None,
                rij["reden_weigering"] if "reden_weigering" in kolommen else None,
            ),
        )
        aangemaakt += cur.rowcount
    logger.info("  %s verlofaanvragen geïmporteerd", aangemaakt)
    return aangemaakt


# ─────────────────────────────────────────────── hoofd service-klasse ─ #

class SqliteImportService:
    """Service voor het importeren van een v0.7 SQLite database via de GUI."""

    @classmethod
    def voorvertoning(
        cls,
        pad: Path,
        bestandsnaam: str,
        doellocatie_code: str,
        doellocatie_naam: str,
    ) -> SqliteVoorvertoning:
        """
        Analyseer een SQLite .db bestand en toon wat geïmporteerd zou worden.

        Args:
            pad:               Tijdelijk pad van het geüploade bestand.
            bestandsnaam:      Originele bestandsnaam (voor UUID-namespace).
            doellocatie_code:  Code van de doellocatie in PostgreSQL.
            doellocatie_naam:  Naam van de doellocatie (enkel gebruikt bij aanmaken).

        Returns:
            SqliteVoorvertoning met aantallen per entiteitstype.
        """
        bron_code = _locatie_code_uit_bestandsnaam(Path(bestandsnaam))
        sqlite_db = _lees_sqlite(pad)
        pg = _pg_verbinding()
        cur = pg.cursor()
        overzicht = SqliteVoorvertoning()
        overzicht.bestandsnaam = bestandsnaam
        overzicht.bron_code = bron_code
        overzicht.doellocatie_code = doellocatie_code
        overzicht.doellocatie_naam = doellocatie_naam

        try:
            # Teams
            tabel_teams = (
                "teams" if _tabel_bestaat(sqlite_db, "teams")
                else "groepen" if _tabel_bestaat(sqlite_db, "groepen")
                else None
            )
            if tabel_teams:
                rijen_teams = sqlite_db.execute(f"SELECT naam FROM {tabel_teams}").fetchall()
                kolommen_t = _kolommen_van(sqlite_db, tabel_teams)
                nieuw_teams = 0
                for t in rijen_teams:
                    naam = t["naam"] if "naam" in kolommen_t else ""
                    cur.execute(
                        "SELECT 1 FROM teams WHERE naam = %s AND locatie_id IN "
                        "(SELECT id FROM locaties WHERE code = %s)",
                        (naam, doellocatie_code),
                    )
                    if not cur.fetchone():
                        nieuw_teams += 1
                overzicht.tabellen["teams"] = {"totaal": len(rijen_teams), "nieuw": nieuw_teams}
            else:
                overzicht.tabellen["teams"] = {"totaal": 0, "nieuw": 0}

            # Werkposten
            if _tabel_bestaat(sqlite_db, "werkposten"):
                rijen_wp = sqlite_db.execute("SELECT naam FROM werkposten").fetchall()
                kolommen_wp = _kolommen_van(sqlite_db, "werkposten")
                nieuw_wp = 0
                for w in rijen_wp:
                    naam = w["naam"] if "naam" in kolommen_wp else ""
                    cur.execute(
                        "SELECT 1 FROM werkposten WHERE LOWER(naam) = %s AND locatie_id IN "
                        "(SELECT id FROM locaties WHERE code = %s)",
                        (naam.strip().lower(), doellocatie_code),
                    )
                    if not cur.fetchone():
                        nieuw_wp += 1
                overzicht.tabellen["werkposten"] = {"totaal": len(rijen_wp), "nieuw": nieuw_wp}
            else:
                overzicht.tabellen["werkposten"] = {"totaal": 0, "nieuw": 0}

            # Shiftcodes
            tabel_sc = "shift_codes" if _tabel_bestaat(sqlite_db, "shift_codes") else "shiftcodes"
            if _tabel_bestaat(sqlite_db, tabel_sc):
                rijen_sc = sqlite_db.execute(f"SELECT code FROM {tabel_sc}").fetchall()
                nieuw_sc = 0
                for s in rijen_sc:
                    cur.execute(
                        "SELECT 1 FROM shiftcodes WHERE code = %s AND locatie_id IN "
                        "(SELECT id FROM locaties WHERE code = %s)",
                        (s["code"], doellocatie_code),
                    )
                    if not cur.fetchone():
                        nieuw_sc += 1
                overzicht.tabellen["shiftcodes"] = {"totaal": len(rijen_sc), "nieuw": nieuw_sc}
            else:
                overzicht.tabellen["shiftcodes"] = {"totaal": 0, "nieuw": 0}

            # Gebruikers
            rijen_g = sqlite_db.execute("SELECT gebruikersnaam FROM gebruikers").fetchall()
            nieuw_g = 0
            for g in rijen_g:
                cur.execute(
                    "SELECT 1 FROM gebruikers WHERE gebruikersnaam = %s",
                    (g["gebruikersnaam"],),
                )
                if not cur.fetchone():
                    nieuw_g += 1
            overzicht.tabellen["gebruikers"] = {"totaal": len(rijen_g), "nieuw": nieuw_g}

            # Planning
            if _tabel_bestaat(sqlite_db, "planning"):
                rijen_p = sqlite_db.execute("SELECT COUNT(*) as n FROM planning").fetchone()
                overzicht.tabellen["planning"] = {
                    "totaal": rijen_p["n"] if rijen_p else 0,
                    "nieuw": rijen_p["n"] if rijen_p else 0,  # exacte telling te duur voor preview
                }
            else:
                overzicht.tabellen["planning"] = {"totaal": 0, "nieuw": 0}

            # Verlof
            tabel_v = "verlof_aanvragen"
            if _tabel_bestaat(sqlite_db, tabel_v):
                rijen_v = sqlite_db.execute(f"SELECT COUNT(*) as n FROM {tabel_v}").fetchone()
                overzicht.tabellen["verlof"] = {
                    "totaal": rijen_v["n"] if rijen_v else 0,
                    "nieuw": rijen_v["n"] if rijen_v else 0,
                }
            else:
                overzicht.tabellen["verlof"] = {"totaal": 0, "nieuw": 0}

        finally:
            cur.close()
            pg.close()
            sqlite_db.close()

        return overzicht

    @classmethod
    def importeer(
        cls,
        pad: Path,
        bestandsnaam: str,
        doellocatie_code: str,
        doellocatie_naam: str,
    ) -> SqliteImportResultaat:
        """
        Importeer een SQLite .db bestand in de PostgreSQL database.

        Maakt eerst een pre-import backup. Records worden nooit overschreven.

        Args:
            pad:               Tijdelijk pad van het geüploade bestand.
            bestandsnaam:      Originele bestandsnaam (voor UUID-namespace).
            doellocatie_code:  Code van de doellocatie (bestaand of nieuw).
            doellocatie_naam:  Naam van de doellocatie (enkel gebruikt bij aanmaken).

        Returns:
            SqliteImportResultaat met aantallen en eventuele fouten.

        Raises:
            ValueError: Als de pre-import backup mislukt.
        """
        bron_code = _locatie_code_uit_bestandsnaam(Path(bestandsnaam))
        resultaat = SqliteImportResultaat()
        resultaat.locatie_code = doellocatie_code

        # Pre-import backup
        pre_backup = BackupService.maak_pre_restore_backup()
        if pre_backup is None:
            raise ValueError("Kon geen pre-import backup aanmaken. Import afgebroken.")
        resultaat.pre_backup = pre_backup.name
        logger.info("Pre-import backup aangemaakt: %s", pre_backup.name)

        sqlite_db = _lees_sqlite(pad)
        pg = _pg_verbinding()
        cur = pg.cursor()

        try:
            logger.info(
                "SQLite import gestart: %s → locatie '%s'",
                bestandsnaam, doellocatie_code,
            )

            # 1. Locatie (aanmaken indien nieuw, anders hergebruiken)
            locatie_id = _haal_of_maak_locatie(cur, doellocatie_code, doellocatie_naam)

            # 2. Teams
            team_mapping = _importeer_teams(sqlite_db, cur, locatie_id, bron_code)
            eerste_team_id = next(iter(team_mapping.values())) if team_mapping else locatie_id
            resultaat.nieuw["teams"] = sum(1 for _ in team_mapping)

            # 3. Werkposten
            werkpost_mapping = _importeer_werkposten(sqlite_db, cur, locatie_id, bron_code)
            resultaat.nieuw["werkposten"] = len(werkpost_mapping)

            # 4. Shiftcodes
            sc_mapping = _importeer_shiftcodes(sqlite_db, cur, locatie_id, bron_code, werkpost_mapping)
            resultaat.nieuw["shiftcodes"] = len(sc_mapping)

            # 5. Gebruikers
            gebruiker_mapping = _importeer_gebruikers(sqlite_db, cur, locatie_id, bron_code)
            resultaat.nieuw["gebruikers"] = len([v for v in gebruiker_mapping.values() if v])

            # 6. Gebruiker-rollen
            rollen_nieuw = _importeer_gebruiker_rollen(
                sqlite_db, cur, locatie_id, gebruiker_mapping, team_mapping
            )
            resultaat.nieuw["gebruiker_rollen"] = rollen_nieuw

            # 7. Planning
            planning_nieuw = _importeer_planning(sqlite_db, cur, gebruiker_mapping, eerste_team_id)
            resultaat.nieuw["planning"] = planning_nieuw

            # 8. Verlof
            verlof_nieuw = _importeer_verlof(sqlite_db, cur, gebruiker_mapping)
            resultaat.nieuw["verlof"] = verlof_nieuw

            pg.commit()
            logger.info(
                "SQLite import succesvol: locatie=%s (bron=%s), %s nieuwe records totaal",
                doellocatie_code, bron_code, resultaat.totaal_nieuw(),
            )

        except Exception as fout:
            pg.rollback()
            logger.error("SQLite import mislukt voor %s: %s", bestandsnaam, fout, exc_info=True)
            raise

        finally:
            sqlite_db.close()
            cur.close()
            pg.close()

        return resultaat
