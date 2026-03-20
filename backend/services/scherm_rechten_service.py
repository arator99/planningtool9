"""SchermRechten service — hybrid schermtoegang beheer (DB overrides + hardcoded defaults)."""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from models.scherm_recht import SchermRecht

logger = logging.getLogger(__name__)

# Hardcoded defaults: route_naam → (label, [toegestane_rollen])
SCHERM_DEFAULTS: dict[str, tuple[str, list[str]]] = {
    "/dashboard":          ("Dashboard",          ["teamlid", "planner", "hr", "beheerder", "super_beheerder"]),
    "/planning":           ("Planning",            ["planner", "beheerder", "super_beheerder"]),
    "/planning/mijn":      ("Mijn Planning",       ["teamlid", "planner", "hr", "beheerder", "super_beheerder"]),
    "/verlof":             ("Verlof",              ["teamlid", "planner", "hr", "beheerder", "super_beheerder"]),
    "/verlof/adv":         ("ADV",                 ["planner", "beheerder", "super_beheerder"]),
    "/rapporten":          ("Rapporten",           ["planner", "hr", "beheerder", "super_beheerder"]),
    "/notities":           ("Notities",            ["teamlid", "planner", "hr", "beheerder", "super_beheerder"]),
    "/shiftcodes":         ("Shiftcodes",          ["beheerder", "super_beheerder"]),
    "/werkposten":         ("Werkposten",          ["beheerder", "super_beheerder"]),
    "/hr":                 ("HR-regels",           ["hr", "beheerder", "super_beheerder"]),
    "/instellingen":       ("Instellingen",        ["beheerder", "super_beheerder"]),
    "/beheer/gebruikers":  ("Gebruikers",          ["beheerder", "super_beheerder"]),
    "/teams":              ("Teams",               ["planner", "beheerder", "super_beheerder"]),
    "/typetabellen":       ("Typetabellen",        ["beheerder", "super_beheerder"]),
    "/competenties":       ("Competenties",        ["beheerder", "super_beheerder"]),
    "/logboek":            ("Logboek",             ["beheerder", "super_beheerder"]),
    "/beheer/rechten":     ("Scherm rechten",      ["beheerder", "super_beheerder"]),
}

ALLE_ROLLEN = ["teamlid", "planner", "hr", "beheerder", "super_beheerder"]


class SchermRechtenService:
    """Service voor schermtoegang beheer.

    Hybrid: DB-override voor de locatie heeft prioriteit; daarna hardcoded default.
    """

    def __init__(self, db: Session, locatie_id: Optional[int]) -> None:
        self.db = db
        self.locatie_id = locatie_id

    def heeft_toegang(self, route_naam: str, rol: str) -> bool:
        """Bepaal of een rol toegang heeft tot een route voor deze locatie."""
        override = (
            self.db.query(SchermRecht)
            .filter(
                SchermRecht.route_naam == route_naam,
                SchermRecht.rol == rol,
                SchermRecht.locatie_id == self.locatie_id,
            )
            .first()
        )
        if override is not None:
            return bool(override.toegestaan)

        if route_naam in SCHERM_DEFAULTS:
            _, rollen = SCHERM_DEFAULTS[route_naam]
            return rol in rollen

        return False

    def haal_rechten_matrix(self) -> dict[str, dict[str, tuple[bool, bool]]]:
        """Bouw volledige rechtenmatrix: {route: {rol: (toegestaan, is_default)}}.

        is_default=True → geen DB-override aanwezig voor deze locatie.
        """
        overrides = (
            self.db.query(SchermRecht)
            .filter(SchermRecht.locatie_id == self.locatie_id)
            .all()
        )
        override_map: dict[tuple[str, str], bool] = {
            (o.route_naam, o.rol): bool(o.toegestaan) for o in overrides
        }

        matrix: dict[str, dict[str, tuple[bool, bool]]] = {}
        for route, (_, default_rollen) in SCHERM_DEFAULTS.items():
            matrix[route] = {}
            for rol in ALLE_ROLLEN:
                key = (route, rol)
                if key in override_map:
                    matrix[route][rol] = (override_map[key], False)
                else:
                    matrix[route][rol] = (rol in default_rollen, True)

        return matrix

    def zet_toegang(self, route_naam: str, rol: str, toegestaan: bool) -> None:
        """Sla een DB-override op. Verwijder de override als de waarde gelijk is aan de default."""
        if route_naam not in SCHERM_DEFAULTS:
            raise ValueError(f"Onbekende route: {route_naam}")

        _, default_rollen = SCHERM_DEFAULTS[route_naam]
        is_default_waarde = toegestaan == (rol in default_rollen)

        # Verwijder bestaande override (altijd)
        self.db.query(SchermRecht).filter(
            SchermRecht.route_naam == route_naam,
            SchermRecht.rol == rol,
            SchermRecht.locatie_id == self.locatie_id,
        ).delete()

        if not is_default_waarde:
            # Sla override op alleen als het afwijkt van de default
            nieuw = SchermRecht(
                route_naam=route_naam,
                rol=rol,
                locatie_id=self.locatie_id,
                toegestaan=toegestaan,
            )
            self.db.add(nieuw)

        self.db.commit()
        logger.info(
            "Schermrecht gewijzigd: route=%s rol=%s locatie=%s → %s",
            route_naam, rol, self.locatie_id, toegestaan,
        )

    def reset_route(self, route_naam: str) -> int:
        """Verwijder alle overrides voor een route binnen deze locatie. Geeft aantal terug."""
        verwijderd = (
            self.db.query(SchermRecht)
            .filter(
                SchermRecht.route_naam == route_naam,
                SchermRecht.locatie_id == self.locatie_id,
            )
            .delete()
        )
        self.db.commit()
        logger.info("Scherm '%s' gereset: %d overrides verwijderd", route_naam, verwijderd)
        return verwijderd
