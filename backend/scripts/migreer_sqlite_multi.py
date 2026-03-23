"""
Migratiescript: meerdere v0.7 SQLite databases → v0.9 PostgreSQL

Gebruik (vanuit projectroot):
    docker compose run --rm \\
        -v "C:/pad/naar/database.PAT.db:/data/database.PAT.db" \\
        -v "C:/pad/naar/database.TO.db:/data/database.TO.db" \\
        app python /app/scripts/migreer_sqlite_multi.py

Of met expliciet pad-argument:
    python scripts/migreer_sqlite_multi.py /data/database.PAT.db /data/database.TO.db

Werkwijze:
- Elke SQLite-bestand vertegenwoordigt één locatie (afgeleid van bestandsnaam: database.PAT.db → 'PAT').
- Per locatie worden teams, gebruikers, werkposten, shiftcodes, planning en verlof geïmporteerd.
- Werkposten worden gededupliceerd op naam (case-insensitive) over alle locaties heen.
- Shiftcodes zonder uuid krijgen een deterministisch uuid5.
- ID's worden NIET hergebruikt — PostgreSQL genereert nieuwe IDs, met mapping-dicts.
- Conflict-strategie: bestaande records (op uuid of semantische sleutel) worden overgeslagen.
"""

import logging
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path("/data")
DATABASE_URL = os.environ["DATABASE_URL"]

# UUID namespace voor deterministisch genereren van ontbrekende UUIDs
_UUID_NS = uuid.UUID("12345678-1234-5678-1234-567812345678")

ROL_MAPPING = {
    "beheerder": "beheerder",
    "planner":   "planner",
    "hr":        "hr",
    "teamlid":   "teamlid",
    "gebruiker": "teamlid",
    "admin":     "super_beheerder",
}


# ─────────────────────────────────────────────────────────── helpers ── #

def pg_verbinding():
    """Verbinding maken met PostgreSQL via DATABASE_URL."""
    dsn = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(dsn)


def lees_sqlite(pad: Path) -> sqlite3.Connection:
    """SQLite database openen met Row factory."""
    if not pad.exists():
        log.error("SQLite database niet gevonden: %s", pad)
        sys.exit(1)
    db = sqlite3.connect(str(pad))
    db.row_factory = sqlite3.Row
    return db


def locatie_code_uit_bestandsnaam(pad: Path) -> str:
    """
    Leid locatie_code af uit bestandsnaam.
    'database.PAT.db' → 'PAT', 'database.TO.db' → 'TO'.
    """
    naam = pad.stem  # 'database.PAT'
    delen = naam.split(".")
    if len(delen) >= 2:
        return delen[-1].upper()
    return naam.upper()


def kolommen_van_tabel(db: sqlite3.Connection, tabel: str) -> set[str]:
    """Geef de kolomnamen van een SQLite-tabel als set."""
    try:
        rijen = db.execute(f"PRAGMA table_info({tabel})").fetchall()
        return {r["name"] for r in rijen}
    except Exception:
        return set()


def tabel_bestaat(db: sqlite3.Connection, tabel: str) -> bool:
    """Controleer of een tabel bestaat in de SQLite database."""
    rij = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabel,)
    ).fetchone()
    return rij is not None


def genereer_uuid(namespace_sleutel: str) -> str:
    """Genereer een deterministisch uuid5 op basis van een sleutel."""
    return str(uuid.uuid5(_UUID_NS, namespace_sleutel))


def verwerk_wachtwoord(hash_waarde) -> str:
    """Bcrypt hash kan bytes of string zijn in SQLite."""
    if isinstance(hash_waarde, bytes):
        return hash_waarde.decode("utf-8")
    return str(hash_waarde)


def haal_of_maak_locatie(cur, code: str, naam: str) -> int:
    """
    Geef het ID van een bestaande Locatie op code, of maak er een aan.

    Returns:
        PostgreSQL ID van de Locatie.
    """
    cur.execute("SELECT id FROM locaties WHERE code = %s", (code,))
    rij = cur.fetchone()
    if rij:
        log.info("  Locatie gevonden: '%s' (id=%s)", code, rij[0])
        return rij[0]

    locatie_uuid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO locaties (uuid, naam, code, is_actief) VALUES (%s, %s, %s, TRUE) RETURNING id",
        (locatie_uuid, naam, code),
    )
    locatie_id = cur.fetchone()[0]
    log.info("  Locatie aangemaakt: '%s' (id=%s)", naam, locatie_id)
    return locatie_id


