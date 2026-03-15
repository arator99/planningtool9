import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import haal_db, haal_huidige_gebruiker, haal_csrf_token, verifieer_csrf
from api.rate_limiter import limiter
from api.sjablonen import sjablonen
from config import instellingen
from i18n import vertaal
from models.gebruiker import Gebruiker
from services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authenticatie"])

_SECURE = instellingen.omgeving != "development"


# ------------------------------------------------------------------ #
# Login / Logout                                                       #
# ------------------------------------------------------------------ #

TOEGESTANE_TALEN = {"nl", "fr", "en"}
_LOGIN_TALEN = ["nl", "fr", "en"]


def _login_js_vertalingen() -> dict:
    """Bouw vertalingen dict voor de login-pagina JS (alle talen)."""
    return {
        code: {
            "gebruikersnaam": vertaal("auth.gebruikersnaam", code),
            "placeholder_gn": vertaal("auth.gebruikersnaam_placeholder", code),
            "wachtwoord":     vertaal("auth.wachtwoord", code),
            "knop":           vertaal("auth.inloggen_btn", code),
        }
        for code in _LOGIN_TALEN
    }


@router.get("/login", response_class=HTMLResponse)
def toon_login(request: Request):
    """Toont de loginpagina. Pre-selecteert de taal uit cookie indien aanwezig."""
    geselecteerde_taal = request.cookies.get("taal", "nl")
    return sjablonen.TemplateResponse(
        "pages/login.html",
        {
            "request": request,
            "geselecteerde_taal": geselecteerde_taal,
            "js_vertalingen": _login_js_vertalingen(),
        },
    )


@router.post("/auth/inloggen")
@limiter.limit("5/minute")
def verwerk_inloggen(
    request: Request,
    gebruikersnaam: str = Form(...),
    wachtwoord: str = Form(...),
    taal: str = Form("nl"),
    db: Session = Depends(haal_db),
):
    """Verwerkt het loginformulier. Slaat taalvoorkeur op en zet cookie."""
    if taal not in TOEGESTANE_TALEN:
        taal = "nl"

    try:
        resultaat = AuthService(db).inloggen(gebruikersnaam, wachtwoord, taal)
    except ValueError as fout:
        logger.warning("Mislukte inlogpoging voor '%s'", gebruikersnaam)
        return sjablonen.TemplateResponse(
            "pages/login.html",
            {
                "request": request,
                "fout": str(fout),
                "geselecteerde_taal": taal,
                "js_vertalingen": _login_js_vertalingen(),
            },
            status_code=401,
        )

    if resultaat["stap"] == "totp_vereist":
        antwoord = RedirectResponse(url="/auth/totp", status_code=303)
        antwoord.set_cookie(key="totp_temp_token", value=resultaat["temp_token"],
                            httponly=True, samesite="strict", secure=_SECURE, max_age=300)
        antwoord.set_cookie(key="taal", value=taal, samesite="lax", secure=_SECURE,
                            max_age=60 * 60 * 24 * 365)
        return antwoord

    antwoord = RedirectResponse(url="/dashboard", status_code=303)
    antwoord.set_cookie(key="toegangs_token", value=resultaat["token"],
                        httponly=True, samesite="strict", secure=_SECURE)
    antwoord.set_cookie(key="taal", value=taal, samesite="lax", secure=_SECURE,
                        max_age=60 * 60 * 24 * 365)
    logger.info("Gebruiker '%s' ingelogd (taal: %s)", gebruikersnaam, taal)
    return antwoord


@router.post("/auth/uitloggen")
def uitloggen(
    _csrf: None = Depends(verifieer_csrf),
):
    """Verwijdert sessie cookies en stuurt terug naar loginpagina."""
    antwoord = RedirectResponse(url="/login", status_code=303)
    antwoord.delete_cookie("toegangs_token")
    antwoord.delete_cookie("totp_temp_token")
    return antwoord


