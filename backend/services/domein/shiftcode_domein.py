"""
Domeinlaag: shiftcodes — constanten en normalisatiefuncties.
Geen SQLAlchemy, geen database-toegang.
"""

# ------------------------------------------------------------------ #
# Constanten                                                          #
# ------------------------------------------------------------------ #

SHIFT_TYPES: list[str] = ["vroeg", "laat", "nacht", "dag", "rust"]
DAG_TYPES: list[str] = ["werkdag", "weekend", "feestdag"]


# ------------------------------------------------------------------ #
# Normalisatie                                                        #
# ------------------------------------------------------------------ #

def normaliseer_shiftcode(code: str) -> str:
    """
    Normaliseert een shiftcode: verwijdert witruimte en zet om naar hoofdletters.

    Args:
        code: Ruwe code-invoer.

    Returns:
        Genormaliseerde code (bijv. " d " → "D").
    """
    return code.strip().upper()
