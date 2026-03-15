"""
Domeinlaag: rapporten — pure functies voor CSV-generatie en datagroepering.
Geen SQLAlchemy, geen database-toegang.
"""
import csv
import io
from typing import Any


def bouw_csv_inhoud(dag_info: list[dict[str, Any]], grid: list[dict[str, Any]]) -> str:
    """
    Genereer een CSV-string van een maandplanningsgrid.

    Args:
        dag_info: Lijst van dicts met 'dag_naam' en 'dag' per kolom.
        grid: Lijst van dicts met 'naam' en 'shifts' (list[str]) per medewerker.

    Returns:
        CSV-string met puntkomma als scheidingsteken (UTF-8 compatible).
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    header = ["Medewerker"] + [f"{d['dag_naam']} {d['dag']}" for d in dag_info]
    writer.writerow(header)

    for rij in grid:
        writer.writerow([rij["naam"]] + rij["shifts"])

    return output.getvalue()


def groepeer_verlof_per_medewerker(aanvragen: list[Any]) -> list[dict[str, Any]]:
    """
    Groepeer goedgekeurde verlofaanvragen per medewerker.

    Args:
        aanvragen: Lijst van aanvraagobjecten met attributen:
                   gebruiker_id, gebruiker.volledige_naam,
                   gebruiker.gebruikersnaam, aantal_dagen.

    Returns:
        Gesorteerde lijst van dicts per medewerker met 'naam',
        'aanvragen' en 'totaal_dagen'.
    """
    gegroepeerd: dict[int, dict[str, Any]] = {}
    for aanvraag in aanvragen:
        uid = aanvraag.gebruiker_id
        if uid not in gegroepeerd:
            naam = aanvraag.gebruiker.volledige_naam or aanvraag.gebruiker.gebruikersnaam
            gegroepeerd[uid] = {"naam": naam, "aanvragen": [], "totaal_dagen": 0}
        gegroepeerd[uid]["aanvragen"].append(aanvraag)
        gegroepeerd[uid]["totaal_dagen"] += aanvraag.aantal_dagen

    return sorted(gegroepeerd.values(), key=lambda x: x["naam"])
