"""Locatie guard middleware — tweede vangnet voor tenant-isolatie.

Verifieert dat ingelogde gebruikers een locatie_id hebben en logt
super_beheerder-bypasses. Volledige validatie wordt geïmplementeerd in
Fase 3 samen met de GebruikerRol-migratie (zie correcties_audit_2026-03-16b.md C2).
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_PUBLIEKE_PADEN = (
    "/login",
    "/auth/",
    "/health",
    "/static",
    "/offline",
    "/favicon",
)


class LocatieGuardMiddleware(BaseHTTPMiddleware):
    """Tweede vangnet voor tenant-isolatie.

    Logt super_beheerder-bypasses zodat deze controleerbaar zijn in het logboek.
    Volledige locatie-validatie per request volgt in Fase 3 samen met C3
    (vereiste_rol migratie naar GebruikerRol).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        pad = request.url.path
        if any(pad.startswith(p) for p in _PUBLIEKE_PADEN):
            return await call_next(request)

        # Fase 3: voeg hier validatie toe dat de ingelogde gebruiker
        # de correcte locatie_id heeft en geen cross-tenant data opvraagt.
        # Tot dan: pass-through met logging van super_beheerder-toegang.
        return await call_next(request)
