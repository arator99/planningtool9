"""
migreer_sqlite.py — Importeer v0.7 SQLite data naar v0.9 PostgreSQL.

Gebruik:
    python migreer_sqlite.py --pat docs/referentie/database.PAT.db \
                             --to  docs/referentie/database.TO.db

Wat wordt geïmporteerd:
    ✅ RodeLijnConfig.referentie_datum  (uit PAT.db rode_lijnen_config)
    ✅ Werkposten (als FK-basis voor werkpost-specifieke shiftcodes)
    ✅ Shiftcodes (generieke + werkpost-specifiek, uit beide db's)
    ✅ Gebruikers + GebruikerRol  (bcrypt-hash rechtstreeks overgenomen)
    ✅ Planning (shifts per dag per medewerker)
    ✅ VerlofAanvraag + VerlofTeamStatus + VerlofSaldo
    ✅ Notities (directe berichten + planner-mailboxberichten)

Rolveldmapping (v0.7 → v0.9 GebruikerRol):
    teamlid   → teamlid  (scope=team_id)
    planner   → planner  (scope=team_id)
    beheerder → beheerder (scope=locatie_id) + teamlid (scope=team_id)

Wachtwoordbeleid:
    v0.7-hashes zijn bcrypt ($2b$). De v0.9 auth_domein herkent dit prefix
    en verifieert via bcrypt — gebruikers kunnen meteen inloggen.
    Na eerste login upgradet auth_service de hash automatisch naar argon2.

Notitie-mapping:
    naar_gebruiker_id > 0   → directe notitie (naar_gebruiker_id gemapped)
    naar_gebruiker_id <= 0  → planners-mailbox (naar_rol='planners', scope=team_id)
"""
import argparse
import logging
import sqlite3
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

# Voeg backend aan sys.path toe zodat imports werken
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessieKlasse, motor, Basis
import models  # noqa: F401 — registreert alle ORM modellen

from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol
from models.locatie import Locatie
from models.notitie import Notitie
from models.planning import Shiftcode, RodeLijnConfig
from models.team import Team
from models.verlof import VerlofAanvraag, VerlofTeamStatus
from models.verlof_saldo import VerlofSaldo

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


def _map_rol(v07_rol: str) -> str:
    """Zet een v0.7 rol om naar de corresponderende v0.9 rol."""
    mapping = {
        "beheerder": "beheerder",
        "planner": "planner",
        "teamlid": "teamlid",
        "hr": "hr",
        "super_beheerder": "super_beheerder",
    }
    return mapping.get(v07_rol or "", "teamlid")


def _parse_datum(waarde: str | None) -> date | None:
    if not waarde:
        return None
    try:
        return date.fromisoformat(waarde[:10])
    except (ValueError, TypeError):
        return None


def _parse_datetime(waarde: str | None) -> datetime | None:
    if not waarde:
        return None
    try:
        return datetime.fromisoformat(waarde)
    except (ValueError, TypeError):
        return None


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
# Werkposten                                                          #
# ------------------------------------------------------------------ #

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


# ------------------------------------------------------------------ #
# Gebruikers + GebruikerRol                                           #
# ------------------------------------------------------------------ #

