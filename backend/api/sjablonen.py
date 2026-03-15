from datetime import date
from pathlib import Path

from fastapi.templating import Jinja2Templates

from i18n import vertaal
from stijlen import genereer_thema_css

sjablonen = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
sjablonen.env.globals["thema_css"] = genereer_thema_css()
sjablonen.env.globals["today"] = str(date.today())
sjablonen.env.globals["t_global"] = vertaal  # t_global(sleutel, taal) — voor gebruik zonder context
