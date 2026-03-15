"""
Domeinlaag: verlof — constanten en pure validatiefuncties.
Geen SQLAlchemy, geen database-toegang.
"""
from datetime import date

# ------------------------------------------------------------------ #
# Constanten                                                          #
# ------------------------------------------------------------------ #

BEHANDELAAR_ROLLEN: frozenset[str] = frozenset({"beheerder", "planner", "hr"})


# ------------------------------------------------------------------ #
# Validatiefuncties                                                   #
# ------------------------------------------------------------------ #

def valideer_verlof_periode(start_datum: date, eind_datum: date) -> None:
    """
    Controleert of de verlofperiode geldig is.

    Raises:
        ValueError: Als einddatum vóór startdatum ligt.
    """
    if eind_datum < start_datum:
        raise ValueError("Einddatum mag niet voor startdatum liggen.")


def bereken_verlof_dagen(start_datum: date, eind_datum: date) -> int:
    """
    Bereken het aantal verlofkalenderdagen (inclusief start- en einddatum).

    Args:
        start_datum: Eerste dag van het verlof.
        eind_datum: Laatste dag van het verlof.

    Returns:
        Aantal dagen als int (minimaal 1).
    """
    return (eind_datum - start_datum).days + 1
