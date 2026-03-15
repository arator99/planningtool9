"""
Migratiescript: v0.7 SQLite → v0.8 PostgreSQL
Gebruik: docker compose run --rm -v "C:/pad/naar/database.db:/data/database.db" app python /app/scripts/migreer_sqlite.py
"""

import logging
import os
import sqlite3
import sys

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

SQLITE_PAD = "/data/database.db"
DATABASE_URL = os.environ["DATABASE_URL"]  # postgresql://user:pass@host/db

ROL_MAPPING = {
    "beheerder": "beheerder",
    "planner":   "planner",
    "hr":        "hr",
    "teamlid":   "gebruiker",
    "gebruiker": "gebruiker",
}


def pg_verbinding():
    # Converteer SQLAlchemy URL naar psycopg2 DSN
    dsn = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(dsn)


def lees_sqlite():
    if not os.path.exists(SQLITE_PAD):
        log.error("SQLite database niet gevonden: %s", SQLITE_PAD)
        sys.exit(1)
    db = sqlite3.connect(SQLITE_PAD)
    db.row_factory = sqlite3.Row
    return db


def verwerk_wachtwoord(hash_waarde) -> str:
    """Bcrypt hash kan bytes of string zijn in SQLite."""
    if isinstance(hash_waarde, bytes):
        return hash_waarde.decode("utf-8")
    return str(hash_waarde)


