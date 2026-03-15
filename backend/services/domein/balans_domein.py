"""
Domeinlaag: balans — pure Python berekeningen voor zaterdag/zondag/feestdag compensatie.
Geen SQLAlchemy, geen database-toegang.

Business logica (overgenomen uit v0.7 BalansService):
- Schuld = KALENDERDAGEN: elke za/zo/feestdag in de maand genereert schuld
- CXW = compensatie voor zaterdagen
- RXW = compensatie voor zondagen
- RXF = compensatie voor feestdagen
- Feestdagen op weekend tellen DUBBEL (zowel za/zo als feestdag)
- Status: tekort (<0), ok (=0), teveel (>0)
"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta


# ------------------------------------------------------------------ #
# Constanten                                                          #
# ------------------------------------------------------------------ #

ZATERDAG_COMPENSATIE_CODES: frozenset[str] = frozenset({"CXW"})
ZONDAG_COMPENSATIE_CODES: frozenset[str] = frozenset({"RXW"})
FEESTDAG_COMPENSATIE_CODES: frozenset[str] = frozenset({"RXF"})


# ------------------------------------------------------------------ #
# Dataclasses                                                         #
# ------------------------------------------------------------------ #

@dataclass
class BalansResultaat:
    """Balans voor één medewerker in één maand."""
    gebruiker_id: int
    gebruiker_naam: str
    # Zaterdag → CXW
    zaterdag_schuld: int
    zaterdag_ingepland: int
    zaterdag_balans: int
    zaterdag_status: str   # 'tekort' | 'ok' | 'teveel'
    # Zondag → RXW
    zondag_schuld: int
    zondag_ingepland: int
    zondag_balans: int
    zondag_status: str
    # Feestdag → RXF
    feestdag_schuld: int
    feestdag_ingepland: int
    feestdag_balans: int
    feestdag_status: str


# ------------------------------------------------------------------ #
# Hulpfuncties                                                        #
# ------------------------------------------------------------------ #

def _bereken_pasen(jaar: int) -> date:
    """Bereken Paaszondag via het Meeus/Jones/Butcher algoritme."""
    a = jaar % 19
    b = jaar // 100
    c = jaar % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    maand = (h + l - 7 * m + 114) // 31
    dag = ((h + l - 7 * m + 114) % 31) + 1
    return date(jaar, maand, dag)


def belgische_feestdagen(jaar: int) -> frozenset[date]:
    """Retourneer de Belgische wettelijke feestdagen als frozenset van date-objecten."""
    pasen = _bereken_pasen(jaar)
    return frozenset({
        date(jaar, 1, 1),                    # Nieuwjaar
        pasen + timedelta(days=1),            # Paasmaandag
        date(jaar, 5, 1),                    # Dag van de Arbeid
        pasen + timedelta(days=39),           # Hemelvaartsdag
        pasen + timedelta(days=50),           # Pinkstermaandag
        date(jaar, 7, 21),                   # Nationale feestdag
        date(jaar, 8, 15),                   # OLV Hemelvaart
        date(jaar, 11, 1),                   # Allerheiligen
        date(jaar, 11, 11),                  # Wapenstilstand
        date(jaar, 12, 25),                  # Kerstmis
    })


def bereken_maand_schuld(jaar: int, maand: int) -> tuple[int, int, int]:
    """
    Bereken het aantal zaterdagen, zondagen en feestdagen in een maand.

    Feestdagen op za/zo tellen DUBBEL (zowel za/zo als feestdag).

    Returns:
        (zaterdag_schuld, zondag_schuld, feestdag_schuld)
    """
    _, aantal_dagen = monthrange(jaar, maand)
    feestdagen = belgische_feestdagen(jaar)

    zat = 0
    zon = 0
    feest = 0

    for dag in range(1, aantal_dagen + 1):
        d = date(jaar, maand, dag)
        weekdag = d.weekday()
        if weekdag == 5:
            zat += 1
        elif weekdag == 6:
            zon += 1
        if d in feestdagen:
            feest += 1

    return zat, zon, feest


def tel_compensatie_codes(shift_codes: list[str | None]) -> tuple[int, int, int]:
    """
    Tel CXW, RXW en RXF codes in een lijst van shift_codes.

    Returns:
        (cxw_count, rxw_count, rxf_count)
    """
    cxw = rxw = rxf = 0
    for code in shift_codes:
        if not code:
            continue
        upper = code.strip().upper()
        if upper in ZATERDAG_COMPENSATIE_CODES:
            cxw += 1
        elif upper in ZONDAG_COMPENSATIE_CODES:
            rxw += 1
        elif upper in FEESTDAG_COMPENSATIE_CODES:
            rxf += 1
    return cxw, rxw, rxf


def bepaal_status(balans: int) -> str:
    """Retourneer 'tekort', 'ok' of 'teveel' op basis van de balanswaarde."""
    if balans < 0:
        return "tekort"
    if balans > 0:
        return "teveel"
    return "ok"


def bouw_balans_resultaat(
    gebruiker_id: int,
    gebruiker_naam: str,
    zaterdag_schuld: int,
    zondag_schuld: int,
    feestdag_schuld: int,
    shift_codes: list[str | None],
) -> BalansResultaat:
    """Bouw een BalansResultaat op basis van schuld en geplande shift codes."""
    cxw, rxw, rxf = tel_compensatie_codes(shift_codes)

    zat_balans = cxw - zaterdag_schuld
    zon_balans = rxw - zondag_schuld
    feest_balans = rxf - feestdag_schuld

    return BalansResultaat(
        gebruiker_id=gebruiker_id,
        gebruiker_naam=gebruiker_naam,
        zaterdag_schuld=zaterdag_schuld,
        zaterdag_ingepland=cxw,
        zaterdag_balans=zat_balans,
        zaterdag_status=bepaal_status(zat_balans),
        zondag_schuld=zondag_schuld,
        zondag_ingepland=rxw,
        zondag_balans=zon_balans,
        zondag_status=bepaal_status(zon_balans),
        feestdag_schuld=feestdag_schuld,
        feestdag_ingepland=rxf,
        feestdag_balans=feest_balans,
        feestdag_status=bepaal_status(feest_balans),
    )