def migreer_gebruikers(
    db: Session,
    conn: sqlite3.Connection,
    team_code: str,
    locatie: Locatie,
    team: Team,
    gedeelde_map: dict[str, int],
) -> dict[int, int]:
    """
    Importeer gebruikers en GebruikerRol records uit één SQLite-database.

    Bcrypt-hashes worden rechtstreeks overgenomen — de v0.9 auth_domein
    ondersteunt verificatie van legacy bcrypt-hashes.

    Args:
        gedeelde_map: {gebruikersnaam → v0.9 gebruiker_id}, gedeeld over beide db's
                      zodat dubbele gebruikers correct worden herkend.

    Returns:
        {v0.7 gebruiker_id → v0.9 gebruiker_id}
    """
    rows = conn.execute(
        "SELECT * FROM gebruikers WHERE id > 0 ORDER BY id"
    ).fetchall()
    id_map: dict[int, int] = {}
    nieuw = 0
    bestaand_ct = 0

    for row in rows:
        r = dict(row)
        v07_id = r["id"]
        username = r["gebruikersnaam"]
        v07_rol = _map_rol(r.get("rol", "teamlid"))

        # Gebruik bestaande v0.9 gebruiker als al geïmporteerd (uit andere db)
        if username in gedeelde_map:
            id_map[v07_id] = gedeelde_map[username]
            bestaand_ct += 1
        else:
            bestaand = db.query(Gebruiker).filter(Gebruiker.gebruikersnaam == username).first()
            if bestaand:
                gedeelde_map[username] = bestaand.id
                id_map[v07_id] = bestaand.id
                bestaand_ct += 1
            else:
                # Converteer BLOB-hash naar str voor opslag
                raw_hash = r.get("wachtwoord_hash") or b""
                if isinstance(raw_hash, bytes):
                    gehashed = raw_hash.decode("utf-8", errors="replace")
                else:
                    gehashed = str(raw_hash)

                g = Gebruiker(
                    uuid=r.get("gebruiker_uuid") or str(uuid.uuid4()),
                    gebruikersnaam=username,
                    gehashed_wachtwoord=gehashed,
                    volledige_naam=r.get("volledige_naam") or username,
                    voornaam=r.get("voornaam"),
                    achternaam=r.get("achternaam"),
                    rol=v07_rol,
                    locatie_id=locatie.id,
                    startweek_typedienst=r.get("startweek_typedienst"),
                    shift_voorkeuren=r.get("shift_voorkeuren"),
                    thema=r.get("theme_voorkeur") or "systeem",
                    is_actief=bool(r.get("is_actief", 1)),
                )
                db.add(g)
                db.flush()
                gedeelde_map[username] = g.id
                id_map[v07_id] = g.id
                nieuw += 1

        v09_gebruiker_id = id_map[v07_id]

        # GebruikerRol aanmaken voor dit team
        _voeg_rol_toe(db, v09_gebruiker_id, v07_rol, team, locatie)

    db.flush()
    logger.info("[%s] Gebruikers: %d nieuw, %d al aanwezig.", team_code, nieuw, bestaand_ct)
    return id_map


def _voeg_rol_toe(
    db: Session,
    gebruiker_id: int,
    rol: str,
    team: Team,
    locatie: Locatie,
) -> None:
    """
    Voeg GebruikerRol(s) toe voor een gebruiker op basis van zijn rol.

    Beheerder krijgt twee rollen: beheerder (locatie-scope) + teamlid (team-scope).
    Planner en teamlid krijgen één rol (team-scope).
    """
    if rol == "beheerder":
        # Beheerder-scope op locatieniveau
        _zet_rol(db, gebruiker_id, "beheerder", locatie.id, is_reserve=False)
        # Ook teamlid-scope zodat ze in het planning-overzicht staan
        _zet_rol(db, gebruiker_id, "teamlid", team.id, is_reserve=False)
    elif rol in ("planner", "teamlid", "hr"):
        _zet_rol(db, gebruiker_id, rol, team.id, is_reserve=False)
    elif rol == "super_beheerder":
        # super_beheerder scope = NAT locatie — niet aangemaakt via migratie
        logger.warning("super_beheerder %d overgeslagen voor GebruikerRol — voeg handmatig toe.", gebruiker_id)


def _zet_rol(
    db: Session,
    gebruiker_id: int,
    rol: str,
    scope_id: int,
    is_reserve: bool,
) -> None:
    """Maak GebruikerRol aan als die nog niet bestaat."""
    bestaand = db.query(GebruikerRol).filter(
        GebruikerRol.gebruiker_id == gebruiker_id,
        GebruikerRol.rol == rol,
        GebruikerRol.scope_id == scope_id,
    ).first()
    if not bestaand:
        db.add(GebruikerRol(
            gebruiker_id=gebruiker_id,
            rol=rol,
            scope_id=scope_id,
            is_reserve=is_reserve,
            is_actief=True,
        ))


