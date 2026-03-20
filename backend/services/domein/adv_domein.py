"""
ADV domein — pure business logica voor arbeidsduurverkorting.

Twee ADV types:
- 'dag_per_week': Elke week dezelfde dag (ma–vr).
- 'week_per_5_weken': Elke 5 weken een volledige werkweek (ma–vr).

De individuele ADV-dagen worden runtime berekend — ze worden NIET opgeslagen.
Geen SQLAlchemy, geen database-toegang.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

ADV_TYPES = ("dag_per_week", "week_per_5_weken")
DAG_NAMEN = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag"]
ADV_TYPE_LABELS = {
    "dag_per_week": "Dag per week",
    "week_per_5_weken": "Week per 5 weken",
}


# ------------------------------------------------------------------ #
# Validatie                                                           #
# ------------------------------------------------------------------ #

def valideer_adv_toekenning(
    adv_type: str,
    dag_van_week: Optional[int],
    start_datum: date,
    eind_datum: Optional[date],
) -> None:
    """
    Valideer ADV-toekenning invoer. Gooit ValueError bij ongeldige invoer.

    Args:
        adv_type: 'dag_per_week' of 'week_per_5_weken'.
        dag_van_week: 0–4 (ma–vr); verplicht bij dag_per_week.
        start_datum: Startdatum.
        eind_datum: Optionele einddatum.
    """
    if adv_type not in ADV_TYPES:
        raise ValueError(f"Ongeldig ADV-type. Kies uit: {', '.join(ADV_TYPES)}.")
    if adv_type == "dag_per_week":
        if dag_van_week is None:
            raise ValueError("Kies een dag voor 'Dag per week'.")
        if not 0 <= dag_van_week <= 4:
            raise ValueError("Dag moet tussen maandag (0) en vrijdag (4) liggen.")
    if eind_datum and eind_datum < start_datum:
        raise ValueError("Einddatum mag niet voor de startdatum liggen.")


# ------------------------------------------------------------------ #
# Genereer ADV-dagen                                                  #
# ------------------------------------------------------------------ #

def genereer_adv_dagen(
    adv_type: str,
    dag_van_week: Optional[int],
    start_datum: date,
    eind_datum: Optional[date],
    jaar: int,
    maand: int,
) -> list[date]:
    """
    Genereer alle ADV-dagen voor een toekenning in een specifieke maand.

    Args:
        adv_type: 'dag_per_week' of 'week_per_5_weken'.
        dag_van_week: 0–4 (alleen bij dag_per_week).
        start_datum: Startdatum van de toekenning.
        eind_datum: Einddatum (of None voor onbeperkt).
        jaar: Het jaar.
        maand: De maand (1–12).

    Returns:
        Lijst van ADV-datums in de opgegeven maand.
    """
    if adv_type == "dag_per_week":
        return _genereer_dag_per_week(dag_van_week, start_datum, eind_datum, jaar, maand)
    if adv_type == "week_per_5_weken":
        return _genereer_week_per_5_weken(start_datum, eind_datum, jaar, maand)
    return []


def _genereer_dag_per_week(
    dag_van_week: Optional[int],
    start_datum: date,
    eind_datum: Optional[date],
    jaar: int,
    maand: int,
) -> list[date]:
    if dag_van_week is None:
        return []
    dagen: list[date] = []
    for dag_nr in range(1, 32):
        try:
            datum = date(jaar, maand, dag_nr)
        except ValueError:
            break
        if datum < start_datum:
            continue
        if eind_datum and datum > eind_datum:
            continue
        if datum.weekday() == dag_van_week:
            dagen.append(datum)
    return dagen


def _genereer_week_per_5_weken(
    start_datum: date,
    eind_datum: Optional[date],
    jaar: int,
    maand: int,
) -> list[date]:
    if maand == 12:
        eerste_volgende = date(jaar + 1, 1, 1)
    else:
        eerste_volgende = date(jaar, maand + 1, 1)
    laatste_dag_maand = eerste_volgende - timedelta(days=1)
    eerste_dag_maand = date(jaar, maand, 1)

    # Maandag van de startweek
    start_week_maandag = start_datum - timedelta(days=start_datum.weekday())

    # Ga terug tot vóór of op de eerste dag van de maand
    huidige = start_week_maandag
    while huidige > eerste_dag_maand:
        huidige -= timedelta(weeks=5)

    dagen: list[date] = []
    while huidige <= laatste_dag_maand:
        for i in range(5):  # ma–vr
            dag = huidige + timedelta(days=i)
            if dag.year != jaar or dag.month != maand:
                continue
            if dag < start_datum:
                continue
            if eind_datum and dag > eind_datum:
                continue
            dagen.append(dag)
        huidige += timedelta(weeks=5)
    return dagen


# ------------------------------------------------------------------ #
# Lookup helper                                                       #
# ------------------------------------------------------------------ #

@dataclass
class AdvInfo:
    """Compact AdvInfo voor gebruik in planning grid en exports."""
    adv_type: str
    dag_van_week: Optional[int]

    @property
    def type_label(self) -> str:
        return ADV_TYPE_LABELS.get(self.adv_type, self.adv_type)

    @property
    def dag_label(self) -> str:
        if self.adv_type == "dag_per_week" and self.dag_van_week is not None:
            return DAG_NAMEN[self.dag_van_week]
        return "-"


def maak_adv_lookup(
    toekenningen: list,   # lijst van AdvToekenning SQLAlchemy objecten
    jaar: int,
    maand: int,
) -> dict[tuple[int, str], AdvInfo]:
    """
    Maak een O(1)-lookup dict voor ADV-dagen: (gebruiker_id, datum_iso) → AdvInfo.

    Args:
        toekenningen: Lijst van actieve AdvToekenning ORM-objecten.
        jaar: Het jaar.
        maand: De maand (1–12).

    Returns:
        Dict[(gebruiker_id, 'YYYY-MM-DD')] → AdvInfo.
    """
    lookup: dict[tuple[int, str], AdvInfo] = {}
    for t in toekenningen:
        dagen = genereer_adv_dagen(
            adv_type=t.adv_type,
            dag_van_week=t.dag_van_week,
            start_datum=t.start_datum,
            eind_datum=t.eind_datum,
            jaar=jaar,
            maand=maand,
        )
        info = AdvInfo(adv_type=t.adv_type, dag_van_week=t.dag_van_week)
        for dag in dagen:
            key = (t.gebruiker_id, dag.isoformat())
            if key not in lookup:
                lookup[key] = info
    return lookup
