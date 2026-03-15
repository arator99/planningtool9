import logging

import pyotp
from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from services.domein.auth_domein import (
    hash_wachtwoord,
    maak_access_token,
    maak_totp_temp_token,
    verifieer_access_token,
    verifieer_totp_temp_token,
    valideer_wachtwoord_sterkte,
    verifieer_wachtwoord,
)

logger = logging.getLogger(__name__)


class AuthService:
    """Authenticatie service: inloggen, JWT tokens, TOTP 2FA en wachtwoord hashing."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Inloggen                                                             #
    # ------------------------------------------------------------------ #

    def inloggen(self, gebruikersnaam: str, wachtwoord: str, taal: str = "nl") -> dict:
        """
        Verifieert inloggegevens en slaat taalvoorkeur op.

        Returns:
            {"stap": "ingelogd", "token": ..., "gebruiker": ...}
            {"stap": "totp_vereist", "temp_token": ...}

        Raises:
            ValueError: Bij ongeldige inloggegevens of inactief account.
        """
        gebruiker = self._haal_gebruiker(gebruikersnaam)
        if not gebruiker or not verifieer_wachtwoord(wachtwoord, gebruiker.gehashed_wachtwoord):
            raise ValueError("Ongeldige gebruikersnaam of wachtwoord")
        if not gebruiker.is_actief:
            logger.warning("Inlogpoging op gedeactiveerd account: '%s'", gebruikersnaam)
            raise ValueError("Ongeldige gebruikersnaam of wachtwoord")

        if gebruiker.taal != taal:
            gebruiker.taal = taal
            self.db.commit()

        if gebruiker.totp_actief:
            return {
                "stap": "totp_vereist",
                "temp_token": maak_totp_temp_token(gebruiker.id),
            }

        return {
            "stap": "ingelogd",
            "token": maak_access_token(gebruiker.id, gebruiker.rol),
            "gebruiker": gebruiker,
        }

    # ------------------------------------------------------------------ #
    # Token verificatie                                                    #
    # ------------------------------------------------------------------ #

    def verifieer_token(self, token: str) -> Gebruiker:
        """
        Verifieert een JWT access token.

        Raises:
            ValueError: Bij ongeldig, verlopen of onbekend token.
        """
        payload = verifieer_access_token(token)
        gebruiker_id: int = payload["sub"]

        gebruiker = self.db.query(Gebruiker).filter(Gebruiker.id == gebruiker_id).first()
        if not gebruiker or not gebruiker.is_actief:
            raise ValueError("Gebruiker niet gevonden of inactief")
        return gebruiker

    def verifieer_totp_temp_token(self, token: str) -> int:
        """
        Verifieert een TOTP-tussenstap token en geeft het gebruiker-ID terug.

        Raises:
            ValueError: Bij ongeldig token of verkeerde stap.
        """
        return verifieer_totp_temp_token(token)

    # ------------------------------------------------------------------ #
    # TOTP 2FA                                                             #
    # ------------------------------------------------------------------ #

    def start_totp_instelling(self, gebruiker_id: int) -> dict:
        """
        Genereert een nieuw TOTP geheim en slaat het op (nog niet actief).

        Returns:
            {"geheim": ..., "uri": ...}  (uri is voor QR code)
        """
        gebruiker = self._haal_gebruiker_op_id(gebruiker_id)
        geheim = pyotp.random_base32()
        gebruiker.totp_geheim = geheim
        gebruiker.totp_actief = False
        self.db.commit()

        uri = pyotp.TOTP(geheim).provisioning_uri(
            name=gebruiker.gebruikersnaam,
            issuer_name="Planning Tool",
        )
        return {"geheim": geheim, "uri": uri}

    def bevestig_totp_instelling(self, gebruiker_id: int, code: str) -> None:
        """
        Verifieert de eerste TOTP code en activeert 2FA voor de gebruiker.

        Raises:
            ValueError: Bij ongeldige code of geen setup gevonden.
        """
        gebruiker = self._haal_gebruiker_op_id(gebruiker_id)
        if not gebruiker.totp_geheim:
            raise ValueError("Geen TOTP setup gevonden — start opnieuw")

        totp = pyotp.TOTP(gebruiker.totp_geheim)
        if not totp.verify(code, valid_window=1):
            raise ValueError("Ongeldige code — controleer de tijd op uw apparaat")

        gebruiker.totp_actief = True
        self.db.commit()
        logger.info("TOTP geactiveerd voor gebruiker %s", gebruiker.gebruikersnaam)

    def verifieer_totp_inlogstap(self, temp_token: str, code: str) -> str:
        """
        Verifieert TOTP code tijdens het inloggen.

        Returns:
            Volledig JWT access token.

        Raises:
            ValueError: Bij ongeldig temp token of ongeldige code.
        """
        gebruiker_id = verifieer_totp_temp_token(temp_token)
        gebruiker = self._haal_gebruiker_op_id(gebruiker_id)

        if not gebruiker.totp_geheim or not gebruiker.totp_actief:
            raise ValueError("TOTP niet geconfigureerd voor dit account")

        totp = pyotp.TOTP(gebruiker.totp_geheim)
        if not totp.verify(code, valid_window=1):
            raise ValueError("Ongeldige authenticatiecode — probeer opnieuw")

        logger.info("TOTP geslaagd voor gebruiker %s", gebruiker.gebruikersnaam)
        return maak_access_token(gebruiker.id, gebruiker.rol)

    # ------------------------------------------------------------------ #
    # Wachtwoord beheer                                                    #
    # ------------------------------------------------------------------ #

    def wijzig_wachtwoord(
        self, gebruiker_id: int, huidig_wachtwoord: str, nieuw_wachtwoord: str
    ) -> None:
        """
        Wijzigt het wachtwoord van de ingelogde gebruiker.

        Raises:
            ValueError: Als het huidige wachtwoord onjuist is of het nieuwe
                        wachtwoord niet voldoet aan de sterkte-eisen.
        """
        gebruiker = self._haal_gebruiker_op_id(gebruiker_id)

        if not verifieer_wachtwoord(huidig_wachtwoord, gebruiker.gehashed_wachtwoord):
            raise ValueError("Huidig wachtwoord is onjuist.")

        fout = valideer_wachtwoord_sterkte(nieuw_wachtwoord)
        if fout:
            raise ValueError(fout)

        gebruiker.gehashed_wachtwoord = hash_wachtwoord(nieuw_wachtwoord)
        self.db.commit()
        logger.info("Wachtwoord gewijzigd voor gebruiker %s", gebruiker.gebruikersnaam)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _haal_gebruiker(self, gebruikersnaam: str) -> Gebruiker | None:
        return (
            self.db.query(Gebruiker)
            .filter(Gebruiker.gebruikersnaam == gebruikersnaam)
            .first()
        )

    def _haal_gebruiker_op_id(self, gebruiker_id: int) -> Gebruiker:
        gebruiker = self.db.query(Gebruiker).filter(Gebruiker.id == gebruiker_id).first()
        if not gebruiker:
            raise ValueError("Gebruiker niet gevonden")
        return gebruiker
