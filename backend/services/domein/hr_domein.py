"""
Domeinlaag: HR regels — constanten en validatiefuncties.
Geen SQLAlchemy, geen database-toegang.
"""

# ------------------------------------------------------------------ #
# Constanten                                                          #
# ------------------------------------------------------------------ #

ERNST_NIVEAUS: frozenset[str] = frozenset({"INFO", "WARNING", "CRITICAL"})
RICHTINGEN: frozenset[str] = frozenset({"max", "min"})


# ------------------------------------------------------------------ #
# Validatiefuncties                                                   #
# ------------------------------------------------------------------ #

def valideer_ernst_niveau(ernst: str) -> None:
    """Controleert of een ernst-niveau geldig is."""
    if ernst not in ERNST_NIVEAUS:
        raise ValueError(f"Ongeldig ernst niveau: {ernst}")


def valideer_richting(richting: str) -> None:
    """Controleert of een richting geldig is ('max' of 'min')."""
    if richting not in RICHTINGEN:
        raise ValueError(f"Ongeldige richting: {richting}. Kies 'max' of 'min'.")


def valideer_override_waarde(richting: str, nationale_waarde: int, override_waarde: int) -> None:
    """
    Controleert of een lokale override strenger is dan de nationale waarde.

    richting="max": override moet <= nationaal (lagere max = strenger).
    richting="min": override moet >= nationaal (hogere min = strenger).

    Raises:
        ValueError: Als de override niet strenger is dan de nationale waarde.
    """
    if richting == "max" and override_waarde > nationale_waarde:
        raise ValueError(
            f"Override waarde {override_waarde} is soepeler dan de nationale waarde {nationale_waarde}. "
            f"Bij richting 'max' moet de override ≤ {nationale_waarde} zijn."
        )
    if richting == "min" and override_waarde < nationale_waarde:
        raise ValueError(
            f"Override waarde {override_waarde} is soepeler dan de nationale waarde {nationale_waarde}. "
            f"Bij richting 'min' moet de override ≥ {nationale_waarde} zijn."
        )


def valideer_interval_dagen(interval: int) -> None:
    """Controleert of het interval voor de rode-lijn cyclus geldig is."""
    if interval < 1:
        raise ValueError("Interval moet minimaal 1 dag zijn.")
