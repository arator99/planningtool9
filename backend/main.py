import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from api.dependencies import haal_huidige_gebruiker, haal_csrf_token, haal_db
from api.rate_limiter import limiter
from api.routers import auth, health, gebruikers, planning, verlof, shiftcodes, hr, notities, rapporten, account, help, werkposten, competenties, logboek, groepen
from api.routers import instellingen as instellingen_router
from services.notitie_service import NotitieService
from services.verlof_service import VerlofService
from services.planning_service import PlanningService
from api.sjablonen import sjablonen
from i18n import maak_vertaler
from config import instellingen
from database import Basis, SessieKlasse, motor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def levensduur(app: FastAPI):
    """Startup: maak tabellen aan en seed een testgebruiker als de DB leeg is."""
    import models  # noqa: F401 — registreert alle ORM modellen bij Basis

    Basis.metadata.create_all(bind=motor)
    logger.info("Database tabellen aangemaakt/gecontroleerd")
    _seed_test_data()
    yield
    logger.info("Planning Tool v0.8 afgesloten")


def _seed_test_data() -> None:
    """Maakt een testgroep + beheerder aan als de database leeg is."""
    from models.groep import Groep, GroepConfig
    from models.gebruiker import Gebruiker
    from services.domein.auth_domein import hash_wachtwoord

    db = SessieKlasse()
    try:
        if db.query(Gebruiker).count() > 0:
            return  # Al geseed

        # Testgroep aanmaken
        groep = Groep(naam="Groep 1", code="GRP1", beschrijving="Testgroep voor ontwikkeling")
        db.add(groep)
        db.flush()  # Haal groep.id op zonder commit

        # Groepsconfiguratie
        groep_config = GroepConfig(groep_id=groep.id)
        db.add(groep_config)

        # Beheerder aanmaken
        admin = Gebruiker(
            gebruikersnaam="admin",
            gehashed_wachtwoord=hash_wachtwoord("Admin1234!"),
            volledige_naam="Beheerder",
            rol="beheerder",
            groep_id=groep.id,
            is_actief=True,
            totp_actief=False,
            taal="nl",
        )
        db.add(admin)
        db.flush()

        # Junction-record aanmaken voor admin
        from models.groep import GebruikerGroep
        db.add(GebruikerGroep(gebruiker_id=admin.id, groep_id=groep.id, is_reserve=False))

        # Test shiftcodes aanmaken
        from models.planning import Shiftcode
        test_codes = [
            Shiftcode(groep_id=groep.id, code="D",   start_uur="08:00", eind_uur="16:00", shift_type="early"),
            Shiftcode(groep_id=groep.id, code="DL",  start_uur="10:00", eind_uur="18:00", shift_type="late"),
            Shiftcode(groep_id=groep.id, code="N",   start_uur="22:00", eind_uur="06:00", shift_type="night"),
            Shiftcode(groep_id=groep.id, code="V",   start_uur=None,    eind_uur=None,    shift_type=None),
            Shiftcode(groep_id=groep.id, code="RXW", start_uur=None,    eind_uur=None,    shift_type=None),
        ]
        for code in test_codes:
            db.add(code)

        db.commit()

        logger.info("=" * 60)
        logger.info("TESTDATA AANGEMAAKT:")
        logger.info("  Groep          : Groep 1 (GRP1)")
        logger.info("  Gebruikersnaam : admin")
        logger.info("  Rol            : beheerder")
        logger.info("=" * 60)
    except Exception as fout:
        logger.error("Fout bij seeden testdata: %s", fout, exc_info=True)
        db.rollback()
    finally:
        db.close()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Voegt security headers toe aan alle responses."""

    _CSP_PRODUCTIE = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data: https://flagcdn.com; "
        "connect-src 'self';"
    )

    async def dispatch(self, request: Request, call_next) -> StarletteResponse:
        antwoord = await call_next(request)
        antwoord.headers["X-Content-Type-Options"] = "nosniff"
        antwoord.headers["X-Frame-Options"] = "DENY"
        antwoord.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        antwoord.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if instellingen.omgeving != "development":
            antwoord.headers["Content-Security-Policy"] = self._CSP_PRODUCTIE
        return antwoord


app = FastAPI(
    title="Planning Tool",
    version=instellingen.app_versie,
    lifespan=levensduur,
    docs_url="/api/docs" if instellingen.omgeving == "development" else None,
    redoc_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(gebruikers.router)
app.include_router(planning.router)
app.include_router(verlof.router)
app.include_router(shiftcodes.router)
app.include_router(hr.router)
app.include_router(notities.router)
app.include_router(rapporten.router)
app.include_router(account.router)
app.include_router(help.router)
app.include_router(werkposten.router)
app.include_router(competenties.router)
app.include_router(logboek.router)
app.include_router(instellingen_router.router)
app.include_router(groepen.router)


@app.get("/")
def startpagina():
    return RedirectResponse(url="/login")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    gebruiker=Depends(haal_huidige_gebruiker),
    csrf_token: str = Depends(haal_csrf_token),
    db=Depends(haal_db),
):
    ongelezen = NotitieService(db).haal_ongelezen_aantal(gebruiker.id, gebruiker.groep_id)
    komende_shifts = PlanningService(db).haal_komende_shifts(gebruiker.id, gebruiker.groep_id)
    pending_verlof = 0
    if gebruiker.rol in ("beheerder", "planner", "hr"):
        pending_verlof = VerlofService(db).haal_pending_count(gebruiker.groep_id)
    return sjablonen.TemplateResponse(
        "pages/dashboard.html",
        {
            "request": request,
            "gebruiker": gebruiker,
            "t": maak_vertaler(gebruiker.taal or "nl"),
            "csrf_token": csrf_token,
            "ongelezen_notities": ongelezen,
            "komende_shifts": komende_shifts,
            "pending_verlof": pending_verlof,
        },
    )
