"""Help router — changelog en helpinformatie."""
import markdown
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from api.dependencies import vereiste_login, haal_csrf_token
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from models.gebruiker import Gebruiker

router = APIRouter(prefix="/help", tags=["help"])

_CHANGELOG_PAD = Path(__file__).parent.parent.parent / "CHANGELOG.md"


def _context(request: Request, gebruiker: Gebruiker, **extra) -> dict:
    return {"request": request, "gebruiker": gebruiker,
            "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}


@router.get("/changelog", response_class=HTMLResponse)
def toon_changelog(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_login),
    csrf_token: str = Depends(haal_csrf_token),
):
    if _CHANGELOG_PAD.exists():
        tekst = _CHANGELOG_PAD.read_text(encoding="utf-8")
        inhoud_html = markdown.markdown(tekst, extensions=["tables", "fenced_code"])
    else:
        inhoud_html = "<p>Changelog niet gevonden.</p>"

    return sjablonen.TemplateResponse(
        "pages/help/changelog.html",
        _context(request, gebruiker, inhoud_html=inhoud_html, csrf_token=csrf_token),
    )
