"""Seed testdata — wordt aangeroepen bij startup als de database leeg is."""
import logging
import os
import secrets
import string

from database import SessieKlasse

logger = logging.getLogger(__name__)


def seed_test_data() -> None:
    """Maakt een testlocatie + team + beheerder aan als de database leeg is."""
    from config import instellingen
    if instellingen.omgeving == "production":
        logger.info("Seeden overgeslagen (productie-omgeving).")
        return

    from models.locatie import Locatie
    from models.team import Team
    from models.gebruiker import Gebruiker
    from models.gebruiker_rol import GebruikerRol
    from models.hr import NationaleHRRegel
    from models.planning import Shiftcode
    from services.domein.auth_domein import hash_wachtwoord

    db = SessieKlasse()
    try:
        if db.query(Gebruiker).count() > 0:
            return  # Al geseed

        # Locatie aanmaken
        locatie = Locatie(naam="Locatie 1", code="LOC1", area_label="Gebied A", is_actief=True)
        db.add(locatie)
        db.flush()

        # Teams aanmaken
        team_pat = Team(naam="PAT", code="PAT", locatie_id=locatie.id, is_actief=True)
        team_to = Team(naam="TO", code="TO", locatie_id=locatie.id, is_actief=True)
        db.add(team_pat)
        db.add(team_to)
        db.flush()

        # Seed-wachtwoord ophalen uit omgevingsvariabele
        seed_wachtwoord = os.environ.get("SEED_ADMIN_WACHTWOORD")
        if not seed_wachtwoord:
            alfabet = string.ascii_letters + string.digits + "!@#$%"
            seed_wachtwoord = "".join(secrets.choice(alfabet) for _ in range(16))
            logger.warning("SEED_ADMIN_WACHTWOORD niet ingesteld — tijdelijk wachtwoord gegenereerd: %s", seed_wachtwoord)

        # Beheerder aanmaken
        admin = Gebruiker(
            gebruikersnaam="admin",
            gehashed_wachtwoord=hash_wachtwoord(seed_wachtwoord),
            volledige_naam="Beheerder",
            locatie_id=locatie.id,
            rol="beheerder",
            is_actief=True,
            totp_actief=False,
            taal="nl",
        )
        db.add(admin)
        db.flush()

        # GebruikerRol voor admin (beheerder → scope = locatie)
        db.add(GebruikerRol(
            gebruiker_id=admin.id,
            rol="beheerder",
            scope_id=locatie.id,
            is_reserve=False,
            is_actief=True,
        ))

        # Nationale HR-regels seeden
        nationale_regels = [
            NationaleHRRegel(code="MAX_DAGEN_OP_RIJ",       naam="Max dagen op rij",              waarde=7,  eenheid="dagen", ernst_niveau="CRITICAL", richting="max", beschrijving="Max aaneengesloten werkdagen zonder rustdag."),
            NationaleHRRegel(code="MIN_RUSTTIJD",            naam="Minimale rusttijd",              waarde=11, eenheid="uren",  ernst_niveau="CRITICAL", richting="min", beschrijving="Min uren rust tussen twee shifts."),
            NationaleHRRegel(code="MAX_UREN_PER_WEEK",      naam="Max uren per week",              waarde=50, eenheid="uren",  ernst_niveau="WARNING",  richting="max", beschrijving="Max gewerkte uren in één kalenderweek."),
            NationaleHRRegel(code="RX_MAX_GAP",              naam="Max dagen tussen rustdagen",     waarde=7,  eenheid="dagen", ernst_niveau="WARNING",  richting="max", beschrijving="Max dagen tussen twee RX-rustdagen."),
            NationaleHRRegel(code="RODE_LIJN_BLOK_GROOTTE", naam="Rode lijn blokgrootte",          waarde=1,  eenheid="blok",  ernst_niveau="INFO",     richting="max", beschrijving="Aantal aaneengesloten 28-daagse periodes per blok."),
        ]
        for regel in nationale_regels:
            db.add(regel)

        # Test shiftcodes aanmaken (nationaal beschikbaar: locatie_id=None)
        test_codes = [
            Shiftcode(locatie_id=None, code="D",   start_uur="08:00", eind_uur="16:00", shift_type="vroeg", telt_als_werkdag=True,  is_nachtprestatie=False, reset_nacht=True),
            Shiftcode(locatie_id=None, code="DL",  start_uur="10:00", eind_uur="18:00", shift_type="laat",  telt_als_werkdag=True,  is_nachtprestatie=False, reset_nacht=True),
            Shiftcode(locatie_id=None, code="N",   start_uur="22:00", eind_uur="06:00", shift_type="nacht", telt_als_werkdag=True,  is_nachtprestatie=True,  reset_nacht=False),
            Shiftcode(locatie_id=None, code="VV",  start_uur=None,    eind_uur=None,    shift_type=None,    telt_als_werkdag=True,  is_nachtprestatie=False, reset_nacht=True,  beschrijving="Verlof"),
            Shiftcode(locatie_id=None, code="RXW", start_uur=None,    eind_uur=None,    shift_type=None,    telt_als_werkdag=False, is_nachtprestatie=False, reset_nacht=False, beschrijving="Rustdag weekend"),
        ]
        for code in test_codes:
            db.add(code)

        db.commit()

        logger.info("=" * 60)
        logger.info("TESTDATA AANGEMAAKT:")
        logger.info("  Locatie        : Locatie 1 (LOC1)")
        logger.info("  Teams          : PAT, TO")
        logger.info("  Gebruikersnaam : admin")
        logger.info("  Rol            : beheerder")
        logger.info("  Nationale HR   : 5 regels geseed")
        logger.info("=" * 60)
    except Exception as fout:
        logger.error("Fout bij seeden testdata: %s", fout, exc_info=True)
        db.rollback()
    finally:
        db.close()
