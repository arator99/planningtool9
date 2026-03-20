"""
maak_super_beheerder.py — Promoveer een gebruiker tot super_beheerder.

Gebruik (vanuit de container):
    docker compose exec app python scripts/maak_super_beheerder.py --gebruikersnaam admin

Wat dit script doet:
    1. Maakt de systeemlocatie NAT aan als die nog niet bestaat
    2. Geeft de opgegeven gebruiker de rol super_beheerder (scope = NAT-locatie)
    3. Past Gebruiker.rol bij naar 'super_beheerder'

Na uitvoering heeft de gebruiker toegang tot /beheer/locaties en /beheer/hr-nationaal.
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessieKlasse, motor, Basis
import models  # noqa: F401

from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol
from models.locatie import Locatie


def _haal_of_maak_nat_locatie(db) -> Locatie:
    """Haal de NAT-systeemlocatie op, of maak ze aan."""
    nat = db.query(Locatie).filter(Locatie.code == "NAT").first()
    if not nat:
        nat = Locatie(
            uuid=str(uuid.uuid4()),
            naam="Nationaal",
            code="NAT",
            area_label=None,
            is_actief=True,
        )
        db.add(nat)
        db.flush()
        print(f"  Systeemlocatie NAT aangemaakt (id={nat.id})")
    else:
        print(f"  Systeemlocatie NAT gevonden (id={nat.id})")
    return nat


def promoveer(gebruikersnaam: str) -> None:
    Basis.metadata.create_all(bind=motor)
    db = SessieKlasse()
    try:
        gebruiker = db.query(Gebruiker).filter(
            Gebruiker.gebruikersnaam == gebruikersnaam
        ).first()
        if not gebruiker:
            print(f"❌  Gebruiker '{gebruikersnaam}' niet gevonden.")
            sys.exit(1)

        print(f"Gebruiker gevonden: {gebruiker.volledige_naam} (id={gebruiker.id}, huidige rol={gebruiker.rol})")

        nat = _haal_of_maak_nat_locatie(db)

        # Controleer of super_beheerder rol al bestaat
        bestaand = db.query(GebruikerRol).filter(
            GebruikerRol.gebruiker_id == gebruiker.id,
            GebruikerRol.rol == "super_beheerder",
            GebruikerRol.scope_id == nat.id,
        ).first()

        if bestaand:
            print(f"  Rol super_beheerder al aanwezig — geen wijziging nodig.")
        else:
            db.add(GebruikerRol(
                gebruiker_id=gebruiker.id,
                rol="super_beheerder",
                scope_id=nat.id,
                is_reserve=False,
                is_actief=True,
            ))
            print(f"  GebruikerRol super_beheerder aangemaakt (scope=NAT id={nat.id})")

        # Denormaliseer rol op Gebruiker record
        gebruiker.rol = "super_beheerder"

        db.commit()
        print(f"✅  {gebruikersnaam} is nu super_beheerder.")
        print(f"   Toegang tot: /beheer/locaties, /beheer/hr-nationaal")
    except Exception as fout:
        db.rollback()
        print(f"❌  Fout: {fout}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promoveer een gebruiker tot super_beheerder.")
    parser.add_argument("--gebruikersnaam", required=True, help="Gebruikersnaam van de te promoveren gebruiker")
    args = parser.parse_args()
    promoveer(args.gebruikersnaam)