def migreer(sqlite_db, pg):
    cur = pg.cursor()

    # Haal groep_id op uit PostgreSQL (eerste groep)
    cur.execute("SELECT id, naam FROM groepen LIMIT 1")
    groep = cur.fetchone()
    if not groep:
        log.error("Geen groep gevonden in PostgreSQL. Start eerst de app zodat seed data aangemaakt wordt.")
        sys.exit(1)
    groep_id, groep_naam = groep
    log.info("Groep gevonden: '%s' (id=%s)", groep_naam, groep_id)

    # ------------------------------------------------------------------ #
    # Opruimen (in omgekeerde FK volgorde)                                 #
    # ------------------------------------------------------------------ #
    log.info("Bestaande data opruimen...")
    # Tabellen met groep_id (CASCADE verwijdert planning_overrides, notificaties, gebruiker_competenties)
    tabellen_met_groep = [
        "planning", "verlof_aanvragen",
        "notities", "audit_log", "competenties",
        "rode_lijnen", "hr_regels",
        "shiftcodes", "werkposten",
        "gebruikers",
    ]
    for tabel in tabellen_met_groep:
        cur.execute(f"DELETE FROM {tabel} WHERE groep_id = %s", (groep_id,))
        log.info("  %s: %s rijen verwijderd", tabel, cur.rowcount)
    # Tabellen zonder groep_id — volledig leegmaken
    for tabel in ("special_codes", "shift_tijden"):
        cur.execute(f"DELETE FROM {tabel}")
        log.info("  %s: %s rijen verwijderd", tabel, cur.rowcount)

    # ------------------------------------------------------------------ #
    # Gebruikers                                                           #
    # ------------------------------------------------------------------ #
    log.info("Gebruikers importeren...")
    gebruikers = sqlite_db.execute("SELECT * FROM gebruikers").fetchall()
    gebruiker_data = []
    for g in gebruikers:
        rol = ROL_MAPPING.get(g["rol"], "gebruiker")
        wachtwoord = verwerk_wachtwoord(g["wachtwoord_hash"])
        gebruiker_data.append((
            g["id"], g["gebruiker_uuid"], g["gebruikersnaam"], wachtwoord,
            g["volledige_naam"] or "", g["voornaam"], g["achternaam"],
            rol, groep_id,
            bool(g["is_reserve"]), g["startweek_typedienst"], g["shift_voorkeuren"],
            "systeem", "nl",  # thema default; v0.7 had geen dark mode
            False, None,  # totp_actief, totp_geheim
            bool(g["is_actief"]), g["aangemaakt_op"], g["gedeactiveerd_op"], g["laatste_login"],
        ))
    execute_values(cur, """
        INSERT INTO gebruikers
            (id, gebruiker_uuid, gebruikersnaam, gehashed_wachtwoord,
             volledige_naam, voornaam, achternaam, rol, groep_id,
             is_reserve, startweek_typedienst, shift_voorkeuren,
             thema, taal,
             totp_actief, totp_geheim,
             is_actief, aangemaakt_op, gedeactiveerd_op, laatste_login)
        VALUES %s
        ON CONFLICT (id) DO NOTHING
    """, gebruiker_data)
    # Herstel sequence
    cur.execute("SELECT setval('gebruikers_id_seq', (SELECT MAX(id) FROM gebruikers))")
    log.info("  %s gebruikers geïmporteerd", len(gebruiker_data))

    # ------------------------------------------------------------------ #
    # Werkposten                                                           #
    # ------------------------------------------------------------------ #
    log.info("Werkposten importeren...")
    werkposten = sqlite_db.execute("SELECT * FROM werkposten").fetchall()
    wp_data = [(
        w["id"], groep_id, w["naam"], w["beschrijving"],
        bool(w["telt_als_werkdag"]), bool(w["reset_12u_rust"]), bool(w["breekt_werk_reeks"]),
        bool(w["is_actief"]), w["aangemaakt_op"], w["gedeactiveerd_op"],
    ) for w in werkposten]
    execute_values(cur, """
        INSERT INTO werkposten
            (id, groep_id, naam, beschrijving,
             telt_als_werkdag, reset_12u_rust, breekt_werk_reeks,
             is_actief, aangemaakt_op, gedeactiveerd_op)
        VALUES %s ON CONFLICT (id) DO NOTHING
    """, wp_data)
    cur.execute("SELECT setval('werkposten_id_seq', (SELECT MAX(id) FROM werkposten))")
    log.info("  %s werkposten geïmporteerd", len(wp_data))

    # ------------------------------------------------------------------ #
    # Shiftcodes                                                           #
    # ------------------------------------------------------------------ #
    log.info("Shiftcodes importeren...")
    shiftcodes = sqlite_db.execute("SELECT * FROM shift_codes").fetchall()
    sc_data = [(
        s["id"], s["werkpost_id"], groep_id,
        s["dag_type"], s["shift_type"], s["code"],
        s["start_uur"], s["eind_uur"], bool(s["is_kritisch"]),
    ) for s in shiftcodes]
    execute_values(cur, """
        INSERT INTO shiftcodes
            (id, werkpost_id, groep_id, dag_type, shift_type, code, start_uur, eind_uur, is_kritisch)
        VALUES %s ON CONFLICT (id) DO NOTHING
    """, sc_data)
    cur.execute("SELECT setval('shiftcodes_id_seq', (SELECT MAX(id) FROM shiftcodes))")
    log.info("  %s shiftcodes geïmporteerd", len(sc_data))

    # ------------------------------------------------------------------ #
    # Speciale codes                                                       #
    # ------------------------------------------------------------------ #
    log.info("Speciale codes importeren...")
    spec = sqlite_db.execute("SELECT * FROM speciale_codes").fetchall()
    spec_data = [(
        s["id"], s["code"], s["naam"], s["term"],
        bool(s["telt_als_werkdag"]), bool(s["reset_12u_rust"]), bool(s["breekt_werk_reeks"]),
    ) for s in spec]
    execute_values(cur, """
        INSERT INTO special_codes (id, code, naam, term, telt_als_werkdag, reset_12u_rust, breekt_werk_reeks)
        VALUES %s ON CONFLICT (id) DO NOTHING
    """, spec_data)
    cur.execute("SELECT setval('special_codes_id_seq', (SELECT MAX(id) FROM special_codes))")
    log.info("  %s speciale codes geïmporteerd", len(spec_data))

    # ------------------------------------------------------------------ #
    # HR Regels                                                            #
    # ------------------------------------------------------------------ #
    log.info("HR regels importeren...")
    regels = sqlite_db.execute("SELECT * FROM hr_regels").fetchall()
    hr_data = [(
        r["id"], groep_id, r["code"], r["naam"],
        r["waarde"], r["waarde_extra"], r["eenheid"],
        r["ernst_niveau"] or "WARNING", bool(r["is_actief"]), r["beschrijving"],
    ) for r in regels]
    execute_values(cur, """
        INSERT INTO hr_regels
            (id, groep_id, code, naam, waarde, waarde_extra, eenheid, ernst_niveau, is_actief, beschrijving)
        VALUES %s ON CONFLICT (id) DO NOTHING
    """, hr_data)
    cur.execute("SELECT setval('hr_regels_id_seq', (SELECT MAX(id) FROM hr_regels))")
    log.info("  %s HR regels geïmporteerd", len(hr_data))

    # ------------------------------------------------------------------ #
    # Rode lijnen                                                          #
    # ------------------------------------------------------------------ #
    log.info("Rode lijnen importeren...")
    rode = sqlite_db.execute("SELECT * FROM rode_lijnen").fetchall()
    rode_data = [(r["id"], groep_id, r["start_datum"], r["interval_dagen"], bool(r["is_actief"])) for r in rode]
    execute_values(cur, """
        INSERT INTO rode_lijnen (id, groep_id, start_datum, interval_dagen, is_actief)
        VALUES %s ON CONFLICT (id) DO NOTHING
    """, rode_data)
    if rode_data:
        cur.execute("SELECT setval('rode_lijnen_id_seq', (SELECT MAX(id) FROM rode_lijnen))")
    log.info("  %s rode lijnen geïmporteerd", len(rode_data))

    # ------------------------------------------------------------------ #
    # Planning                                                             #
    # ------------------------------------------------------------------ #
    log.info("Planning importeren (1666 shifts)...")
    planning = sqlite_db.execute("SELECT * FROM planning").fetchall()
    plan_data = [(
        p["id"], p["gebruiker_id"], groep_id, p["datum"],
        p["shift_code"], p["notitie"], bool(p["notitie_gelezen"]),
        p["status"] or "concept", p["aangemaakt_op"],
    ) for p in planning]
    # In batches van 500
    for i in range(0, len(plan_data), 500):
        execute_values(cur, """
            INSERT INTO planning
                (id, gebruiker_id, groep_id, datum, shift_code, notitie, notitie_gelezen, status, aangemaakt_op)
            VALUES %s ON CONFLICT (gebruiker_id, datum) DO NOTHING
        """, plan_data[i:i+500])
    cur.execute("SELECT setval('planning_id_seq', (SELECT MAX(id) FROM planning))")
    log.info("  %s planning shifts geïmporteerd", len(plan_data))

    # ------------------------------------------------------------------ #
    # Verlofaanvragen                                                      #
    # ------------------------------------------------------------------ #
    log.info("Verlofaanvragen importeren...")
    verlof = sqlite_db.execute("SELECT * FROM verlof_aanvragen").fetchall()

    # Status mapping: v0.7 gebruikt 'goedgekeurd'/'geweigerd'/'pending' — zelfde als v0.8
    verlof_data = [(
        v["id"], v["gebruiker_id"], groep_id,
        v["start_datum"], v["eind_datum"], v["aantal_dagen"],
        v["status"] or "pending", v["toegekende_code_term"], v["opmerking"],
        v["aangevraagd_op"], v["behandeld_door"], v["behandeld_op"], v["reden_weigering"],
    ) for v in verlof]
    execute_values(cur, """
        INSERT INTO verlof_aanvragen
            (id, gebruiker_id, groep_id,
             start_datum, eind_datum, aantal_dagen,
             status, toegekende_code_term, opmerking,
             aangevraagd_op, behandeld_door, behandeld_op, reden_weigering)
        VALUES %s ON CONFLICT (id) DO NOTHING
    """, verlof_data)
    cur.execute("SELECT setval('verlof_aanvragen_id_seq', (SELECT MAX(id) FROM verlof_aanvragen))")
    log.info("  %s verlofaanvragen geïmporteerd", len(verlof_data))

    pg.commit()
    log.info("=" * 50)
    log.info("Migratie voltooid!")
    log.info("  Gebruikers  : %s", len(gebruiker_data))
    log.info("  Werkposten  : %s", len(wp_data))
    log.info("  Shiftcodes  : %s", len(sc_data))
    log.info("  HR regels   : %s", len(hr_data))
    log.info("  Planning    : %s shifts", len(plan_data))
    log.info("  Verlof      : %s aanvragen", len(verlof_data))
    log.info("=" * 50)


if __name__ == "__main__":
    log.info("Migratie gestart: SQLite → PostgreSQL")
    sqlite_db = lees_sqlite()
    pg = pg_verbinding()
    try:
        migreer(sqlite_db, pg)
    except Exception as e:
        pg.rollback()
        log.error("Migratie mislukt: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        sqlite_db.close()
        pg.close()