def haal_of_maak_team(cur, naam: str, code: str, locatie_id: int) -> int:
    """
    Geef het ID van een bestaand Team op naam + locatie, of maak er een aan.

    Returns:
        PostgreSQL ID van het Team.
    """
    cur.execute(
        "SELECT id FROM teams WHERE naam = %s AND locatie_id = %s",
        (naam, locatie_id),
    )
    rij = cur.fetchone()
    if rij:
        return rij[0]

    team_uuid = str(uuid.uuid4())
    cur.execute(
        """INSERT INTO teams (uuid, naam, code, locatie_id, is_actief)
           VALUES (%s, %s, %s, %s, TRUE) RETURNING id""",
        (team_uuid, naam, code, locatie_id),
    )
    team_id = cur.fetchone()[0]
    # TeamConfig aanmaken
    cur.execute(
        "INSERT INTO team_configs (team_id, standaard_taal) VALUES (%s, 'nl')",
        (team_id,),
    )
    log.info("    Team aangemaakt: '%s' (id=%s)", naam, team_id)
    return team_id


def importeer_werkposten(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    locatie_code: str,
) -> dict[int, int]:
    """
    Importeer werkposten uit SQLite naar PostgreSQL.

    Werkposten worden gededupliceerd op naam (case-insensitive).
    Geeft een mapping {sqlite_id: pg_id} terug.
    """
    if not tabel_bestaat(sqlite_db, "werkposten"):
        log.info("  Geen werkposten-tabel gevonden, overgeslagen.")
        return {}

    kolommen = kolommen_van_tabel(sqlite_db, "werkposten")
    rijen = sqlite_db.execute("SELECT * FROM werkposten").fetchall()

    mapping: dict[int, int] = {}
    for rij in rijen:
        naam = rij["naam"] if "naam" in kolommen else f"Werkpost {rij['id']}"
        naam_genormaliseerd = naam.strip().lower()

        # Zoek bestaande werkpost op naam (case-insensitive) in dezelfde locatie
        cur.execute(
            "SELECT id FROM werkposten WHERE LOWER(naam) = %s AND locatie_id = %s",
            (naam_genormaliseerd, locatie_id),
        )
        bestaande = cur.fetchone()
        if bestaande:
            mapping[rij["id"]] = bestaande[0]
            log.debug("    Werkpost '%s' bestaat al (id=%s)", naam, bestaande[0])
            continue

        wp_uuid = (
            rij["uuid"] if "uuid" in kolommen and rij["uuid"]
            else genereer_uuid(f"{locatie_code}/werkpost/{naam}")
        )
        beschrijving = rij["beschrijving"] if "beschrijving" in kolommen else None
        telt_werkdag = bool(rij["telt_als_werkdag"]) if "telt_als_werkdag" in kolommen else True
        reset_rust = bool(rij["reset_12u_rust"]) if "reset_12u_rust" in kolommen else False
        breekt = bool(rij["breekt_werk_reeks"]) if "breekt_werk_reeks" in kolommen else False
        is_actief = bool(rij["is_actief"]) if "is_actief" in kolommen else True

        cur.execute(
            """INSERT INTO werkposten
               (uuid, locatie_id, naam, beschrijving,
                telt_als_werkdag, reset_12u_rust, breekt_werk_reeks, is_actief)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (wp_uuid, locatie_id, naam, beschrijving,
             telt_werkdag, reset_rust, breekt, is_actief),
        )
        pg_id = cur.fetchone()[0]
        mapping[rij["id"]] = pg_id
        log.debug("    Werkpost '%s' aangemaakt (id=%s)", naam, pg_id)

    log.info("  %s werkposten verwerkt (%s nieuw)", len(rijen), sum(
        1 for sqlite_id, pg_id in mapping.items()
        if pg_id not in [
            v for k, v in mapping.items() if k != sqlite_id
        ]
    ))
    return mapping


def importeer_shiftcodes(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    locatie_code: str,
    werkpost_mapping: dict[int, int],
) -> dict[int, int]:
    """
    Importeer shiftcodes uit SQLite naar PostgreSQL.

    Codes zonder uuid krijgen een deterministisch uuid5.
    Deduplicatie op (locatie_id, code).
    Geeft een mapping {sqlite_id: pg_id} terug.
    """
    tabel = "shift_codes" if tabel_bestaat(sqlite_db, "shift_codes") else "shiftcodes"
    if not tabel_bestaat(sqlite_db, tabel):
        log.info("  Geen shiftcodes-tabel gevonden, overgeslagen.")
        return {}

    kolommen = kolommen_van_tabel(sqlite_db, tabel)
    rijen = sqlite_db.execute(f"SELECT * FROM {tabel}").fetchall()

    mapping: dict[int, int] = {}
    for rij in rijen:
        code = rij["code"]

        # Zoek bestaande shiftcode op (locatie_id, code)
        cur.execute(
            "SELECT id FROM shiftcodes WHERE code = %s AND locatie_id = %s",
            (code, locatie_id),
        )
        bestaande = cur.fetchone()
        if bestaande:
            mapping[rij["id"]] = bestaande[0]
            continue

        sc_uuid = (
            rij["uuid"] if "uuid" in kolommen and rij["uuid"]
            else genereer_uuid(f"{locatie_code}/shiftcode/{code}")
        )

        sqlite_wp_id = rij["werkpost_id"] if "werkpost_id" in kolommen else None
        pg_wp_id = werkpost_mapping.get(sqlite_wp_id) if sqlite_wp_id else None

        dag_type = rij["dag_type"] if "dag_type" in kolommen else None
        shift_type = rij["shift_type"] if "shift_type" in kolommen else None
        start_uur = rij["start_uur"] if "start_uur" in kolommen else None
        eind_uur = rij["eind_uur"] if "eind_uur" in kolommen else None
        is_kritisch = bool(rij["is_kritisch"]) if "is_kritisch" in kolommen else False
        telt = bool(rij["telt_als_werkdag"]) if "telt_als_werkdag" in kolommen else True

        cur.execute(
            """INSERT INTO shiftcodes
               (uuid, werkpost_id, locatie_id, dag_type, shift_type, code,
                start_uur, eind_uur, is_kritisch, telt_als_werkdag)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (sc_uuid, pg_wp_id, locatie_id, dag_type, shift_type, code,
             start_uur, eind_uur, is_kritisch, telt),
        )
        pg_id = cur.fetchone()[0]
        mapping[rij["id"]] = pg_id

    log.info("  %s shiftcodes verwerkt", len(rijen))
    return mapping


