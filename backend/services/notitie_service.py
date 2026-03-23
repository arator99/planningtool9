"""Notitie service — berichten via persoonlijke inbox of gedeelde rolmailbox."""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models.notitie import Notitie, MAILBOX_ROLLEN
from models.gebruiker_rol import GebruikerRol, GebruikerRolType
from models.lidmaatschap import Lidmaatschap
from services.domein.notitie_domein import valideer_bericht, valideer_prioriteit

logger = logging.getLogger(__name__)


class NotitieService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Versturen                                                            #
    # ------------------------------------------------------------------ #

    def stuur_naar_gebruiker(
        self,
        van_id: int,
        naar_gebruiker_id: int,
        locatie_id: int,
        bericht: str,
        prioriteit: str,
    ) -> Notitie:
        """Stuur een direct persoonlijk bericht aan een andere gebruiker."""
        valideer_bericht(bericht)
        valideer_prioriteit(prioriteit)
        notitie = Notitie(
            locatie_id=locatie_id,
            van_gebruiker_id=van_id,
            naar_gebruiker_id=naar_gebruiker_id,
            naar_rol=None,
            naar_scope_id=None,
            bericht=bericht.strip(),
            prioriteit=prioriteit,
        )
        self.db.add(notitie)
        self.db.commit()
        self.db.refresh(notitie)
        return notitie

    def stuur_naar_mailbox(
        self,
        van_id: int,
        naar_rol: str,
        naar_scope_id: int,
        locatie_id: int,
        bericht: str,
        prioriteit: str,
    ) -> Notitie:
        """Stuur een bericht naar een gedeelde rolmailbox."""
        valideer_bericht(bericht)
        valideer_prioriteit(prioriteit)
        if naar_rol not in MAILBOX_ROLLEN:
            raise ValueError(f"Ongeldige mailbox-rol: {naar_rol}")
        notitie = Notitie(
            locatie_id=locatie_id,
            van_gebruiker_id=van_id,
            naar_gebruiker_id=None,
            naar_rol=naar_rol,
            naar_scope_id=naar_scope_id,
            bericht=bericht.strip(),
            prioriteit=prioriteit,
        )
        self.db.add(notitie)
        self.db.commit()
        self.db.refresh(notitie)
        return notitie

    # ------------------------------------------------------------------ #
    # Lezen                                                                #
    # ------------------------------------------------------------------ #

    def haal_persoonlijke_inbox(self, gebruiker_id: int, locatie_id: int) -> list[Notitie]:
        """Directe berichten gericht aan deze gebruiker (naar_gebruiker_id)."""
        return (
            self.db.query(Notitie)
            .filter(
                Notitie.locatie_id == locatie_id,
                Notitie.naar_gebruiker_id == gebruiker_id,
                Notitie.verwijderd_op.is_(None),
            )
            .order_by(Notitie.aangemaakt_op.desc())
            .all()
        )

    def haal_mailbox(self, naar_rol: str, naar_scope_id: int) -> list[Notitie]:
        """Berichten voor een gedeelde rolmailbox."""
        return (
            self.db.query(Notitie)
            .filter(
                Notitie.naar_rol == naar_rol,
                Notitie.naar_scope_id == naar_scope_id,
                Notitie.verwijderd_op.is_(None),
            )
            .order_by(Notitie.aangemaakt_op.desc())
            .all()
        )

    def _haal_alle_super_beheerder_mailbox(self) -> list[Notitie]:
        """Alle berichten gericht aan super_beheerders (geen scope-filter)."""
        return (
            self.db.query(Notitie)
            .filter(
                Notitie.naar_rol == "super_beheerders",
                Notitie.verwijderd_op.is_(None),
            )
            .order_by(Notitie.aangemaakt_op.desc())
            .all()
        )

    def haal_alle_inboxen(
        self,
        gebruiker_id: int,
        rollen: list[GebruikerRol],
        locatie_id: int,
    ) -> dict:
        """
        Bouwt een overzicht van alle inboxen voor een gebruiker:
          - persoonlijk: directe berichten
          - mailboxen: lijst van gedeelde mailboxen op basis van GebruikerRol records

        Returns:
            {
              'persoonlijk': [Notitie, ...],
              'mailboxen': [
                {'label': str, 'rol': str, 'scope_id': int, 'notities': [Notitie, ...]},
                ...
              ]
            }
        """
        persoonlijk = self.haal_persoonlijke_inbox(gebruiker_id, locatie_id)

        mailboxen = []

        # Planner mailboxen via actieve Lidmaatschap.is_planner
        planner_leden = (
            self.db.query(Lidmaatschap)
            .filter(
                Lidmaatschap.gebruiker_id == gebruiker_id,
                Lidmaatschap.is_planner == True,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
            .all()
        )
        for lid in planner_leden:
            notities = self.haal_mailbox("planners", lid.team_id)
            mailboxen.append({
                "label": f"planners:{lid.team_id}",
                "rol": "planners",
                "scope_id": lid.team_id,
                "notities": notities,
            })

        # Admin-rollen via GebruikerRol (beheerder / super_beheerder)
        for rol_record in rollen:
            if not rol_record.is_actief:
                continue
            rol_waarde = rol_record.rol.value if isinstance(rol_record.rol, GebruikerRolType) else str(rol_record.rol)
            if rol_waarde == "beheerder":
                scope = rol_record.scope_locatie_id
                notities = self.haal_mailbox("beheerders", scope)
                mailboxen.append({
                    "label": f"beheerders:{scope}",
                    "rol": "beheerders",
                    "scope_id": scope,
                    "notities": notities,
                })
            elif rol_waarde == "super_beheerder":
                notities = self._haal_alle_super_beheerder_mailbox()
                mailboxen.append({
                    "label": "super_beheerders",
                    "rol": "super_beheerders",
                    "scope_id": None,
                    "notities": notities,
                })

        return {"persoonlijk": persoonlijk, "mailboxen": mailboxen}

    def haal_ongelezen_totaal(
        self,
        gebruiker_id: int,
        rollen: list[GebruikerRol],
        locatie_id: int | None,
    ) -> int:
        """Totaal aantal ongelezen berichten over alle inboxen."""
        # Persoonlijke ongelezen
        persoonlijk_count = (
            self.db.query(Notitie)
            .filter(
                Notitie.locatie_id == locatie_id,
                Notitie.naar_gebruiker_id == gebruiker_id,
                Notitie.is_gelezen == False,
                Notitie.verwijderd_op.is_(None),
            )
            .count()
        )

        mailbox_count = 0
        seen_mailboxen: set[tuple] = set()

        # Planner mailboxen
        planner_leden = (
            self.db.query(Lidmaatschap)
            .filter(
                Lidmaatschap.gebruiker_id == gebruiker_id,
                Lidmaatschap.is_planner == True,
                Lidmaatschap.is_actief == True,
                Lidmaatschap.verwijderd_op == None,
            )
            .all()
        )
        for lid in planner_leden:
            key = ("planners", lid.team_id)
            if key not in seen_mailboxen:
                seen_mailboxen.add(key)
                mailbox_count += (
                    self.db.query(Notitie)
                    .filter(
                        Notitie.naar_rol == "planners",
                        Notitie.naar_scope_id == lid.team_id,
                        Notitie.is_gelezen == False,
                        Notitie.verwijderd_op.is_(None),
                    )
                    .count()
                )

        # Admin-rollen
        for rol_record in rollen:
            if not rol_record.is_actief:
                continue
            rol_waarde = rol_record.rol.value if isinstance(rol_record.rol, GebruikerRolType) else str(rol_record.rol)
            if rol_waarde == "beheerder":
                scope = rol_record.scope_locatie_id
                key = ("beheerders", scope)
                if key not in seen_mailboxen:
                    seen_mailboxen.add(key)
                    mailbox_count += (
                        self.db.query(Notitie)
                        .filter(
                            Notitie.naar_rol == "beheerders",
                            Notitie.naar_scope_id == scope,
                            Notitie.is_gelezen == False,
                            Notitie.verwijderd_op.is_(None),
                        )
                        .count()
                    )
            elif rol_waarde == "super_beheerder":
                key = ("super_beheerders", None)
                if key not in seen_mailboxen:
                    seen_mailboxen.add(key)
                    mailbox_count += (
                        self.db.query(Notitie)
                        .filter(
                            Notitie.naar_rol == "super_beheerders",
                            Notitie.is_gelezen == False,
                            Notitie.verwijderd_op.is_(None),
                        )
                        .count()
                    )

        return persoonlijk_count + mailbox_count

    def haal_verzonden(self, gebruiker_id: int, locatie_id: int) -> list[Notitie]:
        """Alle berichten verstuurd door deze gebruiker op de locatie."""
        return (
            self.db.query(Notitie)
            .filter(
                Notitie.van_gebruiker_id == gebruiker_id,
                Notitie.locatie_id == locatie_id,
                Notitie.verwijderd_op.is_(None),
            )
            .order_by(Notitie.aangemaakt_op.desc())
            .all()
        )

    def haal_op_uuid(self, uuid: str) -> Notitie:
        """Zoek een notitie op extern uuid. Gooit ValueError als niet gevonden."""
        obj = self.db.query(Notitie).filter(Notitie.uuid == uuid).first()
        if not obj:
            raise ValueError(f"Notitie niet gevonden: {uuid}")
        return obj

    # ------------------------------------------------------------------ #
    # Markeer gelezen                                                      #
    # ------------------------------------------------------------------ #

    def markeer_gelezen(self, notitie_uuid: str, gebruiker_id: int) -> None:
        """Markeer een specifieke notitie als gelezen (alleen eigen of mailbox-berichten)."""
        n = self.db.query(Notitie).filter(Notitie.uuid == notitie_uuid).first()
        if n and not n.is_gelezen:
            n.is_gelezen = True
            n.gelezen_op = datetime.now()
            self.db.commit()

    def markeer_alles_gelezen(self, gebruiker_id: int, locatie_id: int) -> None:
        """Markeer alle persoonlijke berichten van de gebruiker als gelezen."""
        notities = (
            self.db.query(Notitie)
            .filter(
                Notitie.locatie_id == locatie_id,
                Notitie.naar_gebruiker_id == gebruiker_id,
                Notitie.is_gelezen == False,
                Notitie.verwijderd_op.is_(None),
            )
            .all()
        )
        for n in notities:
            n.is_gelezen = True
            n.gelezen_op = datetime.now()
        self.db.commit()

    def markeer_mailbox_alles_gelezen(
        self, naar_rol: str, naar_scope_id: int
    ) -> None:
        """Markeer alle berichten in een rolmailbox als gelezen."""
        notities = (
            self.db.query(Notitie)
            .filter(
                Notitie.naar_rol == naar_rol,
                Notitie.naar_scope_id == naar_scope_id,
                Notitie.is_gelezen == False,
                Notitie.verwijderd_op.is_(None),
            )
            .all()
        )
        for n in notities:
            n.is_gelezen = True
            n.gelezen_op = datetime.now()
        self.db.commit()

    # ------------------------------------------------------------------ #
    # Verwijderen (soft delete)                                            #
    # ------------------------------------------------------------------ #

    def verwijder(self, notitie_uuid: str, van_id: int) -> None:
        """Soft delete van een verstuurde notitie (alleen door de afzender)."""
        n = self.db.query(Notitie).filter(
            Notitie.uuid == notitie_uuid,
            Notitie.van_gebruiker_id == van_id,
        ).first()
        if not n:
            raise ValueError("Notitie niet gevonden of geen toegang.")
        n.verwijderd_op = datetime.now()
        n.verwijderd_door_id = van_id
        self.db.commit()
