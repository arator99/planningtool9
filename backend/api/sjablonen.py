from datetime import date
from pathlib import Path

from fastapi.templating import Jinja2Templates

from i18n import vertaal

sjablonen = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
sjablonen.env.globals["today"] = str(date.today())
sjablonen.env.globals["t_global"] = vertaal  # t_global(sleutel, taal) — voor gebruik zonder context


def heeft_rol(gebruiker, *rollen: str) -> bool:
    """Jinja2 helper: True als gebruiker minstens één van de opgegeven rollen actief heeft."""
    actieve = {r.rol for r in gebruiker.rollen if r.is_actief}
    return bool(actieve.intersection(rollen))


sjablonen.env.globals["heeft_rol"] = heeft_rol
