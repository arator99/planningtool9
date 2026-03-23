"""Models package — registreert alle ORM-modellen bij SQLAlchemy Basis."""
from models.area import Area  # noqa: F401
from models.locatie import Locatie  # noqa: F401
from models.team import Team, TeamConfig  # noqa: F401
from models.gebruiker_rol import GebruikerRol, GebruikerRolType  # noqa: F401
from models.gebruiker import Gebruiker  # noqa: F401
from models.lidmaatschap import Lidmaatschap, LidmaatschapType  # noqa: F401
from models.planning import (  # noqa: F401
    Werkpost, Shiftcode, ShiftTijd, SpecialCode,
    Planning, PlanningOverride, PlanningWijziging, RodeLijnConfig,
)
from models.verlof import VerlofAanvraag, VerlofTeamStatus  # noqa: F401
from models.verlof_saldo import VerlofSaldo, VerlofSaldoMutatie  # noqa: F401
from models.hr import NationaleHRRegel, LocatieHROverride  # noqa: F401
from models.notitie import Notitie  # noqa: F401
from models.competentie import Competentie, GebruikerCompetentie  # noqa: F401
from models.audit_log import AuditLog  # noqa: F401
from models.notificatie import Notificatie  # noqa: F401
from models.instelling import AppInstelling  # noqa: F401
from models.typetabel import Typetabel, TypetabelEntry  # noqa: F401
from models.adv import AdvToekenning  # noqa: F401
from models.scherm_recht import SchermRecht  # noqa: F401
from models.aankondiging import Aankondiging  # noqa: F401

__all__ = [
    "Area",
    "Locatie",
    "Team", "TeamConfig",
    "GebruikerRol", "GebruikerRolType",
    "Gebruiker",
    "Lidmaatschap", "LidmaatschapType",
    "Werkpost", "Shiftcode", "ShiftTijd", "SpecialCode",
    "Planning", "PlanningOverride", "PlanningWijziging", "RodeLijnConfig",
    "VerlofAanvraag", "VerlofTeamStatus",
    "VerlofSaldo", "VerlofSaldoMutatie",
    "NationaleHRRegel", "LocatieHROverride",
    "Notitie",
    "Competentie", "GebruikerCompetentie",
    "AuditLog",
    "Notificatie",
    "AppInstelling",
    "Typetabel", "TypetabelEntry",
    "AdvToekenning",
    "SchermRecht",
    "Aankondiging",
]