# ------------------------------------------------------------------ #
# Planning                                                            #
# ------------------------------------------------------------------ #

def migreer_planning(
    db: Session,
    conn: sqlite3.Connection,
    team_code: str,
    team: Team,
    gebruiker_id_map: dict[int, int],
) -> tuple[int, int]:
    """
    Importeer planning-shifts uit één SQLite-database.

    Args:
        gebruiker_id_map: {v0.7 gebruiker_id → v0.9 gebruiker_id}

    Returns:
        (nieuw, overgeslagen)
    """
    from models.planning import Planning
    rows = conn.execute(
        "SELECT * FROM planning ORDER BY gebruiker_id, datum"
    ).fetchall()
    nieuw = 0
    overgeslagen = 0

    for row in rows:
        r = dict(row)
        v07_uid = r.get("gebruiker_id")
        v09_uid = gebruiker_id_map.get(v07_uid)
        if not v09_uid:
            overgeslagen += 1
            continue

        datum_str = r.get("datum")
        if not datum_str:
            overgeslagen += 1
            continue
        datum = _parse_datum(datum_str)
        if not datum:
            overgeslagen += 1
            continue

        # UniqueConstraint op (gebruiker_id, datum) — sla dubbelen over
        bestaand = db.query(Planning).filter(
            Planning.gebruiker_id == v09_uid,
            Planning.datum == datum,
        ).first()
        if bestaand:
            overgeslagen += 1
            continue

        shift = Planning(
            uuid=str(uuid.uuid4()),
            gebruiker_id=v09_uid,
            team_id=team.id,
            datum=datum,
            shift_code=r.get("shift_code"),
            notitie=r.get("notitie"),
            notitie_gelezen=bool(r.get("notitie_gelezen", False)),
            status=r.get("status") or "concept",
        )
        db.add(shift)
        nieuw += 1

        # Flush periodiek om geheugen te beperken
        if nieuw % 500 == 0:
            db.flush()

    db.flush()
    logger.info("[%s] Planning: %d nieuw, %d overgeslagen.", team_code, nieuw, overgeslagen)
    return nieuw, overgeslagen


# ------------------------------------------------------------------ #
# Verlof                                                              #
# ------------------------------------------------------------------ #

def migreer_verlof_aanvragen(
    db: Session,
    conn: sqlite3.Connection,
    team_code: str,
    team: Team,
    gebruiker_id_map: dict[int, int],
) -> tuple[int, int]:
    """
    Importeer verlof aanvragen en bijbehorende VerlofTeamStatus records.

    Returns:
        (nieuw, overgeslagen)
    """
    rows = conn.execute("SELECT * FROM verlof_aanvragen ORDER BY id").fetchall()
    nieuw = 0
    overgeslagen = 0

    for row in rows:
        r = dict(row)
        v09_uid = gebruiker_id_map.get(r.get("gebruiker_id"))
        if not v09_uid:
            overgeslagen += 1
            continue

        start = _parse_datum(r.get("start_datum"))
        eind = _parse_datum(r.get("eind_datum"))
        if not start or not eind:
            overgeslagen += 1
            continue

        # Controleer of aanvraag al bestaat (zelfde gebruiker + periode)
        bestaand = db.query(VerlofAanvraag).filter(
            VerlofAanvraag.gebruiker_id == v09_uid,
            VerlofAanvraag.start_datum == start,
            VerlofAanvraag.eind_datum == eind,
        ).first()
        if bestaand:
            overgeslagen += 1
            continue

        v07_status = r.get("status") or "pending"
        behandeld_door = gebruiker_id_map.get(r.get("behandeld_door"))
        ingediend_door = gebruiker_id_map.get(r.get("ingediend_door")) if r.get("ingediend_door") else None

        aanvraag = VerlofAanvraag(
            uuid=str(uuid.uuid4()),
            gebruiker_id=v09_uid,
            start_datum=start,
            eind_datum=eind,
            aantal_dagen=r.get("aantal_dagen") or 1,
            status=v07_status,
            toegekende_code_term=r.get("toegekende_code_term"),
            opmerking=r.get("opmerking"),
            aangevraagd_op=_parse_datetime(r.get("aangevraagd_op")),
            behandeld_door=behandeld_door,
            behandeld_op=_parse_datetime(r.get("behandeld_op")),
            reden_weigering=r.get("reden_weigering"),
            ingediend_door=ingediend_door,
        )
        db.add(aanvraag)
        db.flush()

        # VerlofTeamStatus — één record per aanvraag per team
        db.add(VerlofTeamStatus(
            verlof_id=aanvraag.id,
            team_id=team.id,
            status=v07_status,
            behandeld_door_id=behandeld_door,
            behandeld_op=_parse_datetime(r.get("behandeld_op")),
            reden_weigering=r.get("reden_weigering"),
        ))
        nieuw += 1

    db.flush()
    logger.info("[%s] VerlofAanvragen: %d nieuw, %d overgeslagen.", team_code, nieuw, overgeslagen)
    return nieuw, overgeslagen


