"""
DatabaseImportService — importeer en merge een JSON-export in de bestaande database.

Merge-strategie:
- Conflict-sleutel: uuid (aanwezig op alle operationele modellen)
- Bij conflict: skip (bestaande record blijft ongewijzigd)
- Volgorde: locaties → teams → gebruikers → rollen → werkposten → shiftcodes
            → planning → verlof → notities

Het JSON-bestand moet gegenereerd zijn door DatabaseExportService (versie 0.9).
"""

import json
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import psycopg2
from psycopg2.extras import execute_values

from services.backup_service import BackupService

logger = logging.getLogger(__name__)

_ONDERSTEUNDE_VERSIES = {"0.9"}


class MergeResultaat:
    """Resultaat van een merge-operatie."""

    def __init__(self) -> None:
        self.nieuw: dict[str, int] = {}
        self.overgeslagen: dict[str, int] = {}
        self.fouten: list[str] = []
        self.pre_backup: Optional[str] = None

    def totaal_nieuw(self) -> int:
        return sum(self.nieuw.values())

    def totaal_overgeslagen(self) -> int:
        return sum(self.overgeslagen.values())

    def als_dict(self) -> dict:
        return {
            "nieuw":          self.nieuw,
            "overgeslagen":   self.overgeslagen,
            "fouten":         self.fouten,
            "pre_backup":     self.pre_backup,
            "totaal_nieuw":   self.totaal_nieuw(),
            "totaal_overgeslagen": self.totaal_overgeslagen(),
        }


