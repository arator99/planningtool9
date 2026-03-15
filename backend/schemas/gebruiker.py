import re
from typing import Optional

from pydantic import BaseModel, field_validator

from schemas.auth import GebruikerRol

_WACHTWOORD_PATROON = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+,.?":{}|<>]).{8,}$'
)
_GEBRUIKERSNAAM_PATROON = re.compile(r'^[a-zA-Z0-9_]+$')


class GebruikerAanmaken(BaseModel):
    gebruikersnaam: str
    wachtwoord: str
    volledige_naam: str
    voornaam: Optional[str] = None
    achternaam: Optional[str] = None
    rol: GebruikerRol
    is_reserve: bool = False
    startweek_typedienst: Optional[int] = None

    @field_validator("gebruikersnaam")
    @classmethod
    def valideer_gebruikersnaam(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Gebruikersnaam moet minstens 3 tekens bevatten")
        if not _GEBRUIKERSNAAM_PATROON.match(v):
            raise ValueError("Gebruikersnaam mag alleen letters, cijfers en _ bevatten")
        return v

    @field_validator("wachtwoord")
    @classmethod
    def valideer_wachtwoord(cls, v: str) -> str:
        if not _WACHTWOORD_PATROON.match(v):
            raise ValueError(
                "Wachtwoord moet minstens 8 tekens bevatten met een hoofdletter, "
                "kleine letter, cijfer en speciaal teken"
            )
        return v

    @field_validator("startweek_typedienst")
    @classmethod
    def valideer_startweek(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in range(1, 7):
            raise ValueError("Startweek moet tussen 1 en 6 liggen")
        return v


class GebruikerBewerken(BaseModel):
    gebruikersnaam: str
    volledige_naam: str
    voornaam: Optional[str] = None
    achternaam: Optional[str] = None
    rol: GebruikerRol
    is_reserve: bool = False
    startweek_typedienst: Optional[int] = None

    @field_validator("gebruikersnaam")
    @classmethod
    def valideer_gebruikersnaam(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Gebruikersnaam moet minstens 3 tekens bevatten")
        if not _GEBRUIKERSNAAM_PATROON.match(v):
            raise ValueError("Gebruikersnaam mag alleen letters, cijfers en _ bevatten")
        return v

    @field_validator("startweek_typedienst")
    @classmethod
    def valideer_startweek(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in range(1, 7):
            raise ValueError("Startweek moet tussen 1 en 6 liggen")
        return v


class WachtwoordReset(BaseModel):
    nieuw_wachtwoord: str

    @field_validator("nieuw_wachtwoord")
    @classmethod
    def valideer_wachtwoord(cls, v: str) -> str:
        if not _WACHTWOORD_PATROON.match(v):
            raise ValueError(
                "Wachtwoord moet minstens 8 tekens bevatten met een hoofdletter, "
                "kleine letter, cijfer en speciaal teken"
            )
        return v
