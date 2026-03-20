"""
bcrypt_audit.py — Tel resterende bcrypt-hashes in de database.

Gebruik (vanuit container of met actieve .env):
    python backend/scripts/bcrypt_audit.py

Uitvoer:
    - Aantal gebruikers met legacy bcrypt-hash
    - Gebruikersnamen (voor geforceerde wachtwoordreset)
    - Aanbeveling: safe to remove bcrypt dependency als count=0

Plan: uitvoeren ~60 dagen na go-live.
Als count > 0: geforceerde wachtwoordreset sturen naar betrokken accounts.
Zodra count = 0: bcrypt verwijderen uit requirements.txt + legacy-pad uit auth_domein.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessieKlasse
import models  # noqa: F401

from models.gebruiker import Gebruiker

_BCRYPT_PREFIXEN = ("$2b$", "$2a$", "$2y$")


def audit() -> None:
    db = SessieKlasse()
    try:
        gebruikers = db.query(Gebruiker).filter(Gebruiker.is_actief == True).all()  # noqa: E712
        legacy = [g for g in gebruikers if g.gehashed_wachtwoord.startswith(_BCRYPT_PREFIXEN)]

        totaal = len(gebruikers)
        count = len(legacy)

        print(f"Totaal actieve gebruikers : {totaal}")
        print(f"Met legacy bcrypt-hash    : {count}")

        if count == 0:
            print("\n✅  Geen bcrypt-hashes meer aanwezig.")
            print("   Safe to remove: bcrypt uit requirements.txt + legacy-pad uit auth_domein.py")
        else:
            print(f"\n⚠️  {count} gebruiker(s) nog met bcrypt-hash:")
            for g in legacy:
                print(f"   - {g.gebruikersnaam} (id={g.id}, last_login={g.laatste_login})")
            print("\n   Actie: stuur wachtwoordreset-mail naar bovenstaande accounts.")
    finally:
        db.close()


if __name__ == "__main__":
    audit()
