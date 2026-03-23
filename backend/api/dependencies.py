"""FastAPI dependencies — authenticatie, autorisatie en locatie-context.

Rolmodel (v0.9):
  GebruikerRol   → enkel administratieve rollen: super_beheerder | beheerder | hr
  Lidmaatschap   → teamkoppeling: is_planner=True geeft plannerrechten binnen een team
"""
import logging

from fastapi import Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from database import SessieKlasse
from models.gebruiker import Gebruiker
from models.gebruiker_rol import GebruikerRol, GebruikerRolType
from services.auth_service import AuthService
from services.domein.csrf_domein import genereer_csrf_token, verifieer_csrf_token


# ---------------------------------------------------------------------------
# DB-sessie
# ---------------------------------------------------------------------------

def haal_db():
    """FastAPI dependency: geeft een database sessie en sluit deze na gebruik."""
    db = SessieKlasse()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Authenticatie
# ---------------------------------------------------------------------------

def haal_huidige_gebruiker(
    request: Request,
    db: Session = Depends(haal_db),
) -> Gebruiker:
    """
    FastAPI dependency: leest het JWT token uit de httpOnly cookie
    en geeft de ingelogde gebruiker terug.
    """
    token = request.cookies.get("toegangs_token")
    logger.debug("Cookies aanwezig: %s", list(request.cookies.keys()))
    if not token:
        logger.warning("Geen 'toegangs_token' cookie gevonden bij %s", request.url.path)
        raise HTTPException(status_code=401, detail="Niet ingelogd")
    try:
        return AuthService(db).verifieer_token(token)
    except ValueError as fout:
        logger.error("Token verificatie mislukt: %s", fout)
        raise HTTPException(status_code=401, detail=str(fout)) from fout


