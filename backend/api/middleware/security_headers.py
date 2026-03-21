"""Security headers middleware — voegt veiligheidsheaders toe aan elke response."""
import secrets
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import instellingen

# Per-request nonce — veilig voor async via ContextVar
_nonce_var: ContextVar[str] = ContextVar("csp_nonce", default="")


def haal_csp_nonce() -> str:
    """Geeft de CSP-nonce voor het huidige request terug (te gebruiken in Jinja2-templates)."""
    return _nonce_var.get()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    _CSP_PRODUCTIE_TMPL = (
        "default-src 'self'; "
        "script-src 'self' 'nonce-{{nonce}}' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://flagcdn.com; "
        "connect-src 'self';"
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        nonce = secrets.token_urlsafe(16)
        _nonce_var.set(nonce)
        antwoord = await call_next(request)
        antwoord.headers["X-Content-Type-Options"] = "nosniff"
        antwoord.headers["X-Frame-Options"] = "DENY"
        antwoord.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        antwoord.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if instellingen.omgeving != "development":
            csp = self._CSP_PRODUCTIE_TMPL.replace("{{nonce}}", nonce)
            antwoord.headers["Content-Security-Policy"] = csp
            antwoord.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return antwoord
