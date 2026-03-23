"""
DatabaseExportService — exporteer de volledige database als JSON.

Het JSON-formaat is ontworpen voor merge-import: elke tabel als lijst van dicts,
met UUID als samenvoegingssleutel. Gebruikt voor de GUI-merge functionaliteit.

Let op: bevat geen audit_log of sessie-data — enkel operationele en configuratiedata.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol
from models.hr import NationaleHRRegel, LocatieHROverride
from models.locatie import Locatie
from models.notitie import Notitie
from models.planning import Planning, Shiftcode, Werkpost
from models.team import Team, TeamConfig
from models.verlof import VerlofAanvraag

logger = logging.getLogger(__name__)

_EXPORT_VERSIE = "0.9"


def _serialiseer(waarde: Any) -> Any:
    """Converteer Python-typen naar JSON-serialiseerbare waarden."""
    if isinstance(waarde, datetime):
        return waarde.isoformat()
    if isinstance(waarde, date):
        return waarde.isoformat()
    return waarde


def _model_naar_dict(obj) -> dict:
    """Converteer een SQLAlchemy-model naar een dict van kolom-waarden."""
    return {
        kolom.key: _serialiseer(getattr(obj, kolom.key))
        for kolom in obj.__class__.__table__.columns
    }


class DatabaseExportService:
    """Service voor het exporteren van de database naar JSON-formaat."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def exporteer_naar_json(self) -> dict:
        """
        Exporteer alle operationele en configuratiedata naar een JSON-structuur.

        Uitgesloten: audit_log, notificaties, sessiedata.

        Returns:
            Dict met versie, tijdstip en per-tabel lijsten van records.
        """
        logger.info("Database export gestart")
        export = {
            "versie": _EXPORT_VERSIE,
            "export_tijdstip": datetime.now().isoformat(),
            "tabellen": {
                "locaties":           self._exporteer_locaties(),
                "teams":              self._exporteer_teams(),
                "team_configs":       self._exporteer_team_configs(),
                "gebruikers":         self._exporteer_gebruikers(),
                "gebruiker_rollen":   self._exporteer_gebruiker_rollen(),
                "werkposten":         self._exporteer_werkposten(),
                "shiftcodes":         self._exporteer_shiftcodes(),
                "nationale_hr_regels": self._exporteer_nationale_hr_regels(),
                "locatie_hr_overrides": self._exporteer_locatie_hr_overrides(),
                "planning":           self._exporteer_planning(),
                "verlof_aanvragen":   self._exporteer_verlof(),
                "notities":           self._exporteer_notities(),
            },
        }
        totaal = sum(len(v) for v in export["tabellen"].values())
        logger.info("Export klaar: %s records in %s tabellen", totaal, len(export["tabellen"]))
        return export

    def exporteer_naar_bestand(self, pad: Path) -> int:
        """
        Schrijf de export naar een JSON-bestand.

        Args:
            pad: Doelpad voor het JSON-bestand.

        Returns:
            Aantal geëxporteerde records.
        """
        export = self.exporteer_naar_json()
        pad.parent.mkdir(parents=True, exist_ok=True)
        with open(pad, "w", encoding="utf-8") as f:
            json.dump(export, f, ensure_ascii=False, indent=2)
        totaal = sum(len(v) for v in export["tabellen"].values())
        logger.info("Export opgeslagen: %s (%s records)", pad, totaal)
        return totaal

    # ── Privé exporteurs per tabel ───────────────────────────────────── #

    def _exporteer_locaties(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(Locatie).all()]

    def _exporteer_teams(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(Team).all()]

    def _exporteer_team_configs(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(TeamConfig).all()]

    def _exporteer_gebruikers(self) -> list[dict]:
        """Exporteer gebruikers — wachtwoord-hashes worden meegenomen voor restore."""
        return [_model_naar_dict(r) for r in self.db.query(Gebruiker).all()]

    def _exporteer_gebruiker_rollen(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(GebruikerRol).all()]

    def _exporteer_werkposten(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(Werkpost).all()]

    def _exporteer_shiftcodes(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(Shiftcode).all()]

    def _exporteer_nationale_hr_regels(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(NationaleHRRegel).all()]

    def _exporteer_locatie_hr_overrides(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(LocatieHROverride).all()]

    def _exporteer_planning(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(Planning).all()]

    def _exporteer_verlof(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(VerlofAanvraag).all()]

    def _exporteer_notities(self) -> list[dict]:
        return [_model_naar_dict(r) for r in self.db.query(Notitie).all()]