# ------------------------------------------------------------------ #
# TOTP verificatie (tijdens inloggen)                                  #
# ------------------------------------------------------------------ #

@router.get("/auth/totp", response_class=HTMLResponse)
def toon_totp_verificatie(request: Request):
    """Toont de TOTP-invoerpagina (tweede stap bij inloggen)."""
    temp_token = request.cookies.get("totp_temp_token")
    if not temp_token:
        return RedirectResponse(url="/login", status_code=303)
    return sjablonen.TemplateResponse("pages/totp_verifieer.html", {"request": request})


@router.post("/auth/totp/verifieer")
@limiter.limit("5/minute")
def verwerk_totp_verificatie(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(haal_db),
):
    """Verifieert de TOTP code tijdens het inloggen."""
    temp_token = request.cookies.get("totp_temp_token")
    if not temp_token:
        return RedirectResponse(url="/login", status_code=303)

    try:
        access_token = AuthService(db).verifieer_totp_inlogstap(temp_token, code)
    except ValueError as fout:
        return sjablonen.TemplateResponse(
            "pages/totp_verifieer.html",
            {"request": request, "fout": str(fout)},
            status_code=401,
        )

    antwoord = RedirectResponse(url="/dashboard", status_code=303)
    antwoord.set_cookie(
        key="toegangs_token",
        value=access_token,
        httponly=True,
        samesite="strict",
        secure=_SECURE,
    )
    antwoord.delete_cookie("totp_temp_token")
    return antwoord


# ------------------------------------------------------------------ #
# TOTP instelling (na inloggen)                                        #
# ------------------------------------------------------------------ #

@router.get("/totp/instellen", response_class=HTMLResponse)
def toon_totp_instellen(
    request: Request,
    huidige_gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
    db: Session = Depends(haal_db),
    csrf_token: str = Depends(haal_csrf_token),
):
    """Genereert een QR code voor TOTP-instelling."""
    resultaat = AuthService(db).start_totp_instelling(huidige_gebruiker.id)
    antwoord = sjablonen.TemplateResponse(
        "pages/totp_instellen.html",
        {
            "request": request,
            "gebruiker": huidige_gebruiker,
            "totp_uri": resultaat["uri"],
            "totp_geheim": resultaat["geheim"],
            "csrf_token": csrf_token,
        },
    )
    antwoord.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    antwoord.headers["Pragma"] = "no-cache"
    return antwoord


@router.post("/totp/instellen/bevestig")
@limiter.limit("3/minute")
def bevestig_totp_instellen(
    request: Request,
    code: str = Form(...),
    huidige_gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
    db: Session = Depends(haal_db),
    _csrf: None = Depends(verifieer_csrf),
):
    """Verifieert de eerste TOTP code en activeert 2FA."""
    try:
        AuthService(db).bevestig_totp_instelling(huidige_gebruiker.id, code)
    except ValueError as fout:
        resultaat = AuthService(db).start_totp_instelling(huidige_gebruiker.id)
        return sjablonen.TemplateResponse(
            "pages/totp_instellen.html",
            {
                "request": request,
                "gebruiker": huidige_gebruiker,
                "totp_uri": resultaat["uri"],
                "totp_geheim": resultaat["geheim"],
                "fout": str(fout),
            },
            status_code=400,
        )

    return RedirectResponse(url="/welkom?totp=actief", status_code=303)


# ------------------------------------------------------------------ #
# Welkom (testpagina)                                                  #
# ------------------------------------------------------------------ #

@router.get("/welkom", response_class=HTMLResponse)
def toon_welkom(
    request: Request,
    huidige_gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
):
    """Testpagina na inloggen — toont gebruikersinfo."""
    totp_zojuist_actief = request.query_params.get("totp") == "actief"
    return sjablonen.TemplateResponse(
        "pages/welkom.html",
        {
            "request": request,
            "gebruiker": huidige_gebruiker,
            "totp_zojuist_actief": totp_zojuist_actief,
        },
    )
