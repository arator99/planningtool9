"""
Typetabel domein — pure business logica voor roostersjablonen.

Een typetabel is een cyclisch weekpatroon (N weken) dat medewerkers doorlopen.
Per medewerker is een startweek gedefinieerd die bepaalt welke week in de cyclus
ze op een gegeven datum volgen.

Geen SQLAlchemy, geen database-toegang.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# Vaste referentiedatum voor consistente weekberekeningen (ISO week 1, 2024)
REFERENTIE_DATUM: date = date(2024, 1, 1)

DAG_NAMEN = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]


# ------------------------------------------------------------------ #
# Validatie                                                           #
# ------------------------------------------------------------------ #

def valideer_typetabel_naam(naam: str) -> None:
    """Valideer naam van een typetabel. Gooit ValueError bij ongeldige invoer."""
    if not naam or not naam.strip():
        raise ValueError("Naam is verplicht.")
    if len(naam.strip()) < 2:
        raise ValueError("Naam moet minimaal 2 karakters bevatten.")
    if len(naam.strip()) > 100:
        raise ValueError("Naam mag maximaal 100 karakters bevatten.")


def valideer_aantal_weken(aantal: int) -> None:
    """Valideer het aantal weken van een typetabel. Gooit ValueError bij ongeldige invoer."""
    if not isinstance(aantal, int):
        raise ValueError("Aantal weken moet een geheel getal zijn.")
    if aantal < 1:
        raise ValueError("Aantal weken moet minimaal 1 zijn.")
    if aantal > 52:
        raise ValueError("Aantal weken mag maximaal 52 zijn.")


# ------------------------------------------------------------------ #
# Dataclasses                                                         #
# ------------------------------------------------------------------ #

@dataclass
class TypetabelRij:
    """Eén rij in het typetabel grid: week × 7 dagen → shift_codes."""
    week_nummer: int                          # 1-based
    shifts: list[Optional[str]] = field(default_factory=lambda: [None] * 7)

    def dag_naam(self, dag: int) -> str:
        """Geef Nederlandse dagnaam voor dag 0–6."""
        return DAG_NAMEN[dag] if 0 <= dag <= 6 else "?"


# ------------------------------------------------------------------ #
# Bereken verwachte shift                                             #
# ------------------------------------------------------------------ #

def bereken_week_in_cyclus(
    datum: date,
    startweek: int,
    aantal_weken: int,
) -> int:
    """
    Bereken welke week in de cyclus een medewerker op een datum volgt.

    Args:
        datum: De datum waarvoor de week bepaald wordt.
        startweek: De startweek van de medewerker (1-based).
        aantal_weken: Totaal aantal weken in de cyclus.

    Returns:
        Week in de cyclus (1-based).
    """
    dagen_sinds_ref = (datum - REFERENTIE_DATUM).days
    weken_sinds_ref = dagen_sinds_ref // 7
    return ((weken_sinds_ref + startweek - 1) % aantal_weken) + 1


def bereken_verwachte_shift(
    datum: date,
    startweek: int,
    grid: dict[tuple[int, int], Optional[str]],
    aantal_weken: int,
) -> Optional[str]:
    """
    Bereken de verwachte shift voor een medewerker op een datum.

    Args:
        datum: De datum.
        startweek: De startweek van de medewerker (1-based, 1 ≤ startweek ≤ aantal_weken).
        grid: Dict[(week_nummer, dag_van_week)] → shift_code, gebouwd uit TypetabelEntry records.
        aantal_weken: Totaal aantal weken in de cyclus.

    Returns:
        Shift code string of None.
    """
    if not startweek or startweek < 1 or startweek > aantal_weken:
        return None
    week = bereken_week_in_cyclus(datum, startweek, aantal_weken)
    dag = datum.weekday()  # 0=ma, 6=zo
    return grid.get((week, dag))