def importeer_gebruikers(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    locatie_code: str,
) -> dict[int, int]:
    """
    Importeer gebruikers uit SQLite naar PostgreSQL.

    Deduplicatie op gebruikersnaam.
    Geeft een mapping {sqlite_id: pg_id} terug.
    """
    kolommen = kolommen_van_tabel(sqlite_db, "gebruikers")
    rijen = sqlite_db.execute("SELECT * FROM gebruikers").fetchall()

    mapping: dict[int, int] = {}
    for rij in rijen:
        gebruikersnaam = rij["gebruikersnaam"]

        # Deduplicatie op gebruikersnaam
        cur.execute(
            "SELECT id FROM gebruikers WHERE gebruikersnaam = %s", (gebruikersnaam,)
        )
        bestaande = cur.fetchone()
        if bestaande:
            mapping[rij["id"]] = bestaande[0]
            log.debug("    Gebruiker '%s' bestaat al (id=%s)", gebruikersnaam, bestaande[0])
            continue

        # UUID: v0.7 gebruikt 'gebruiker_uuid'
        g_uuid = None
        if "gebruiker_uuid" in kolommen and rij["gebruiker_uuid"]:
            g_uuid = rij["gebruiker_uuid"]
        elif "uuid" in kolommen and rij["uuid"]:
            g_uuid = rij["uuid"]
        else:
            g_uuid = genereer_uuid(f"{locatie_code}/gebruiker/{gebruikersnaam}")

        wachtwoord = verwerk_wachtwoord(rij["wachtwoord_hash"])
        rol_v7 = rij["rol"] if "rol" in kolommen else "teamlid"
        rol_v9 = ROL_MAPPING.get(rol_v7, "teamlid")

        volledige_naam = rij["volledige_naam"] if "volledige_naam" in kolommen else gebruikersnaam
        voornaam = rij["voornaam"] if "voornaam" in kolommen else None
        achternaam = rij["achternaam"] if "achternaam" in kolommen else None
        is_reserve = bool(rij["is_reserve"]) if "is_reserve" in kolommen else False
        startweek = rij["startweek_typedienst"] if "startweek_typedienst" in kolommen else None
        shift_vk = rij["shift_voorkeuren"] if "shift_voorkeuren" in kolommen else None
        is_actief = bool(rij["is_actief"]) if "is_actief" in kolommen else True
        aangemaakt = rij["aangemaakt_op"] if "aangemaakt_op" in kolommen else None
        gedeactiveerd = rij["gedeactiveerd_op"] if "gedeactiveerd_op" in kolommen else None
        laatste_login = rij["laatste_login"] if "laatste_login" in kolommen else None

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
            (g_uuid, gebruikersnaam, wachtwoord,
             volledige_naam or "", voornaam, achternaam,
             rol_v9, locatie_id, startweek, shift_vk,
             is_actief, aangemaakt, gedeactiveerd, laatste_login),
        )
        pg_id = cur.fetchone()[0]
        mapping[rij["id"]] = pg_id
        log.debug("    Gebruiker '%s' aangemaakt (id=%s)", gebruikersnaam, pg_id)

    log.info("  %s gebruikers verwerkt (%s nieuw)", len(rijen),
             sum(1 for v in mapping.values() if v not in []))
    return mapping


