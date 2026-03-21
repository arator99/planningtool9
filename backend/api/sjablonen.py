from datetime import date
from pathlib import Path

from fastapi.templating import Jinja2Templates

from api.middleware.security_headers import haal_csp_nonce
from i18n import vertaal

sjablonen = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
sjablonen.env.globals["today"] = str(date.today())
sjablonen.env.globals["t_global"] = vertaal  # t_global(sleutel, taal) — voor gebruik zonder context
sjablonen.env.globals["csp_nonce"] = haal_csp_nonce  # per-request nonce voor inline scripts


def heeft_rol(gebruiker, *rollen: str) -> bool:
    """Jinja2 helper: True als gebruiker minstens één van de opgegeven rollen actief heeft."""
    actieve = {r.rol for r in gebruiker.rollen if r.is_actief}
    return bool(actieve.intersection(rollen))


sjablonen.env.globals["heeft_rol"] = heeft_rol
