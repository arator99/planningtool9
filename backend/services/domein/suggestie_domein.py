"""
Domeinlaag: suggestie — pure Python scoring voor shift-suggesties.
Geen SQLAlchemy, geen database-toegang.

Scoring per shiftcode voor een gebruiker/datum:
  BASIS (50)
+ historiek bonus  (max +25 — hoe vaak deed de gebruiker dit code de afgelopen 90 dagen)
+ voorkeur bonus   (max +15 — op basis van Gebruiker.shift_voorkeuren JSON)
---
= score (geclampt 0–100)
"""
import json
from dataclasses import dataclass, field

BASIS_SCORE: float = 50.0
HISTORIEK_MAX_BONUS: float = 25.0
VOORKEUR_BONUS: float = 15.0
MAX_SCORE: float = 100.0

HISTORIEK_LOOKBACK_DAGEN: int = 90
HISTORIEK_REFERENTIE_AANTAL: int = 10   # Aantal keer = volle historiek-bonus

SHIFT_TYPES_VOORKEUR: frozenset[str] = frozenset({"vroeg", "laat", "nacht"})


# ------------------------------------------------------------------ #
# Dataclasses                                                         #
# ------------------------------------------------------------------ #

@dataclass
class ShiftcodeSuggestie:
    """Gescoorde shiftcode-suggestie voor één gebruiker op één datum."""
    shiftcode: str
    score: float           # 0.0 – 100.0
    redenen: list[str] = field(default_factory=list)
    is_valide: bool = True  # False als er CRITICAL HR-overtredingen zijn (toekomst)


# ------------------------------------------------------------------ #
# Hulpfuncties                                                        #
# ------------------------------------------------------------------ #

def parseer_shift_voorkeuren(json_str: str | None) -> dict[str, int]:
    """
    Parseer `Gebruiker.shift_voorkeuren` JSON.

    Verwacht formaat: `{"vroeg": 1, "laat": 2, "nacht": 3}`
    Rang 1 = hoogste voorkeur, 3 = laagste.

    Returns:
        Dict {shift_type: rang} — leeg dict als niet parseerbaar.
    """
    if not json_str:
        return {}
    try:
        data = json.loads(json_str)
        if isinstance(data, dict):
            return {k: int(v) for k, v in data.items() if k in SHIFT_TYPES_VOORKEUR}
    except (ValueError, TypeError):
        pass
    return {}


def bereken_historiek_bonus(
    shiftcode: str,
    historiek: list[str | None],
) -> tuple[float, str | None]:
    """
    Bereken bonus op basis van hoe vaak de gebruiker deze code recentelijk gebruikte.

    Returns:
        (bonus, reden_string | None)
    """
    if not historiek:
        return 0.0, None

    code_upper = shiftcode.upper()
    count = sum(1 for c in historiek if c and c.upper() == code_upper)

    if count == 0:
        return 0.0, None

    ratio = min(count / HISTORIEK_REFERENTIE_AANTAL, 1.0)
    bonus = ratio * HISTORIEK_MAX_BONUS
    return bonus, f"Historiek: {count}x in {HISTORIEK_LOOKBACK_DAGEN} dagen"


def bereken_voorkeur_bonus(
    shift_type: str | None,
    voorkeuren: dict[str, int],
) -> tuple[float, str | None]:
    """
    Bereken bonus op basis van shift-type voorkeur (rang 1 = hoogste voorkeur).

    Returns:
        (bonus, reden_string | None)
    """
    if not shift_type or not voorkeuren or shift_type not in voorkeuren:
        return 0.0, None

    rang = voorkeuren[shift_type]
    if rang == 1:
        bonus = VOORKEUR_BONUS
    elif rang == 2:
        bonus = VOORKEUR_BONUS * 0.5
    else:
        bonus = VOORKEUR_BONUS * 0.2

    return bonus, f"Voorkeur rang {rang}"


def scoreer_shiftcode(
    shiftcode: str,
    shift_type: str | None,
    historiek: list[str | None],
    voorkeuren: dict[str, int],
) -> ShiftcodeSuggestie:
    """
    Bereken een ShiftcodeSuggestie voor een specifieke shiftcode en gebruikerscontext.

    Args:
        shiftcode: De te beoordelen shiftcode.
        shift_type: Shift-type van de code (bijv. 'vroeg', 'laat', 'nacht').
        historiek: Lijst van recente shift_codes voor deze gebruiker.
        voorkeuren: Parsed shift-voorkeuren {shift_type: rang}.
    """
    score = BASIS_SCORE
    redenen: list[str] = []

    hist_bonus, hist_reden = bereken_historiek_bonus(shiftcode, historiek)
    if hist_bonus > 0:
        score += hist_bonus
        redenen.append(hist_reden)

    voork_bonus, voork_reden = bereken_voorkeur_bonus(shift_type, voorkeuren)
    if voork_bonus > 0:
        score += voork_bonus
        redenen.append(voork_reden)

    return ShiftcodeSuggestie(
        shiftcode=shiftcode,
        score=max(0.0, min(score, MAX_SCORE)),
        redenen=redenen,
        is_valide=True,
    )


def suggereer_voor_weekdag(
    weekdag: int,
    historiek_per_weekdag: dict[int, list[str | None]],
) -> str | None:
    """
    Geef de meest voorkomende werkshiftcode voor een weekdag (voor batch-auto).

    Args:
        weekdag: Weekdag 0–6 (0 = maandag).
        historiek_per_weekdag: Dict {weekdag: [shift_codes]}.

    Returns:
        De meest voorkomende code, of None als geen historiek.
    """
    shifts = historiek_per_weekdag.get(weekdag, [])
    if not shifts:
        return None

    tellingen: dict[str, int] = {}
    for code in shifts:
        if code:
            tellingen[code.upper()] = tellingen.get(code.upper(), 0) + 1

    if not tellingen:
        return None

    return max(tellingen, key=lambda k: tellingen[k])


def bouw_historiek_per_weekdag(
    shift_codes_met_datum: list[tuple],
) -> dict[int, list[str | None]]:
    """
    Groepeer shift_codes per weekdag.

    Args:
        shift_codes_met_datum: Lijst van (datum: date, shift_code: str | None) tuples.

    Returns:
        Dict {weekdag: [shift_codes]}.
    """
    resultaat: dict[int, list[str | None]] = {}
    for datum, code in shift_codes_met_datum:
        weekdag = datum.weekday()
        resultaat.setdefault(weekdag, []).append(code)
    return resultaat