def importeer_gebruiker_rollen(
    sqlite_db: sqlite3.Connection,
    cur,
    locatie_id: int,
    gebruiker_mapping: dict[int, int],
    team_mapping: dict[int, int],
) -> None:
    """
    Maak GebruikerRol records aan in PostgreSQL op basis van rol in de SQLite gebruikerstabel.

    v0.7 heeft geen aparte rollen-tabel: de rol zit als kolom in de gebruikerstabel.
    We leiden de scope_id af uit de locatie (beheerder/hr) of het eerste team (teamlid/planner).
    """
    kolommen = kolommen_van_tabel(sqlite_db, "gebruikers")
    rijen = sqlite_db.execute("SELECT * FROM gebruikers").fetchall()

    eerste_team_id: Optional[int] = None
    if team_mapping:
        eerste_team_id = next(iter(team_mapping.values()))

    aangemaakt = 0
    for rij in rijen:
        sqlite_id = rij["id"]
        pg_gebruiker_id = gebruiker_mapping.get(sqlite_id)
        if pg_gebruiker_id is None:
            continue  # Gebruiker was al aanwezig, rol ook vermoedelijk al ok

        rol_v7 = rij["rol"] if "rol" in kolommen else "teamlid"
        rol_v9 = ROL_MAPPING.get(rol_v7, "teamlid")

        # Scope: beheerder/hr krijgen locatie_id; teamlid/planner krijgen team_id
        if rol_v9 in ("beheerder", "hr", "super_beheerder"):
            scope_id = locatie_id
        else:
            scope_id = eerste_team_id or locatie_id

        if scope_id is None:
            log.warning("    Geen scope_id voor gebruiker id=%s, overgeslagen", sqlite_id)
            continue

        cur.execute(
            """INSERT INTO gebruiker_rollen (gebruiker_id, rol, scope_id, is_reserve, is_actief)
               VALUES (%s, %s, %s, %s, TRUE)
               ON CONFLICT (gebruiker_id, rol, scope_id) DO NOTHING""",
            (pg_gebruiker_id, rol_v9, scope_id,
             bool(rij["is_reserve"]) if "is_reserve" in kolommen else False),
        )
        if cur.rowcount:
            aangemaakt += 1

    log.info("  %s gebruiker_rollen aangemaakt", aangemaakt)