def migreer_verlof_saldi(
    db: Session,
    conn: sqlite3.Connection,
    team_code: str,
    gebruiker_id_map: dict[int, int],
) -> tuple[int, int]:
    """
    Importeer verlof saldi per gebruiker per jaar.

    Returns:
        (nieuw, overgeslagen)
    """
    rows = conn.execute("SELECT * FROM verlof_saldo ORDER BY gebruiker_id, jaar").fetchall()
    nieuw = 0
    overgeslagen = 0

    for row in rows:
        r = dict(row)
        v09_uid = gebruiker_id_map.get(r.get("gebruiker_id"))
        if not v09_uid:
            overgeslagen += 1
            continue

        jaar = r.get("jaar")
        if not jaar:
            overgeslagen += 1
            continue

        bestaand = db.query(VerlofSaldo).filter(
            VerlofSaldo.gebruiker_id == v09_uid,
            VerlofSaldo.jaar == jaar,
        ).first()
        if bestaand:
            overgeslagen += 1
            continue

        saldo = VerlofSaldo(
            gebruiker_id=v09_uid,
            jaar=jaar,
            verlof_totaal=r.get("verlof_totaal") or 0,
            verlof_overgedragen=r.get("verlof_overgedragen") or 0,
            kd_totaal=r.get("kd_totaal") or 0,
            kd_overgedragen=r.get("kd_overgedragen") or 0,
            opmerking=r.get("opmerking"),
            overdracht_verwerkt_op=_parse_datetime(r.get("overdracht_verwerkt_op")),
        )
        db.add(saldo)
        nieuw += 1

    db.flush()
    logger.info("[%s] VerlofSaldi: %d nieuw, %d overgeslagen.", team_code, nieuw, overgeslagen)
    return nieuw, overgeslagen


# ------------------------------------------------------------------ #
# Notities                                                            #
# ------------------------------------------------------------------ #