def _lees_export(pad: Path) -> dict:
    """
    Lees en valideer een JSON-exportbestand.

    Args:
        pad: Pad naar het JSON-bestand.

    Returns:
        Gevalideerde export-dict.

    Raises:
        ValueError: Als het bestand ongeldig of incompatibel is.
    """
    if not pad.exists():
        raise ValueError(f"Bestand niet gevonden: {pad}")

    try:
        with open(pad, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as fout:
        raise ValueError(f"Ongeldig JSON-bestand: {fout}") from fout

    versie = data.get("versie", "onbekend")
    if versie not in _ONDERSTEUNDE_VERSIES:
        raise ValueError(
            f"Onondersteunde export-versie: {versie}. "
            f"Alleen {_ONDERSTEUNDE_VERSIES} worden ondersteund."
        )

    if "tabellen" not in data:
        raise ValueError("Export bevat geen 'tabellen' sleutel.")

    return data


def _pg_verbinding() -> psycopg2.extensions.connection:
    """Maak verbinding met PostgreSQL via DATABASE_URL."""
    import os
    from urllib.parse import urlparse
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(url)


def _tel_bestaand(cur, tabel: str, uuid_kolom: str, uuid_waarde: str) -> bool:
    """Controleer of een record met het gegeven UUID al bestaat."""
    cur.execute(
        f"SELECT 1 FROM {tabel} WHERE {uuid_kolom} = %s LIMIT 1",
        (uuid_waarde,),
    )
    return cur.fetchone() is not None


def _verwerk_tabel_eenvoudig(
    cur,
    tabel: str,
    records: list[dict],
    uuid_kolom: str,
    kolommen: list[str],
    resultaat: MergeResultaat,
    label: str,
) -> None:
    """
    Voeg records in een tabel in, sla bestaande (op uuid) over.

    Args:
        cur:        psycopg2 cursor.
        tabel:      Tabelnaam in PostgreSQL.
        records:    Lijst van dicts uit de JSON-export.
        uuid_kolom: Kolom die als samenvoegingssleutel dient (typisch 'uuid').
        kolommen:   Te importeren kolommen (zonder id).
        resultaat:  MergeResultaat om aantallen bij te houden.
        label:      Leesbaar label voor logging.
    """
    nieuw = 0
    overgeslagen = 0

    for record in records:
        uuid_waarde = record.get(uuid_kolom)
        if not uuid_waarde:
            logger.warning("%s: record zonder uuid overgeslagen: %s", label, record)
            overgeslagen += 1
            continue

        if _tel_bestaand(cur, tabel, uuid_kolom, uuid_waarde):
            overgeslagen += 1
            continue

        waarden = tuple(record.get(k) for k in kolommen)
        placeholders = ", ".join(["%s"] * len(kolommen))
        kolomnamen = ", ".join(kolommen)

        try:
            cur.execute(
                f"INSERT INTO {tabel} ({kolomnamen}) VALUES ({placeholders})",
                waarden,
            )
            nieuw += 1
        except Exception as fout:
            logger.warning("%s: insert mislukt voor uuid=%s: %s", label, uuid_waarde, fout)
            resultaat.fouten.append(f"{label} uuid={uuid_waarde}: {fout}")
            overgeslagen += 1

    resultaat.nieuw[label] = nieuw
    resultaat.overgeslagen[label] = overgeslagen
    logger.info("  %s: %s nieuw, %s overgeslagen", label, nieuw, overgeslagen)


class DatabaseImportService:
    """Service voor het importeren en samenvoegen van een JSON-export."""

    @classmethod
    def voorvertoning(cls, pad: Path) -> dict:
        """
        Analyseer een JSON-exportbestand en geef een samenvatting zonder te importeren.

        Args:
            pad: Pad naar het JSON-exportbestand.

        Returns:
            Dict met per tabel: aantal records in export + hoeveel al bestaan.
        """
        export = _lees_export(pad)
        pg = _pg_verbinding()
        cur = pg.cursor()
        overzicht = {}

        try:
            for tabel_naam, records in export["tabellen"].items():
                if not records:
                    overzicht[tabel_naam] = {"export": 0, "nieuw": 0, "bestaand": 0}
                    continue

                pg_tabel = _JSON_NAAR_PG_TABEL.get(tabel_naam, tabel_naam)
                uuid_kolom = _UUID_KOLOM.get(tabel_naam, "uuid")

                nieuw = 0
                bestaand = 0
                for record in records:
                    uuid_waarde = record.get(uuid_kolom)
                    if uuid_waarde and _tel_bestaand(cur, pg_tabel, uuid_kolom, uuid_waarde):
                        bestaand += 1
                    else:
                        nieuw += 1

                overzicht[tabel_naam] = {
                    "export":   len(records),
                    "nieuw":    nieuw,
                    "bestaand": bestaand,
                }
        finally:
            cur.close()
            pg.close()

        return {
            "versie":         export.get("versie"),
            "export_tijdstip": export.get("export_tijdstip"),
            "tabellen":       overzicht,
        }

    @classmethod
    def merge(cls, pad: Path) -> MergeResultaat:
        """
        Voer een merge uit: importeer records uit het JSON-bestand die nog niet bestaan.

        Maakt eerst een pre-restore backup.

        Args:
            pad: Pad naar het JSON-exportbestand.

        Returns:
            MergeResultaat met aantallen en eventuele fouten.
        """
        export = _lees_export(pad)
        resultaat = MergeResultaat()

        # Pre-restore backup
        pre_backup = BackupService.maak_pre_restore_backup()
        if pre_backup is None:
            raise ValueError("Kon geen pre-merge backup aanmaken. Merge afgebroken.")
        resultaat.pre_backup = pre_backup.name
        logger.info("Pre-merge backup aangemaakt: %s", pre_backup.name)

        pg = _pg_verbinding()
        try:
            _voer_merge_uit(pg, export["tabellen"], resultaat)
            pg.commit()
            logger.info(
                "Merge succesvol: %s nieuw, %s overgeslagen, %s fouten",
                resultaat.totaal_nieuw(),
                resultaat.totaal_overgeslagen(),
                len(resultaat.fouten),
            )
        except Exception as fout:
            pg.rollback()
            logger.error("Merge mislukt, rollback uitgevoerd: %s", fout, exc_info=True)
            raise
        finally:
            pg.close()

        return resultaat


# ─────────────────────────────── interne merge-logica ─────────────── #

# Mapping van JSON-tabelnamen naar PostgreSQL-tabelnamen
_JSON_NAAR_PG_TABEL: dict[str, str] = {
    "locaties":              "locaties",
    "teams":                 "teams",
    "team_configs":          "team_configs",
    "gebruikers":            "gebruikers",
    "gebruiker_rollen":      "gebruiker_rollen",
    "werkposten":            "werkposten",
    "shiftcodes":            "shiftcodes",
    "nationale_hr_regels":   "nationale_hr_regels",
    "locatie_hr_overrides":  "locatie_hr_overrides",
    "planning":              "planning",
    "verlof_aanvragen":      "verlof_aanvragen",
    "notities":              "notities",
}

# UUID-kolom per tabel (voor conflict-detectie)
_UUID_KOLOM: dict[str, str] = {
    "locaties":              "uuid",
    "teams":                 "uuid",
    "team_configs":          "team_id",   # team_configs heeft geen uuid — team_id is uniek
    "gebruikers":            "uuid",
    "gebruiker_rollen":      "uuid",
    "werkposten":            "uuid",
    "shiftcodes":            "uuid",
    "nationale_hr_regels":   "uuid",
    "locatie_hr_overrides":  "uuid",
    "planning":              "uuid",
    "verlof_aanvragen":      "uuid",
    "notities":              "uuid",
}

# Kolommen te importeren per tabel (id wordt door PostgreSQL gegenereerd)
_KOLOMMEN: dict[str, list[str]] = {
    "locaties": [
        "uuid", "naam", "code", "area_label", "is_actief", "aangemaakt_op",
        "verwijderd_op", "verwijderd_door_id",
    ],
    "teams": [
        "uuid", "naam", "code", "locatie_id", "beschrijving", "is_actief", "aangemaakt_op",
        "verwijderd_op", "verwijderd_door_id",
    ],
    "gebruikers": [
        "uuid", "gebruikersnaam", "gehashed_wachtwoord",
        "volledige_naam", "voornaam", "achternaam",
        "rol", "locatie_id", "is_reserve", "startweek_typedienst", "shift_voorkeuren",
        "thema", "taal", "totp_actief", "totp_geheim",
        "is_actief", "aangemaakt_op", "gedeactiveerd_op", "laatste_login",
        "verwijderd_op", "verwijderd_door_id",
    ],
    "gebruiker_rollen": [
        "uuid", "gebruiker_id", "rol", "scope_id", "is_reserve", "is_actief",
    ],
    "werkposten": [
        "uuid", "locatie_id", "naam", "beschrijving",
        "telt_als_werkdag", "reset_12u_rust", "breekt_werk_reeks", "is_actief",
        "aangemaakt_op", "gedeactiveerd_op", "verwijderd_op", "verwijderd_door_id",
    ],
    "shiftcodes": [
        "uuid", "werkpost_id", "locatie_id", "dag_type", "shift_type", "code",
        "beschrijving", "start_uur", "eind_uur", "is_kritisch",
        "telt_als_werkdag", "is_nachtprestatie", "reset_nacht",
    ],
    "nationale_hr_regels": [
        "uuid", "code", "naam", "waarde", "eenheid", "richting", "ernst_niveau",
        "beschrijving", "is_actief",
    ],
    "locatie_hr_overrides": [
        "uuid", "nationale_regel_id", "locatie_id", "waarde",
        "aangemaakt_op", "aangemaakt_door_id",
    ],
    "planning": [
        "uuid", "gebruiker_id", "team_id", "datum", "shift_code",
        "notitie", "notitie_gelezen", "status", "aangemaakt_op",
        "verwijderd_op", "verwijderd_door_id",
    ],
    "verlof_aanvragen": [
        "uuid", "gebruiker_id", "start_datum", "eind_datum", "aantal_dagen",
        "status", "toegekende_code_term", "opmerking", "aangevraagd_op",
        "behandeld_door", "behandeld_op", "reden_weigering", "ingediend_door",
        "verwijderd_op", "verwijderd_door_id",
    ],
    "notities": [
        "uuid", "afzender_id", "ontvanger_id", "onderwerp", "inhoud",
        "is_gelezen", "aangemaakt_op", "verwijderd_op", "verwijderd_door_id",
    ],
}


def _voer_merge_uit(pg, tabellen: dict[str, list[dict]], resultaat: MergeResultaat) -> None:
    """
    Voer de volledige merge uit in de juiste FK-volgorde.

    team_configs worden apart behandeld omdat ze geen uuid hebben.
    """
    cur = pg.cursor()

    volgorde = [
        "locaties",
        "teams",
        "gebruikers",
        "gebruiker_rollen",
        "werkposten",
        "shiftcodes",
        "nationale_hr_regels",
        "locatie_hr_overrides",
        "planning",
        "verlof_aanvragen",
        "notities",
    ]

    for tabel_naam in volgorde:
        records = tabellen.get(tabel_naam, [])
        if not records:
            resultaat.nieuw[tabel_naam] = 0
            resultaat.overgeslagen[tabel_naam] = 0
            continue

        pg_tabel = _JSON_NAAR_PG_TABEL[tabel_naam]
        uuid_kolom = _UUID_KOLOM[tabel_naam]
        kolommen = [k for k in _KOLOMMEN[tabel_naam] if k in records[0]]

        _verwerk_tabel_eenvoudig(
            cur, pg_tabel, records, uuid_kolom, kolommen, resultaat, tabel_naam
        )

    # team_configs: geen uuid → dedupliceer op team_id
    team_config_records = tabellen.get("team_configs", [])
    nieuw_tc = 0
    overgeslagen_tc = 0
    for record in team_config_records:
        team_id = record.get("team_id")
        if not team_id:
            overgeslagen_tc += 1
            continue
        cur.execute("SELECT 1 FROM team_configs WHERE team_id = %s", (team_id,))
        if cur.fetchone():
            overgeslagen_tc += 1
        else:
            try:
                cur.execute(
                    "INSERT INTO team_configs (team_id, standaard_taal) VALUES (%s, %s)",
                    (team_id, record.get("standaard_taal", "nl")),
                )
                nieuw_tc += 1
            except Exception as fout:
                resultaat.fouten.append(f"team_configs team_id={team_id}: {fout}")
                overgeslagen_tc += 1

    resultaat.nieuw["team_configs"] = nieuw_tc
    resultaat.overgeslagen["team_configs"] = overgeslagen_tc
    logger.info("  team_configs: %s nieuw, %s overgeslagen", nieuw_tc, overgeslagen_tc)

    cur.close()
