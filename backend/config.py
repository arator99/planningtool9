from pydantic import model_validator
from pydantic_settings import BaseSettings

_DEVELOPMENT_SENTINEL = "dev-geheime-sleutel-ALLEEN-voor-lokale-test-niet-in-productie"


class Instellingen(BaseSettings):
    database_url: str
    geheime_sleutel: str
    toegangs_token_verlopen_minuten: int = 30
    omgeving: str = "development"
    app_versie: str = "0.9.0"

    model_config = {"env_file": ".env"}

    @model_validator(mode="after")
    def controleer_productie_secret(self) -> "Instellingen":
        if self.omgeving != "development" and self.geheime_sleutel == _DEVELOPMENT_SENTINEL:
            raise ValueError(
                "GEHEIME_SLEUTEL mag niet de development-standaardwaarde zijn in productie."
            )
        return self


instellingen = Instellingen()