def importeer_planning(
    sqlite_db: sqlite3.Connection,
    cur,
    gebruiker_mapping: dict[int, int],
    team_id: int,
) -> int:
    """
    Importeer planningshifts uit SQLite naar PostgreSQL.

    Deduplicatie op (gebruiker_id, datum) — PostgreSQL unique constraint.
    Geeft het aantal geïmporteerde records terug.
    """
    if not tabel_bestaat(sqlite_db, "planning"):
        return 0

    kolommen = kolommen_van_tabel(sqlite_db, "planning")
    rijen = sqlite_db.execute("SELECT * FROM planning").fetchall()

    aangemaakt = 0
    batch: list[tuple] = []
    for rij in rijen:
        sqlite_gebruiker_id = rij["gebruiker_id"]
        pg_gebruiker_id = gebruiker_mapping.get(sqlite_gebruiker_id)
        if pg_gebruiker_id is None:
            log.warning("    Planning: gebruiker_id=%s niet gevonden, overgeslagen", sqlite_gebruiker_id)
            continue

        plan_uuid = (
            rij["uuid"] if "uuid" in kolommen and rij["uuid"]
            else str(uuid.uuid4())
        )
        datum = rij["datum"]
        shift_code = rij["shift_code"] if "shift_code" in kolommen else None
        notitie = rij["notitie"] if "notitie" in kolommen else None
        notitie_gelezen = bool(rij["notitie_gelezen"]) if "notitie_gelezen" in kolommen else False
        status = (rij["status"] or "concept") if "status" in kolommen else "concept"
        aangemaakt_op = rij["aangemaakt_op"] if "aangemaakt_op" in kolommen else None

        batch.append((plan_uuid, pg_gebruiker_id, team_id, datum,
                      shift_code, notitie, notitie_gelezen, status, aangemaakt_op))

    if batch:
        for i in range(0, len(batch), 500):
            execute_values(
                cur,
                """INSERT INTO planning
                   (uuid, gebruiker_id, team_id, datum, shift_code,
                    notitie, notitie_gelezen, status, aangemaakt_op)
                   VALUES %s
                   ON CONFLICT (gebruiker_id, datum) DO NOTHING""",
                batch[i:i + 500],
            )
            aangemaakt += cur.rowcount

    log.info("  %s planning shifts geïmporteerd (van %s)", aangemaakt, len(batch))
    return aangemaakt


def importeer_verlof(
    sqlite_db: sqlite3.Connection,
    cur,
    gebruiker_mapping: dict[int, int],
) -> int:
    """
    Importeer verlofaanvragen uit SQLite naar PostgreSQL.

    Deduplicatie op uuid (als aanwezig), anders altijd invoegen.
    Geeft het aantal geïmporteerde records terug.
    """
    tabel = "verlof_aanvragen"
    if not tabel_bestaat(sqlite_db, tabel):
        return 0

    kolommen = kolommen_van_tabel(sqlite_db, tabel)
    rijen = sqlite_db.execute(f"SELECT * FROM {tabel}").fetchall()

    aangemaakt = 0
    for rij in rijen:
        sqlite_gebruiker_id = rij["gebruiker_id"]
        pg_gebruiker_id = gebruiker_mapping.get(sqlite_gebruiker_id)
        if pg_gebruiker_id is None:
            continue

        verlof_uuid = (
            rij["uuid"] if "uuid" in kolommen and rij["uuid"]
            else str(uuid.uuid4())
        )
        start = rij["start_datum"]
        eind = rij["eind_datum"]
        aantal = rij["aantal_dagen"] if "aantal_dagen" in kolommen else 1
        status = (rij["status"] or "pending") if "status" in kolommen else "pending"
        code_term = rij["toegekende_code_term"] if "toegekende_code_term" in kolommen else None
        opmerking = rij["opmerking"] if "opmerking" in kolommen else None
        aangevraagd = rij["aangevraagd_op"] if "aangevraagd_op" in kolommen else None
        behandeld_op = rij["behandeld_op"] if "behandeld_op" in kolommen else None
        reden = rij["reden_weigering"] if "reden_weigering" in kolommen else None

        cur.execute(
            """INSERT INTO verlof_aanvragen
               (uuid, gebruiker_id, start_datum, eind_datum, aantal_dagen,
                status, toegekende_code_term, opmerking, aangevraagd_op,
                behandeld_op, reden_weigering)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (uuid) DO NOTHING""",
            (verlof_uuid, pg_gebruiker_id, start, eind, aantal,
             status, code_term, opmerking, aangevraagd, behandeld_op, reden),
        )
        aangemaakt += cur.rowcount

    log.info("  %s verlofaanvragen geïmporteerd", aangemaakt)
    return aangemaakt


# ───────────────────────────────────────────────────── hoofdfunctie ── #

