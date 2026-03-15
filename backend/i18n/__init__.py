"""i18n — vertaalinfrastructuur voor Planning Tool v0.8.

Gebruik:
    from i18n import maak_vertaler

    # In router _context():
    t = maak_vertaler(gebruiker.taal)
    return {"t": t, ...}

    # In template:
    {{ t("verlof.aanvragen") }}
    {{ t("algemeen.opgeslagen", naam="Jan") }}

Fallback:
    1. Gevraagde taal → 2. Nederlands → 3. Sleutel zelf
"""
import json
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

TALEN = {"nl", "fr", "en"}
STANDAARD_TAAL = "nl"
_I18N_MAP = Path(__file__).parent


@lru_cache(maxsize=None)
def _laad(taal: str) -> dict[str, str]:
    assert taal in TALEN, f"Ongeldige taalcode in _laad(): {taal!r}"
    pad = _I18N_MAP / f"{taal}.json"
    if not pad.exists():
        logger.warning("Vertaalbestand niet gevonden: %s", pad)
        return {}
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Fout bij laden vertaling %s: %s", taal, e)
        return {}


def vertaal(sleutel: str, taal: str = STANDAARD_TAAL, **kwargs) -> str:
    """
    Vertaal een sleutel naar de opgegeven taal.

    Fallback: gevraagde taal → Nederlands → sleutel zelf.
    Ondersteunt str.format() placeholders via kwargs.
    """
    taal = taal if taal in TALEN else STANDAARD_TAAL

    tekst = _laad(taal).get(sleutel)

    if tekst is None and taal != STANDAARD_TAAL:
        tekst = _laad(STANDAARD_TAAL).get(sleutel)

    if tekst is None:
        return sleutel  # Toon sleutel als fallback

    if kwargs:
        try:
            return tekst.format(**kwargs)
        except KeyError:
            return tekst

    return tekst


def maak_vertaler(taal: str) -> Callable[[str], str]:
    """
    Geeft een gebonden vertaalfunctie terug voor een specifieke taal.
    Gebruik in router _context() om `t` beschikbaar te maken in templates.
    """
    taal = taal if taal in TALEN else STANDAARD_TAAL

    def t(sleutel: str, **kwargs) -> str:
        return vertaal(sleutel, taal, **kwargs)

    return t