def vereiste_login(gebruiker: Gebruiker = Depends(haal_huidige_gebruiker)) -> Gebruiker:
    """FastAPI dependency: elke ingelogde gebruiker, ongeacht rol."""
    return gebruiker


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def haal_csrf_token(
    request: Request,
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> str:
    """FastAPI dependency: genereert een vers CSRF-token voor gebruik in GET-handlers."""
    return genereer_csrf_token(str(gebruiker.id))


def verifieer_csrf(
    request: Request,
    csrf_token: str = Form(None),
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> None:
    """FastAPI dependency: valideert het CSRF-token bij POST-handlers."""
    if not csrf_token or not verifieer_csrf_token(csrf_token, str(gebruiker.id)):
        logger.warning("CSRF-validatie mislukt voor gebruiker %s op %s", gebruiker.id, request.url.path)
        raise HTTPException(status_code=403, detail="Ongeldige of ontbrekende CSRF-token")


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------

def _actieve_admin_rollen(gebruiker: Gebruiker) -> set[str]:
    """Geeft de set van actieve administratieve rolnamen (GebruikerRol).

    Retourneert enkel: 'super_beheerder', 'beheerder', 'hr'.
    Planner- en teamlidrechten zitten in Lidmaatschap, niet hier.
    """
    return {
        r.rol.value if isinstance(r.rol, GebruikerRolType) else str(r.rol)
        for r in gebruiker.rollen
        if r.is_actief
    }


def _heeft_actief_planner_lidmaatschap(gebruiker: Gebruiker) -> bool:
    """True als de gebruiker minstens één actief planner-lidmaatschap heeft."""
    return any(
        lid.is_planner and lid.is_actief and lid.verwijderd_op is None
        for lid in gebruiker.lidmaatschappen
    )


def _haal_toegankelijke_locatie_ids(gebruiker: Gebruiker, db: Session) -> list[int]:
    """Alle locatie IDs waar deze gebruiker toegang toe heeft, op basis van rollen en lidmaatschappen."""
    from models.lidmaatschap import Lidmaatschap
    from models.locatie import Locatie
    from models.team import Team

    rollen = _actieve_admin_rollen(gebruiker)

    def _alle_actieve_locatie_ids() -> list[int]:
        return [
            r[0] for r in db.query(Locatie.id).filter(
                Locatie.is_actief == True,
                Locatie.verwijderd_op == None,
            ).all()
        ]

    if "super_beheerder" in rollen:
        return _alle_actieve_locatie_ids()

    locatie_ids: set[int] = set()

    for rol_obj in gebruiker.rollen:
        if not rol_obj.is_actief:
            continue
        rol_waarde = rol_obj.rol.value if isinstance(rol_obj.rol, GebruikerRolType) else str(rol_obj.rol)

        if rol_waarde == "beheerder" and rol_obj.scope_locatie_id:
            locatie_ids.add(rol_obj.scope_locatie_id)

        elif rol_waarde == "hr":
            if rol_obj.scope_area_id is None:
                # Nationaal HR — ziet alle locaties
                return _alle_actieve_locatie_ids()
            # Area HR — enkel locaties in die area
            area_locs = db.query(Locatie.id).filter(
                Locatie.area_id == rol_obj.scope_area_id,
                Locatie.is_actief == True,
                Locatie.verwijderd_op == None,
            ).all()
            locatie_ids.update(r[0] for r in area_locs)

    # Teamlid/planner — via actieve lidmaatschappen
    lid_locs = (
        db.query(Team.locatie_id)
        .join(Lidmaatschap, Lidmaatschap.team_id == Team.id)
        .filter(
            Lidmaatschap.gebruiker_id == gebruiker.id,
            Lidmaatschap.is_actief == True,
            Lidmaatschap.verwijderd_op == None,
            Team.is_actief == True,
            Team.verwijderd_op == None,
        )
        .distinct()
        .all()
    )
    locatie_ids.update(r[0] for r in lid_locs)

    return list(locatie_ids)


# ---------------------------------------------------------------------------
# Locatie-context (multi-locatie)
# ---------------------------------------------------------------------------

def haal_actieve_locatie_id(
    request: Request,
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
    db: Session = Depends(haal_db),
) -> int | None:
    """
    Geeft de actief geselecteerde locatie_id met server-side allow-list validatie.

    Afleiding per rol:
      teamlid/planner  → Lidmaatschap → Team → locatie_id
      beheerder        → GebruikerRol.scope_locatie_id
      hr (area)        → eerste locatie in GebruikerRol.scope_area_id
      hr (nationaal)   → cookie, alle locaties
      super_beheerder  → cookie, alle locaties

    Bij meerdere locaties kan de gebruiker schakelen via cookie 'locatie_context'.
    De cookie-waarde wordt gevalideerd tegen de server-side allow-list.
    """
    toegankelijke_ids = _haal_toegankelijke_locatie_ids(gebruiker, db)
    if not toegankelijke_ids:
        return None

    toegankelijke_set = set(toegankelijke_ids)
    cookie_val = request.cookies.get("locatie_context")
    if cookie_val:
        try:
            gewenste_id = int(cookie_val)
            if gewenste_id in toegankelijke_set:
                return gewenste_id
            logger.warning(
                "Gebruiker %s vroeg locatie_context=%s aan, maar heeft daar geen toegang toe.",
                gebruiker.id, gewenste_id,
            )
        except (ValueError, TypeError):
            pass

    return toegankelijke_ids[0]


def haal_beschikbare_locaties(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
    db: Session = Depends(haal_db),
) -> list[int]:
    """FastAPI dependency: alle locatie IDs toegankelijk voor de huidige gebruiker."""
    return _haal_toegankelijke_locatie_ids(gebruiker, db)


# ---------------------------------------------------------------------------
# Rol-checks (administratief niveau — GebruikerRol)
# ---------------------------------------------------------------------------

def vereiste_rol(*rollen: str):
    """
    FastAPI dependency factory: controleert of de ingelogde gebruiker
    minstens één van de opgegeven administratieve rollen heeft.
    Geldige waarden: 'super_beheerder', 'beheerder', 'hr'.
    Voor planner-checks, gebruik vereiste_planner_of_hoger().
    """
    def _controleer(gebruiker: Gebruiker = Depends(haal_huidige_gebruiker)) -> Gebruiker:
        if not _actieve_admin_rollen(gebruiker).intersection(rollen):
            raise HTTPException(status_code=403, detail="Onvoldoende rechten")
        return gebruiker
    return _controleer


def vereiste_super_beheerder(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: enkel super_beheerder."""
    if "super_beheerder" not in _actieve_admin_rollen(gebruiker):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_beheerder_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: beheerder of super_beheerder."""
    if not _actieve_admin_rollen(gebruiker).intersection({"beheerder", "super_beheerder"}):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_hr_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """FastAPI dependency: hr, beheerder of super_beheerder."""
    if not _actieve_admin_rollen(gebruiker).intersection({"hr", "beheerder", "super_beheerder"}):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker


def vereiste_planner_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """
    FastAPI dependency: planner (Lidmaatschap.is_planner=True), hr, beheerder of super_beheerder.

    'Planner' is geen administratieve rol meer — het is een eigenschap van een Lidmaatschap.
    """
    if _actieve_admin_rollen(gebruiker).intersection({"hr", "beheerder", "super_beheerder"}):
        return gebruiker
    if _heeft_actief_planner_lidmaatschap(gebruiker):
        return gebruiker
    raise HTTPException(status_code=403, detail="Onvoldoende rechten")


def vereiste_schrijfrechten(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
) -> Gebruiker:
    """
    FastAPI dependency: schrijfrechten voor operationele data.

    HR heeft enkel leesrechten op shifts en planning — zij mogen niet schrijven.
    Schrijfgerechtigden: super_beheerder, beheerder, planner.
    """
    rollen = _actieve_admin_rollen(gebruiker)
    if rollen.intersection({"super_beheerder", "beheerder"}):
        return gebruiker
    if _heeft_actief_planner_lidmaatschap(gebruiker):
        return gebruiker
    raise HTTPException(status_code=403, detail="Onvoldoende rechten — HR heeft enkel leesrechten")


# ---------------------------------------------------------------------------
# Scope-checks (helper-functies voor gebruik in services/routers)
# ---------------------------------------------------------------------------

def heeft_rol_in_team(
    gebruiker_id: int,
    team_id: int,
    rollen: tuple[str, ...],
    db: Session,
) -> bool:
    """
    Controleer of een gebruiker een van de opgegeven team-rollen heeft voor team_id.

    Args:
        gebruiker_id: De te controleren gebruiker.
        team_id: Het team waarvoor gecontroleerd wordt.
        rollen: Tuple van geaccepteerde rollen: 'teamlid' (elk actief lidmaatschap)
                of 'planner' (is_planner=True).
        db: Database sessie.

    Returns:
        True als een passend actief lidmaatschap gevonden wordt.
    """
    from models.lidmaatschap import Lidmaatschap

    basis_q = db.query(Lidmaatschap).filter(
        Lidmaatschap.gebruiker_id == gebruiker_id,
        Lidmaatschap.team_id == team_id,
        Lidmaatschap.is_actief == True,
        Lidmaatschap.verwijderd_op == None,
    )

    if "teamlid" in rollen:
        # Elk actief lidmaatschap kwalificeert als teamlid
        return basis_q.first() is not None

    if "planner" in rollen:
        return basis_q.filter(Lidmaatschap.is_planner == True).first() is not None

    return False


def heeft_rol_in_locatie(
    gebruiker_id: int,
    locatie_id: int,
    rollen: tuple[str, ...],
    db: Session,
) -> bool:
    """
    Controleer of een gebruiker een van de opgegeven administratieve rollen heeft voor locatie_id.

    Args:
        gebruiker_id: De te controleren gebruiker.
        locatie_id: De locatie waarvoor gecontroleerd wordt.
        rollen: Tuple van geaccepteerde rollen: 'beheerder', 'hr', 'super_beheerder'.
        db: Database sessie.

    Returns:
        True als een passende actieve GebruikerRol gevonden wordt.
    """
    if "super_beheerder" in rollen:
        if db.query(GebruikerRol).filter(
            GebruikerRol.gebruiker_id == gebruiker_id,
            GebruikerRol.rol == GebruikerRolType.super_beheerder,
            GebruikerRol.is_actief == True,
        ).first() is not None:
            return True

    if "beheerder" in rollen:
        if db.query(GebruikerRol).filter(
            GebruikerRol.gebruiker_id == gebruiker_id,
            GebruikerRol.rol == GebruikerRolType.beheerder,
            GebruikerRol.scope_locatie_id == locatie_id,
            GebruikerRol.is_actief == True,
        ).first() is not None:
            return True

    if "hr" in rollen:
        from models.locatie import Locatie

        locatie = db.query(Locatie).filter(Locatie.id == locatie_id).first()
        if locatie:
            for hr_rol in db.query(GebruikerRol).filter(
                GebruikerRol.gebruiker_id == gebruiker_id,
                GebruikerRol.rol == GebruikerRolType.hr,
                GebruikerRol.is_actief == True,
            ).all():
                if hr_rol.scope_area_id is None:
                    # Nationaal HR — ziet alle locaties
                    return True
                if locatie.area_id and hr_rol.scope_area_id == locatie.area_id:
                    return True

    return False


def heeft_rol_in_area(
    gebruiker_id: int,
    area_id: int,
    rollen: tuple[str, ...],
    db: Session,
) -> bool:
    """
    Controleer of een gebruiker een van de opgegeven rollen heeft voor area_id.

    Args:
        gebruiker_id: De te controleren gebruiker.
        area_id: De area waarvoor gecontroleerd wordt.
        rollen: Tuple van geaccepteerde rollen (enkel 'hr' is area-scopebaar).
        db: Database sessie.

    Returns:
        True als een passende actieve GebruikerRol gevonden wordt.
    """
    if "super_beheerder" in rollen:
        if db.query(GebruikerRol).filter(
            GebruikerRol.gebruiker_id == gebruiker_id,
            GebruikerRol.rol == GebruikerRolType.super_beheerder,
            GebruikerRol.is_actief == True,
        ).first() is not None:
            return True

    filtered_rollen = [r for r in rollen if r not in ("super_beheerder",)]
    if not filtered_rollen:
        return False

    return db.query(GebruikerRol).filter(
        GebruikerRol.gebruiker_id == gebruiker_id,
        GebruikerRol.scope_area_id == area_id,
        GebruikerRol.rol.in_(filtered_rollen),
        GebruikerRol.is_actief == True,
    ).first() is not None


def haal_primaire_team_id(gebruiker_id: int, db: Session) -> int | None:
    """
    Geeft het eerste actieve team-ID van een gebruiker via Lidmaatschap.
    Planners komen eerst (is_planner=True), daarna gewone teamleden.
    """
    from models.lidmaatschap import Lidmaatschap

    planner_lid = db.query(Lidmaatschap).filter(
        Lidmaatschap.gebruiker_id == gebruiker_id,
        Lidmaatschap.is_planner == True,
        Lidmaatschap.is_actief == True,
        Lidmaatschap.verwijderd_op == None,
    ).first()
    if planner_lid:
        return planner_lid.team_id

    lid = db.query(Lidmaatschap).filter(
        Lidmaatschap.gebruiker_id == gebruiker_id,
        Lidmaatschap.is_actief == True,
        Lidmaatschap.verwijderd_op == None,
    ).first()
    return lid.team_id if lid else None


def haal_planner_team_ids(gebruiker_id: int, db: Session) -> list[int]:
    """Geeft de team_ids waarvoor een gebruiker actief planner is."""
    from models.lidmaatschap import Lidmaatschap

    return [
        lid.team_id
        for lid in db.query(Lidmaatschap).filter(
            Lidmaatschap.gebruiker_id == gebruiker_id,
            Lidmaatschap.is_planner == True,
            Lidmaatschap.is_actief == True,
            Lidmaatschap.verwijderd_op == None,
        ).all()
    ]