def migreer_notities(
    db: Session,
    conn: sqlite3.Connection,
    team_code: str,
    team: Team,
    locatie: Locatie,
    gebruiker_id_map: dict[int, int],
) -> tuple[int, int]:
    """
    Importeer notities uit één SQLite-database.

    Mapping:
      naar_gebruiker_id > 0   → directe notitie
      naar_gebruiker_id <= 0  → planners-mailbox (naar_rol='planners', scope=team_id)

    Returns:
        (nieuw, overgeslagen)
    """
    rows = conn.execute("SELECT * FROM notities ORDER BY id").fetchall()
    nieuw = 0
    overgeslagen = 0

    for row in rows:
        r = dict(row)
        van_id = gebruiker_id_map.get(r.get("van_gebruiker_id"))
        if not van_id:
            overgeslagen += 1
            continue

        v07_naar_id = r.get("naar_gebruiker_id")
        is_mailbox = v07_naar_id is None or v07_naar_id <= 0
        naar_gebruiker_id = None
        naar_rol = None
        naar_scope_id = None

        if is_mailbox:
            naar_rol = "planners"
            naar_scope_id = team.id
        else:
            v09_naar_id = gebruiker_id_map.get(v07_naar_id)
            if not v09_naar_id:
                overgeslagen += 1
                continue
            naar_gebruiker_id = v09_naar_id

        prioriteit_raw = r.get("prioriteit") or "normaal"
        prioriteit = prioriteit_raw if prioriteit_raw in ("laag", "normaal", "hoog") else "normaal"

        notitie = Notitie(
            uuid=str(uuid.uuid4()),
            locatie_id=locatie.id,
            van_gebruiker_id=van_id,
            naar_gebruiker_id=naar_gebruiker_id,
            naar_rol=naar_rol,
            naar_scope_id=naar_scope_id,
            bericht=r.get("bericht") or "",
            is_gelezen=bool(r.get("is_gelezen", False)),
            prioriteit=prioriteit,
            aangemaakt_op=_parse_datetime(r.get("aangemaakt_op")),
            gelezen_op=_parse_datetime(r.get("gelezen_op")),
        )
        db.add(notitie)
        nieuw += 1

    db.flush()
    logger.info("[%s] Notities: %d nieuw, %d overgeslagen.", team_code, nieuw, overgeslagen)
    return nieuw, overgeslagen


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
            logger.error(
                "Locatie 'LOC1' niet gevonden. "
                "Zorg dat de app minstens één keer opgestart is (seed)."
            )
            sys.exit(1)

        logger.info("Locatie gevonden: %s (id=%d)", locatie.naam, locatie.id)

        # Teams ophalen — aangemaakt door seed
        team_pat = db.query(Team).filter(Team.code == "PAT", Team.locatie_id == locatie.id).first()
        team_to = db.query(Team).filter(Team.code == "TO", Team.locatie_id == locatie.id).first()
        if not team_pat or not team_to:
            logger.error("Teams PAT/TO niet gevonden. Zorg dat de app minstens één keer opgestart is (seed).")
            sys.exit(1)

        logger.info("Teams gevonden: %s (id=%d), %s (id=%d)", team_pat.naam, team_pat.id, team_to.naam, team_to.id)

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

        # ── Gebruikers (gedeelde map om duplicaten te detecteren) ─────
        logger.info("--- Gebruikers PAT ---")
        gedeelde_gebruiker_map: dict[str, int] = {}  # {gebruikersnaam → v0.9 id}
        pat_gebruiker_id_map = migreer_gebruikers(
            db, pat_conn, "PAT", locatie, team_pat, gedeelde_gebruiker_map
        )

        logger.info("--- Gebruikers TO ---")
        to_gebruiker_id_map = migreer_gebruikers(
            db, to_conn, "TO", locatie, team_to, gedeelde_gebruiker_map
        )

        # ── Planning ──────────────────────────────────────────────────
        logger.info("--- Planning PAT ---")
        migreer_planning(db, pat_conn, "PAT", team_pat, pat_gebruiker_id_map)

        logger.info("--- Planning TO ---")
        migreer_planning(db, to_conn, "TO", team_to, to_gebruiker_id_map)

        # ── Verlof ────────────────────────────────────────────────────
        logger.info("--- Verlof PAT ---")
        migreer_verlof_aanvragen(db, pat_conn, "PAT", team_pat, pat_gebruiker_id_map)
        migreer_verlof_saldi(db, pat_conn, "PAT", pat_gebruiker_id_map)

        logger.info("--- Verlof TO ---")
        migreer_verlof_aanvragen(db, to_conn, "TO", team_to, to_gebruiker_id_map)
        migreer_verlof_saldi(db, to_conn, "TO", to_gebruiker_id_map)

        # ── Notities ──────────────────────────────────────────────────
        logger.info("--- Notities PAT ---")
        migreer_notities(db, pat_conn, "PAT", team_pat, locatie, pat_gebruiker_id_map)

        logger.info("--- Notities TO ---")
        migreer_notities(db, to_conn, "TO", team_to, locatie, to_gebruiker_id_map)

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
