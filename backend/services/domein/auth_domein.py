"""
Domeinlaag: authenticatie — pure functies voor wachtwoord en JWT-tokens.
Geen SQLAlchemy, geen database-toegang.
"""
import re
import time

import bcrypt as _bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from jwt.exceptions import InvalidTokenError

from config import instellingen

_argon2 = PasswordHasher()

# Prefixen van legacy bcrypt-hashes (v0.7/v0.8 migratie)
_BCRYPT_PREFIXEN = ("$2b$", "$2a$", "$2y$")


# ------------------------------------------------------------------ #
# Wachtwoord                                                          #
# ------------------------------------------------------------------ #

def valideer_wachtwoord_sterkte(wachtwoord: str) -> str | None:
    """
    Controleert of een wachtwoord voldoet aan de sterkte-eisen.

    Returns:
        Foutmelding als string, of None als het wachtwoord geldig is.
    """
    if len(wachtwoord) < 8:
        return "Wachtwoord moet minimaal 8 tekens lang zijn."
    if not re.search(r"[A-Z]", wachtwoord):
        return "Wachtwoord moet minimaal één hoofdletter bevatten."
    if not re.search(r"[a-z]", wachtwoord):
        return "Wachtwoord moet minimaal één kleine letter bevatten."
    if not re.search(r"\d", wachtwoord):
        return "Wachtwoord moet minimaal één cijfer bevatten."
    if not re.search(r"[^A-Za-z0-9]", wachtwoord):
        return "Wachtwoord moet minimaal één speciaal teken bevatten."
    return None


def hash_wachtwoord(wachtwoord: str) -> str:
    """Hasht een plain-text wachtwoord met argon2 voor opslag in de database."""
    return _argon2.hash(wachtwoord)


def verifieer_wachtwoord(wachtwoord: str, gehashed: str) -> bool:
    """
    Verifieert een plain-text wachtwoord tegen een opgeslagen hash.

    Ondersteunt zowel argon2 (nieuw) als bcrypt (legacy migratie v0.7/v0.8).
    Bij een geldige bcrypt-verificatie wordt de hash NIET automatisch opnieuw gehashed —
    dat doet auth_service.verifieer_en_migreer() na een succesvolle login.
    """
    if gehashed.startswith(_BCRYPT_PREFIXEN):
        # Legacy bcrypt-hash — read-only verificatie
        return _bcrypt.checkpw(wachtwoord.encode(), gehashed.encode())
    try:
        return _argon2.verify(gehashed, wachtwoord)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def heeft_legacy_hash(gehashed: str) -> bool:
    """Geeft True als de hash nog een bcrypt-hash is (migratie nodig)."""
    return gehashed.startswith(_BCRYPT_PREFIXEN)


# ------------------------------------------------------------------ #
# JWT Tokens                                                          #
# ------------------------------------------------------------------ #

_AUD_TOEGANG = "toegang"
_AUD_TOTP_STAP = "totp_stap"
_AUD_TOTP_SETUP = "totp_setup"


def maak_access_token(gebruiker_id: int) -> str:
    """
    Maak een ondertekend JWT access token.

    Args:
        gebruiker_id: ID van de gebruiker (wordt 'sub' claim).

    Returns:
        Geserialiseerde JWT string.
    """
    verlooptijd = int(time.time()) + (instellingen.toegangs_token_verlopen_minuten * 60)
    payload = {"sub": gebruiker_id, "exp": verlooptijd, "aud": _AUD_TOEGANG}
    return jwt.encode(payload, instellingen.geheime_sleutel, algorithm="HS256")


def maak_totp_temp_token(gebruiker_id: int) -> str:
    """
    Maak een kortlopend JWT token voor de TOTP tussenstap (5 minuten geldig).

    Args:
        gebruiker_id: ID van de gebruiker.

    Returns:
        Geserialiseerde JWT string met 'stap'='totp'.
    """
    verlooptijd = int(time.time()) + (5 * 60)
    payload = {"sub": gebruiker_id, "stap": "totp", "exp": verlooptijd, "aud": _AUD_TOTP_STAP}
    return jwt.encode(payload, instellingen.geheime_sleutel, algorithm="HS256")


def verifieer_access_token(token: str) -> dict:
    """
    Decodeer en valideer een JWT access token.

    Returns:
        Payload dict met 'sub' (gebruiker_id) en 'rol'.

    Raises:
        ValueError: Bij ongeldig, verlopen of onvolledig token.
    """
    try:
        payload = jwt.decode(
            token, instellingen.geheime_sleutel, algorithms=["HS256"], audience=_AUD_TOEGANG
        )
        if payload.get("sub") is None:
            raise ValueError("Ongeldig token: geen gebruiker-ID")
        return payload
    except InvalidTokenError as fout:
        raise ValueError("Ongeldig of verlopen token") from fout


def maak_totp_setup_token(gebruiker_id: int) -> str:
    """
    Maak een kortlopend JWT token voor verplichte TOTP-instelling (15 minuten).

    Args:
        gebruiker_id: ID van de gebruiker.

    Returns:
        Geserialiseerde JWT string met aud='totp_setup'.
    """
    verlooptijd = int(time.time()) + (15 * 60)
    payload = {"sub": gebruiker_id, "stap": "totp_setup", "exp": verlooptijd, "aud": _AUD_TOTP_SETUP}
    return jwt.encode(payload, instellingen.geheime_sleutel, algorithm="HS256")


def verifieer_totp_setup_token(token: str) -> int:
    """
    Decodeer en valideer een TOTP-setup token.

    Returns:
        gebruiker_id als int.

    Raises:
        ValueError: Bij ongeldig token of verkeerde audience.
    """
    try:
        payload = jwt.decode(
            token, instellingen.geheime_sleutel, algorithms=["HS256"], audience=_AUD_TOTP_SETUP
        )
        if payload.get("stap") != "totp_setup":
            raise ValueError("Ongeldig setup token type")
        gebruiker_id: int | None = payload.get("sub")
        if gebruiker_id is None:
            raise ValueError("Ongeldig setup token: geen gebruiker-ID")
        return gebruiker_id
    except InvalidTokenError as fout:
        raise ValueError("Ongeldig of verlopen setup token") from fout


def verifieer_totp_temp_token(token: str) -> int:
    """
    Decodeer en valideer een TOTP tussenstap token.

    Returns:
        gebruiker_id als int.

    Raises:
        ValueError: Bij ongeldig token of verkeerde stap.
    """
    try:
        payload = jwt.decode(
            token, instellingen.geheime_sleutel, algorithms=["HS256"], audience=_AUD_TOTP_STAP
        )
        if payload.get("stap") != "totp":
            raise ValueError("Ongeldig temp token type")
        gebruiker_id: int | None = payload.get("sub")
        if gebruiker_id is None:
            raise ValueError("Ongeldig temp token: geen gebruiker-ID")
        return gebruiker_id
    except InvalidTokenError as fout:
        raise ValueError("Ongeldig of verlopen temp token") from fout
