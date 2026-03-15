"""
Domeinlaag: gebruikers — pure validatiefuncties.
Geen SQLAlchemy, geen database-toegang.
"""
import re

# ------------------------------------------------------------------ #
# Reguliere expressies                                                #
# ------------------------------------------------------------------ #

GEBRUIKERSNAAM_PATROON = re.compile(r'^[a-zA-Z0-9_]+$')


# ------------------------------------------------------------------ #
# Validatiefuncties                                                   #
# ------------------------------------------------------------------ #

def valideer_gebruikersnaam_formaat(gebruikersnaam: str) -> None:
    """
    Controleert of een gebruikersnaam geldig is qua formaat.

    Raises:
        ValueError: Als de gebruikersnaam te kort is of ongeldige tekens bevat.
    """
    if len(gebruikersnaam) < 3:
        raise ValueError("Gebruikersnaam moet minstens 3 tekens bevatten")
    if not GEBRUIKERSNAAM_PATROON.match(gebruikersnaam):
        raise ValueError("Gebruikersnaam mag alleen letters, cijfers en _ bevatten")