def migreer_een_database(sqlite_pad: Path, pg) -> None:
    """Migreer één SQLite-database naar PostgreSQL."""
    locatie_code = locatie_code_uit_bestandsnaam(sqlite_pad)
    locatie_naam = f"Locatie {locatie_code}"
    log.info("=" * 60)
    log.info("Migreren: %s → locatie '%s'", sqlite_pad.name, locatie_code)
    log.info("=" * 60)

    sqlite_db = lees_sqlite(sqlite_pad)
    cur = pg.cursor()

    try:
        # 1. Locatie
        log.info("Stap 1: Locatie")
        locatie_id = haal_of_maak_locatie(cur, locatie_code, locatie_naam)

        # 2. Teams
        log.info("Stap 2: Teams")
        team_mapping: dict[int, int] = {}
        tabel_teams = (
            "teams" if tabel_bestaat(sqlite_db, "teams")
            else "groepen" if tabel_bestaat(sqlite_db, "groepen")
            else None
        )
        if tabel_teams:
            kolommen_teams = kolommen_van_tabel(sqlite_db, tabel_teams)
            teams_rijen = sqlite_db.execute(f"SELECT * FROM {tabel_teams}").fetchall()
            for t in teams_rijen:
                naam = t["naam"] if "naam" in kolommen_teams else f"Team {t['id']}"
                code = (
                    t["code"] if "code" in kolommen_teams
                    else naam[:20].upper().replace(" ", "_")
                )
                pg_team_id = haal_of_maak_team(cur, naam, code, locatie_id)
                team_mapping[t["id"]] = pg_team_id
            log.info("  %s teams verwerkt", len(teams_rijen))
        else:
            # Geen teams-tabel: maak één standaard team aan
            log.info("  Geen teams-tabel — standaard team aanmaken")
            pg_team_id = haal_of_maak_team(cur, locatie_code, locatie_code, locatie_id)
            team_mapping[1] = pg_team_id

        eerste_pg_team_id = next(iter(team_mapping.values()))

        # 3. Werkposten
        log.info("Stap 3: Werkposten")
        werkpost_mapping = importeer_werkposten(sqlite_db, cur, locatie_id, locatie_code)

        # 4. Shiftcodes
        log.info("Stap 4: Shiftcodes")
        importeer_shiftcodes(sqlite_db, cur, locatie_id, locatie_code, werkpost_mapping)

        # 5. Gebruikers
        log.info("Stap 5: Gebruikers")
        gebruiker_mapping = importeer_gebruikers(sqlite_db, cur, locatie_id, locatie_code)

        # 6. Gebruiker-rollen
        log.info("Stap 6: Gebruiker-rollen")
        importeer_gebruiker_rollen(sqlite_db, cur, locatie_id, gebruiker_mapping, team_mapping)

        # 7. Planning
        log.info("Stap 7: Planning")
        importeer_planning(sqlite_db, cur, gebruiker_mapping, eerste_pg_team_id)

        # 8. Verlof
        log.info("Stap 8: Verlofaanvragen")
        importeer_verlof(sqlite_db, cur, gebruiker_mapping)

        pg.commit()
        log.info("✓ Migratie '%s' succesvol afgerond", locatie_code)

    except Exception as fout:
        pg.rollback()
        log.error("✗ Migratie '%s' mislukt: %s", locatie_code, fout, exc_info=True)
        raise
    finally:
        sqlite_db.close()
        cur.close()


def zoek_sqlite_bestanden() -> list[Path]:
    """Zoek automatisch SQLite-bestanden in /data/ als geen argumenten meegegeven."""
    if not DATA_DIR.exists():
        return []
    return sorted(DATA_DIR.glob("*.db"))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        paden = [Path(p) for p in sys.argv[1:]]
    else:
        paden = zoek_sqlite_bestanden()
        if not paden:
            log.error("Geen .db bestanden gevonden in %s en geen argumenten meegegeven.", DATA_DIR)
            log.error("Gebruik: python migreer_sqlite_multi.py /pad/naar/database.PAT.db ...")
            sys.exit(1)

    log.info("Te migreren: %s", [str(p) for p in paden])

    pg = pg_verbinding()
    try:
        for pad in paden:
            migreer_een_database(pad, pg)
        log.info("=" * 60)
        log.info("Alle databases gemigreerd!")
    except Exception:
        sys.exit(1)
    finally:
        pg.close()
