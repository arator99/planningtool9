"""
migreer_sqlite.py — Importeer v0.7 SQLite data naar v0.9 PostgreSQL.

Gebruik:
    python migreer_sqlite.py --pat docs/referentie/database.PAT.db \
                             --to  docs/referentie/database.TO.db

Wat wordt geïmporteerd (Fase 2 scope):
    ✅ RodeLijnConfig.referentie_datum  (uit PAT.db rode_lijnen_config)
    ✅ Shiftcodes (generieke + werkpost-specifiek, uit beide db's)
    ✅ Werkposten (als FK-basis voor werkpost-specifieke shiftcodes)

Wat NIET in dit script zit (later, Fase 11):
    ⬜ Gebruikers + GebruikerRol
    ⬜ Planning (shifts per dag per medewerker)
    ⬜ Verlof aanvragen + saldi
    ⬜ Notities

Veldmapping shift_codes (v0.7 → v0.9 Shiftcode):
    code              → code
    start_uur         → start_uur
    eind_uur          → eind_uur
    werkpost_id       → werkpost_id  (nullable, na werkpost-import)
    dag_type          → dag_type
    shift_type        → shift_type
    is_kritisch       → is_kritisch
    telt_als_werkdag  → telt_als_werkdag
    reset_12u_rust    → reset_nacht  (bool: heft nacht-beperking op)
    shift_type='nacht'→ is_nachtprestatie  (afgeleid)
"""
import argparse
import logging
import sqlite3
import sys
import uuid
from datetime import date
from pathlib import Path

# Voeg backend aan sys.path toe zodat imports werken
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.orm import Session

from database import SessieKlasse, motor, Basis
import models  # noqa: F401 — registreert alle ORM modellen

from models.planning import Shiftcode, RodeLijnConfig
from models.locatie import Locatie
from models.team import Team

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _open_sqlite(pad: str) -> sqlite3.Connection:
    conn = sqlite3.connect(pad)
    conn.row_factory = sqlite3.Row
    return conn


def _is_nachtprestatie(shift_type: str | None) -> bool:
    """Een nachtshift activeert de nacht-vervolgingsbeperking (12u rust + vervolgbeperking)."""
    return (shift_type or "").lower() in ("nacht", "night")


def _reset_nacht(reset_12u_rust: bool, shift_type: str | None) -> bool:
    """
    Bepaal of een shiftcode de nacht-vervolgingsbeperking opheft.

    Businessregel: na een nachtshift kan je NIET direct naar een vroege of dagshift,
    tenzij er een tussendag is met VV, KD of Z. Dat zijn de "reset"-codes.

    reset_12u_rust=True staat ook op nachtshifts zelf — maar die resetten hun
    eigen beperking uiteraard NIET. Alleen niet-nachtcodes met reset_12u_rust=True
    zijn echte reset-codes (VV, KD, Z, VD, ...).
    """
    return reset_12u_rust and not _is_nachtprestatie(shift_type)


# ------------------------------------------------------------------ #
# RodeLijnConfig                                                      #
# ------------------------------------------------------------------ #

