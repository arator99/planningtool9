"""
Domeinlaag: CSRF-tokenbeveiliging via het synchronizer token pattern.
Gebruikt itsdangerous (transitive dependency via Starlette/FastAPI).
Geen SQLAlchemy, geen database-toegang.
"""
import logging

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import instellingen

logger = logging.getLogger(__name__)

_SALT = "csrf"
_MAX_AGE = 3600  # 1 uur


def genereer_csrf_token(sessie_id: str) -> str:
    """Genereert een HMAC-gesigneerd CSRF-token gekoppeld aan de sessie-ID."""
    serializer = URLSafeTimedSerializer(instellingen.geheime_sleutel)
    return serializer.dumps(sessie_id, salt=_SALT)


def verifieer_csrf_token(token: str, sessie_id: str, max_age: int = _MAX_AGE) -> bool:
    """
    Verifieert het CSRF-token.
    Retourneert True als het token geldig is en overeenkomt met sessie_id.
    Retourneert False bij elk falen (verlopen, ongeldig, mismatch).
    """
    serializer = URLSafeTimedSerializer(instellingen.geheime_sleutel)
    try:
        waarde = serializer.loads(token, salt=_SALT, max_age=max_age)
    except SignatureExpired:
        logger.warning("CSRF-token verlopen voor sessie %s", sessie_id)
        return False
    except BadSignature:
        logger.warning("Ongeldig CSRF-token voor sessie %s", sessie_id)
        return False
    return waarde == sessie_id
