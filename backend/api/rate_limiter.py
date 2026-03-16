from slowapi import Limiter
from slowapi.util import get_remote_address


def _haal_client_ip(request) -> str:
    """Leest het werkelijke client-IP achter Cloudflare Tunnel."""
    return (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or get_remote_address(request)
    )


limiter = Limiter(key_func=_haal_client_ip)
