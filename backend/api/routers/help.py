"""Help router — changelog, helpinformatie en offline-pagina."""
import bleach
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
_TOEGESTANE_TAGS = [
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "strong", "em", "code", "pre",
    "ul", "ol", "li", "blockquote", "hr",
    "table", "thead", "tbody", "tr", "th", "td",
    "a",
]
_TOEGESTANE_ATTRIBUTEN = {"a": ["href", "title"], "td": ["align"], "th": ["align"]}


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
        inhoud_html = bleach.clean(inhoud_html, tags=_TOEGESTANE_TAGS,
                                   attributes=_TOEGESTANE_ATTRIBUTEN, strip=True)
    else:
        inhoud_html = "<p>Changelog niet gevonden.</p>"

    return sjablonen.TemplateResponse(
        "pages/help/changelog.html",
        _context(request, gebruiker, inhoud_html=inhoud_html, csrf_token=csrf_token),
    )


