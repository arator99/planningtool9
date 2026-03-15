"""
Domeinlaag: notities — constanten en validatiefuncties.
Geen SQLAlchemy, geen database-toegang.
"""

# ------------------------------------------------------------------ #
# Constanten                                                          #
# ------------------------------------------------------------------ #

PRIORITEITEN: frozenset[str] = frozenset({"normaal", "hoog", "urgent"})


# ------------------------------------------------------------------ #
# Validatiefuncties                                                   #
# ------------------------------------------------------------------ #

def valideer_bericht(bericht: str) -> None:
    """
    Controleert of een berichttekst niet leeg is.

    Raises:
        ValueError: Als het bericht leeg of alleen witruimte bevat.
    """
    if not bericht or not bericht.strip():
        raise ValueError("Bericht mag niet leeg zijn.")


def valideer_prioriteit(prioriteit: str) -> None:
    """
    Controleert of de prioriteit een geldige waarde heeft.

    Raises:
        ValueError: Als de prioriteit niet in PRIORITEITEN staat.
    """
    if prioriteit not in PRIORITEITEN:
        raise ValueError("Ongeldige prioriteit.")
