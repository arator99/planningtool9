"""
Domeinlaag: HR regels — constanten en validatiefuncties.
Geen SQLAlchemy, geen database-toegang.
"""

# ------------------------------------------------------------------ #
# Constanten                                                          #
# ------------------------------------------------------------------ #

ERNST_NIVEAUS: frozenset[str] = frozenset({"INFO", "WARNING", "CRITICAL"})


# ------------------------------------------------------------------ #
# Validatiefuncties                                                   #
# ------------------------------------------------------------------ #

def valideer_ernst_niveau(ernst: str) -> None:
    """
    Controleert of een ernst-niveau geldig is.

    Raises:
        ValueError: Als het niveau niet in ERNST_NIVEAUS staat.
    """
    if ernst not in ERNST_NIVEAUS:
        raise ValueError(f"Ongeldig ernst niveau: {ernst}")


def valideer_interval_dagen(interval: int) -> None:
    """
    Controleert of het interval voor de rode-lijn cyclus geldig is.

    Raises:
        ValueError: Als het interval kleiner dan 1 is.
    """
    if interval < 1:
        raise ValueError("Interval moet minimaal 1 dag zijn.")
