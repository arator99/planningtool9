"""Planning Tool v0.9 — app entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.middleware.security_headers import SecurityHeadersMiddleware
from api.rate_limiter import limiter
from api.routers import (
    auth, health, gebruikers, planning, verlof, shiftcodes, hr, notities,
    rapporten, account, help, werkposten, competenties, logboek, teams,
)
from api.routers import instellingen as instellingen_router
from api.routers import beheer_hr, dashboard
from api.seed import seed_test_data
from config import instellingen
from database import Basis, motor

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
    seed_test_data()
    yield
    logger.info("Planning Tool v0.9 afgesloten")


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
app.include_router(dashboard.router)
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
app.include_router(teams.router)
app.include_router(beheer_hr.router)


@app.get("/")
def startpagina():
    return RedirectResponse(url="/login")
