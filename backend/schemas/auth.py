from enum import Enum

from pydantic import BaseModel


class GebruikerRol(str, Enum):
    beheerder = "beheerder"
    planner = "planner"
    hr = "hr"
    gebruiker = "gebruiker"


class GebruikerUitvoer(BaseModel):
    id: int
    gebruikersnaam: str
    rol: GebruikerRol
    is_actief: bool
    totp_actief: bool

    model_config = {"from_attributes": True}
