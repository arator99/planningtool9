"""Security headers middleware — voegt veiligheidsheaders toe aan elke response."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import instellingen


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    _CSP_PRODUCTIE = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://flagcdn.com; "
        "connect-src 'self';"
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        antwoord = await call_next(request)
        antwoord.headers["X-Content-Type-Options"] = "nosniff"
        antwoord.headers["X-Frame-Options"] = "DENY"
        antwoord.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        antwoord.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if instellingen.omgeving != "development":
            antwoord.headers["Content-Security-Policy"] = self._CSP_PRODUCTIE
            antwoord.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return antwoord
