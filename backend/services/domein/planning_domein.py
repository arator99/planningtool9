"""
Domeinlaag: planning — pure Python constanten en hulpfuncties.
Geen SQLAlchemy, geen database-toegang.
"""
from datetime import date
from typing import Any

# ------------------------------------------------------------------ #
# Constanten                                                          #
# ------------------------------------------------------------------ #

SHIFT_TYPE_VOLGORDE: list[str | None] = ["vroeg", "laat", "nacht", "dag", "rust", None]

DAG_TYPE_VOLGORDE: list[str | None] = ["werkdag", "zaterdag", "zondag", None]
DAG_TYPE_LABELS: dict[str | None, str] = {
    "werkdag": "Weekdag",
    "zaterdag": "Zaterdag",
    "zondag": "Zondag",
    None: "Alle dagen",
}

SHIFT_TYPE_CONFIG: dict[str | None, dict[str, str]] = {
    "vroeg": {"naam": "Vroege Dienst", "var_bg": "var(--grid-vroeg)",   "var_tekst": "var(--grid-vroeg-tekst)"},
    "laat":  {"naam": "Late Dienst",   "var_bg": "var(--grid-laat)",    "var_tekst": "var(--grid-laat-tekst)"},
    "nacht": {"naam": "Nachtdienst",   "var_bg": "var(--grid-nacht)",   "var_tekst": "var(--grid-nacht-tekst)"},
    "dag":   {"naam": "Dagdienst",     "var_bg": "var(--grid-dag)",     "var_tekst": "var(--grid-dag-tekst)"},
    "rust":  {"naam": "Rust / Verlof", "var_bg": "var(--grid-rust)",    "var_tekst": "var(--grid-rust-tekst)"},
    None:    {"naam": "Overig",        "var_bg": "var(--grid-standby)", "var_tekst": "var(--grid-standby-tekst)"},
}

# Celkleuren (hex) per shift_type — gelijk aan v0.7 kleurenschema
CEL_KLEUREN: dict[str | None, str] = {
    "early": "#E3F2FD",   # lichtblauw   — vroege dienst
    "late":  "#FFF3E0",   # lichtoranje  — late dienst
    "night": "#F3E5F5",   # lichtpaars   — nachtdienst
    "day":   "#FFFFFF",   # wit          — dagdienst
    "rest":  "#E8F5E9",   # lichtgroen   — rust/verlof/compensatie
    None:    "#FAFAFA",   # lichtgrijs   — standby/onbekend
}

# Speciale codes die altijd als rust/verlof kleuren, ongeacht shift_type
RUST_CODES: frozenset[str] = frozenset({
    "RX", "R", "RUST", "CX", "CXW", "RXW", "RXF", "V", "VV", "VP", "KD", "ADV", "Z", "DA",
})

STANDBY_CODES: frozenset[str] = frozenset({"T", "WACHT", "STANDBY", "W"})

MAAND_NAMEN: dict[int, str] = {
    1: "januari", 2: "februari", 3: "maart", 4: "april",
    5: "mei", 6: "juni", 7: "juli", 8: "augustus",
    9: "september", 10: "oktober", 11: "november", 12: "december",
}

DAG_NAMEN: list[str] = ["ma", "di", "wo", "do", "vr", "za", "zo"]


# ------------------------------------------------------------------ #
# Hulpfuncties                                                        #
# ------------------------------------------------------------------ #

def bouw_dag_info(datums: list[date]) -> list[dict[str, Any]]:
    """
    Bouw een lijst met metadata per dag (datum, dagnummer, dagnaam, weekend).

    Args:
        datums: Lijst van date-objecten voor de maand.

    Returns:
        Lijst van dicts met 'datum', 'dag', 'dag_naam', 'is_weekend'.
    """
    vandaag = date.today()
    return [
        {
            "datum": d.isoformat(),
            "dag": d.day,
            "dag_naam": DAG_NAMEN[d.weekday()],
            "weekdag": d.weekday(),
            "is_weekend": d.weekday() >= 5,
            "is_vandaag": d == vandaag,
        }
        for d in datums
    ]


def bereken_navigatie(jaar: int, maand: int) -> tuple[dict[str, int], dict[str, int]]:
    """
    Bereken vorige en volgende maand voor navigatielinks.

    Args:
        jaar: Het huidige jaar.
        maand: De huidige maand (1–12).

    Returns:
        Tuple van (vorige, volgende) als dicts met 'jaar' en 'maand'.
    """
    if maand == 1:
        vorige = {"jaar": jaar - 1, "maand": 12}
    else:
        vorige = {"jaar": jaar, "maand": maand - 1}

    if maand == 12:
        volgende = {"jaar": jaar + 1, "maand": 1}
    else:
        volgende = {"jaar": jaar, "maand": maand + 1}

    return vorige, volgende


def groepeer_shiftcodes(codes: list[Any]) -> list[dict[str, Any]]:
    """
    Groepeer shiftcodes per shift_type, met sub-groepen per dag_type.

    Args:
        codes: Lijst van Shiftcode ORM-objecten met 'shift_type' en 'dag_type'.

    Returns:
        Lijst van dicts met 'naam', 'var_bg', 'var_tekst', 'sub_groepen'.
        Elke sub_groep: {'dag_label', 'dag_type', 'codes'}.
    """
    gegroepeerd: dict[str | None, list] = {}
    for sc in codes:
        key = sc.shift_type if sc.shift_type in SHIFT_TYPE_CONFIG else None
        gegroepeerd.setdefault(key, []).append(sc)

    resultaat = []
    for shift_type in SHIFT_TYPE_VOLGORDE:
        if shift_type not in gegroepeerd:
            continue
        cfg = SHIFT_TYPE_CONFIG[shift_type]

        # Sub-groepeer per dag_type binnen dit shift-type
        dag_gegroepeerd: dict[str | None, list] = {}
        for sc in gegroepeerd[shift_type]:
            dag_key = sc.dag_type if sc.dag_type in DAG_TYPE_LABELS else None
            dag_gegroepeerd.setdefault(dag_key, []).append(sc)

        sub_groepen = [
            {
                "dag_label": DAG_TYPE_LABELS[dag_type],
                "dag_type": dag_type,
                "codes": dag_gegroepeerd[dag_type],
            }
            for dag_type in DAG_TYPE_VOLGORDE
            if dag_type in dag_gegroepeerd
        ]

        resultaat.append({
            "naam": cfg["naam"],
            "var_bg": cfg["var_bg"],
            "var_tekst": cfg["var_tekst"],
            "sub_groepen": sub_groepen,
        })
    return resultaat