def migreer_rode_lijn(db: Session, pat_conn: sqlite3.Connection) -> None:
    """Importeer referentiedatum van rode lijn uit PAT.db (beide db's hebben dezelfde datum)."""
    row = pat_conn.execute(
        "SELECT start_datum FROM rode_lijnen_config WHERE is_actief = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if not row:
        logger.warning("Geen actieve rode_lijnen_config gevonden in PAT.db — overgeslagen.")
        return

    ref_datum = date.fromisoformat(row["start_datum"])
    bestaand = db.query(RodeLijnConfig).first()
    if bestaand:
        logger.info("RodeLijnConfig bestaat al (referentie_datum=%s) — overgeslagen.", bestaand.referentie_datum)
        return

    db.add(RodeLijnConfig(referentie_datum=ref_datum))
    db.flush()
    logger.info("RodeLijnConfig aangemaakt: referentie_datum=%s", ref_datum)


# ------------------------------------------------------------------ #
# Shiftcodes                                                          #
# ------------------------------------------------------------------ #

def migreer_shiftcodes(
    db: Session,
    conn: sqlite3.Connection,
    locatie_id: int | None,
    team_code: str,
    werkpost_uuid_map: dict[int, int],
) -> tuple[int, int]:
    """
    Importeer shiftcodes uit één SQLite-database.

    Args:
        db:              SQLAlchemy sessie
        conn:            Geopende SQLite connectie
        locatie_id:      locatie_id voor werkpost-specifieke codes (None = nationaal)
        team_code:       Naam van de db voor logging ('PAT' of 'TO')
        werkpost_uuid_map: {v0.7 werkpost_id → v0.9 werkpost_id}

    Returns:
        (nieuw, overgeslagen) teller tuple
    """
    rows = conn.execute("SELECT * FROM shift_codes ORDER BY code").fetchall()
    nieuw = 0
    overgeslagen = 0

    for row in rows:
        r = dict(row)
        code = r["code"]

        # Generieke codes (werkpost_id=None) zijn nationaal beschikbaar (locatie_id=None).
        # Werkpost-specifieke codes zijn gekoppeld aan hun locatie.
        v07_werkpost_id = r.get("werkpost_id")
        is_generiek = v07_werkpost_id is None

        effectieve_locatie_id = None if is_generiek else locatie_id
        v09_werkpost_id = werkpost_uuid_map.get(v07_werkpost_id) if v07_werkpost_id else None

        # Check of code al bestaat (generiek: code only; werkpost-specifiek: code + locatie)
        bestaand_query = db.query(Shiftcode).filter(Shiftcode.code == code)
        if is_generiek:
            bestaand_query = bestaand_query.filter(Shiftcode.locatie_id.is_(None))
        else:
            bestaand_query = bestaand_query.filter(Shiftcode.locatie_id == effectieve_locatie_id)

        if bestaand_query.first():
            overgeslagen += 1
            continue

        v07_shift_type = r.get("shift_type")
        v07_reset_12u = bool(r.get("reset_12u_rust", True))

        shiftcode = Shiftcode(
            uuid=str(uuid.uuid4()),
            code=code,
            beschrijving=r.get("beschrijving"),
            werkpost_id=v09_werkpost_id,
            locatie_id=effectieve_locatie_id,
            dag_type=r.get("dag_type"),
            shift_type=v07_shift_type,   # Dutch values bewaard: 'vroeg', 'laat', 'nacht'
            start_uur=r.get("start_uur"),
            eind_uur=r.get("eind_uur"),
            is_kritisch=bool(r.get("is_kritisch", False)),
            telt_als_werkdag=bool(r.get("telt_als_werkdag", True)),
            is_nachtprestatie=_is_nachtprestatie(v07_shift_type),
            reset_nacht=_reset_nacht(v07_reset_12u, v07_shift_type),
        )
        db.add(shiftcode)
        nieuw += 1

    db.flush()
    logger.info("[%s] Shiftcodes: %d nieuw, %d overgeslagen.", team_code, nieuw, overgeslagen)
    return nieuw, overgeslagen


def _bouw_werkpost_map(
    db: Session,
    conn: sqlite3.Connection,
    locatie_id: int,
    team_code: str,
) -> dict[int, int]:
    """
    Zorg dat werkposten bestaan in v0.9 en geef een {v0.7_id → v0.9_id} map terug.
    Werkposten worden aangemaakt als ze nog niet bestaan (op naam + locatie_id).
    """
    from models.planning import Werkpost
    import uuid as uuid_module

    rows = conn.execute("SELECT * FROM werkposten ORDER BY id").fetchall()
    id_map: dict[int, int] = {}

    for row in rows:
        r = dict(row)
        naam = r.get("naam") or r.get("code") or f"Werkpost {r['id']}"
        bestaand = db.query(Werkpost).filter(
            Werkpost.naam == naam,
            Werkpost.locatie_id == locatie_id,
        ).first()
        if bestaand:
            id_map[r["id"]] = bestaand.id
        else:
            wp = Werkpost(
                uuid=str(uuid_module.uuid4()),
                naam=naam,
                locatie_id=locatie_id,
                beschrijving=r.get("beschrijving"),
                is_actief=True,
            )
            db.add(wp)
            db.flush()
            id_map[r["id"]] = wp.id
            logger.info("[%s] Werkpost aangemaakt: %s", team_code, naam)

    return id_map


# ------------------------------------------------------------------ #
# Hoofdfunctie                                                        #
# ------------------------------------------------------------------ #

def migreer(pat_pad: str, to_pad: str) -> None:
    Basis.metadata.create_all(bind=motor)
    db: Session = SessieKlasse()

    try:
        pat_conn = _open_sqlite(pat_pad)
        to_conn = _open_sqlite(to_pad)

        # Locatie ophalen (we verwachten dat LOC1 al bestaat via seed)
        locatie = db.query(Locatie).filter(Locatie.code == "LOC1").first()
        if not locatie:
            logger.error("Locatie 'LOC1' niet gevonden. Zorg dat de app minstens één keer opgestart is (seed).")
            sys.exit(1)

        logger.info("Locatie gevonden: %s (id=%d)", locatie.naam, locatie.id)

        # ── RodeLijnConfig ────────────────────────────────────────────
        logger.info("--- RodeLijnConfig ---")
        migreer_rode_lijn(db, pat_conn)

        # ── Werkposten + Shiftcodes PAT ───────────────────────────────
        logger.info("--- Shiftcodes PAT ---")
        pat_werkpost_map = _bouw_werkpost_map(db, pat_conn, locatie.id, "PAT")
        migreer_shiftcodes(db, pat_conn, locatie.id, "PAT", pat_werkpost_map)

        # ── Werkposten + Shiftcodes TO ────────────────────────────────
        logger.info("--- Shiftcodes TO ---")
        to_werkpost_map = _bouw_werkpost_map(db, to_conn, locatie.id, "TO")
        migreer_shiftcodes(db, to_conn, locatie.id, "TO", to_werkpost_map)

        db.commit()
        logger.info("✅  Migratie voltooid.")

    except Exception as fout:
        logger.error("❌  Migratie mislukt: %s", fout, exc_info=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()
        pat_conn.close()
        to_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migreer v0.7 SQLite data naar v0.9 PostgreSQL.")
    parser.add_argument("--pat", required=True, help="Pad naar database.PAT.db")
    parser.add_argument("--to",  required=True, help="Pad naar database.TO.db")
    args = parser.parse_args()

    migreer(args.pat, args.to)
