# Configuratie Referentie

**Versie:** 0.7.x
**Laatst bijgewerkt:** 2026-03-01
**Doel:** Complete referentie van systeem configuratie, paden, sessie management en constanten

---

## 📋 Inhoudsopgave

1. [Introductie](#introductie)
2. [Config Klasse](#config-klasse)
3. [Sessie Management](#sessie-management)
4. [Database Configuratie](#database-configuratie)
5. [Logging Configuratie](#logging-configuratie)
6. [Environment Setup](#environment-setup)
7. [Constanten & Enums](#constanten--enums)

---

## Introductie

### Configuratie Principes

**GEEN hardcoded paden** - alles via `Config` klasse:

```python
# ❌ VERBODEN
db_path = "C:\\Users\\...\\data\\database.db"

# ✅ CORRECT
from src.kern.config import Config
db_path = Config.DB_PATH
```

**Cross-platform compatibiliteit:**
- Gebruik `pathlib.Path` voor paden
- Forward slashes automatisch gegarandeerd
- Werkt op Windows, Mac, Linux

---

## Config Klasse

**Locatie:** `src/kern/config.py`

### Klasse Definitie

```python
class Config:
    """
    Centrale configuratie voor de applicatie.
    Alle constanten zijn Final (immutable).
    """
```

**KRITIEK:** Alle attributen zijn `Final` - **kan niet gewijzigd worden** na definitie.

---

### Project Informatie

```python
# Project metadata
APP_NAAM: Final[str] = "Planningtool"
APP_VERSIE: Final[str] = "0.7.1"
```

**Gebruik:**
```python
from src.kern.config import Config

print(f"{Config.APP_NAAM} v{Config.APP_VERSIE}")
# => "Planningtool v0.7.1"
```

---

### Paden (Paths)

#### Basis Paden

```python
BASE_DIR: Final[Path]      # Project root directory
DATA_DIR: Final[Path]       # data/
DB_PATH: Final[Path]        # data/database.db
LOG_DIR: Final[Path]        # logs/
LOG_FILE: Final[Path]       # logs/applicatie.log
```

**Structuur:**
```
C:\Users\arato\PycharmProjects\Planningtool7\  (BASE_DIR)
├── data\                                        (DATA_DIR)
│   └── database.db                              (DB_PATH)
├── logs\                                        (LOG_DIR)
│   └── applicatie.log                           (LOG_FILE)
└── src\
    └── ...
```

---

#### UI Paden

```python
BRONNEN_DIR: Final[Path]    # src/bronnen/
ICON_PATH: Final[Path]      # src/bronnen/icons/
```

**Gebruik:**
```python
from src.kern.config import Config

# Laad logo
logo_path = Config.BRONNEN_DIR / "afbeeldingen" / "icon.ico"
if logo_path.exists():
    pixmap = QPixmap(str(logo_path))

# Laad icoon
icoon_path = Config.ICON_PATH / "user.png"
```

---

#### Database URI

```python
DB_URI: Final[str]  # Forward slash garantie voor SQLite
```

**Gebruik:**
```python
# SQLite connection string (cross-platform)
db_uri = Config.DB_URI
# => "C:/Users/arato/PycharmProjects/Planningtool7/data/database.db"
```

**KRITIEK:** Forward slashes (`/`) ook op Windows - SQLite vereist dit.

---

### Methods

#### `initialiseer_mappen()`

```python
@classmethod
def initialiseer_mappen(cls) -> None:
    """
    Zorgt ervoor dat benodigde mappenstructuur bestaat.
    Wordt automatisch aangeroepen bij import.
    """
    cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
```

**Effect:**
- Creëert `data/` en `logs/` directories indien niet bestaand
- Geen error als al bestaat (`exist_ok=True`)
- **Automatisch** uitgevoerd bij `import Config`

---

### Volledige Gebruik Voorbeelden

#### Database Pad

```python
from src.kern.config import Config
import sqlite3

# Open database
conn = sqlite3.connect(Config.DB_PATH)

# Of via context manager (preferred)
from src.kern.database import get_db

with get_db() as conn:
    cursor = conn.execute("SELECT * FROM gebruikers")
```

---

#### Logging Setup

```python
from src.kern.config import Config
import logging

# Setup file logger
logging.basicConfig(
    filename=Config.LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info(f"Applicatie gestart: {Config.APP_NAAM} v{Config.APP_VERSIE}")
```

---

#### Bestand Operaties

```python
from src.kern.config import Config

# Lees configuratie bestand
config_file = Config.DATA_DIR / "settings.json"
if config_file.exists():
    with open(config_file, 'r') as f:
        settings = json.load(f)

# Schrijf export bestand
export_file = Config.DATA_DIR / "exports" / "planning_2026_01.xlsx"
export_file.parent.mkdir(exist_ok=True)  # Creëer exports/ directory
save_to_excel(export_file)
```

---

## Sessie Management

**Locatie:** `src/kern/sessie.py`

### Sessie Klasse

```python
class Sessie:
    """
    Singleton klasse voor sessie management.
    Houdt bij welke gebruiker is ingelogd.
    """
```

**Pattern:** Singleton - **één instantie** voor hele applicatie.

---

### Methods

#### `login()`

```python
@classmethod
def login(cls, gebruiker_data: Dict[str, Any]) -> None:
    """
    Zet gebruiker als ingelogd.

    Args:
        gebruiker_data: Dict met gebruiker info
            - id: int
            - gebruikersnaam: str
            - volledige_naam: str
            - rol: str
            - (optioneel) andere velden
    """
```

**Gebruik:**
```python
from src.kern.sessie import Sessie

# Login na succesvolle authenticatie
sessie_data = {
    'id': 1,
    'gebruikersnaam': 'jan.peeters',
    'volledige_naam': 'Peeters Jan',
    'rol': 'planner'
}
Sessie.login(sessie_data)
```

**Effect:**
- Slaat gebruiker data op in singleton instance
- Voegt `login_tijd` timestamp toe automatisch

---

#### `logout()`

```python
@classmethod
def logout(cls) -> None:
    """Logt huidige gebruiker uit."""
```

**Gebruik:**
```python
from src.kern.sessie import Sessie

# Bij uitloggen
Sessie.logout()
```

**Effect:** Wist alle gebruiker data uit sessie.

---

#### `is_ingelogd()`

```python
@classmethod
def is_ingelogd(cls) -> bool:
    """Check of er een gebruiker is ingelogd."""
```

**Gebruik:**
```python
from src.kern.sessie import Sessie

if not Sessie.is_ingelogd():
    # Redirect naar login scherm
    main_window.navigeer_naar("login")
```

---

#### Getters (Nederlands + Engels)

De Sessie klasse biedt zowel Nederlandstalige als Engelstalige methodes. **Voorkeur:** Gebruik de Nederlandse variant.

```python
# Nederlandstalige methodes (VOORKEUR)
@classmethod
def haal_gebruiker_id(cls) -> Optional[int]:
    """Retourneert ID van ingelogde gebruiker."""

@classmethod
def haal_rol(cls) -> Optional[str]:
    """Retourneert rol ('teamlid', 'planner', 'beheerder', 'admin')."""

@classmethod
def haal_volledige_naam(cls) -> Optional[str]:
    """Retourneert volledige naam."""

# Engelstalige aliases (backwards compatibiliteit)
get_gebruiker_id = haal_gebruiker_id
get_rol = haal_rol
get_volledige_naam = haal_volledige_naam

@classmethod
def get_gebruikersnaam(cls) -> Optional[str]:
    """Retourneert gebruikersnaam."""

@classmethod
def get_alle_data(cls) -> Optional[Dict[str, Any]]:
    """Retourneert COPY van alle gebruiker data."""
```

**Gebruik:**
```python
from src.kern.sessie import Sessie

# Haal huidige gebruiker info (Nederlands - voorkeur)
gebruiker_id = Sessie.haal_gebruiker_id()
rol = Sessie.haal_rol()
naam = Sessie.haal_volledige_naam()

# Check rol
if Sessie.haal_rol() in ['admin', 'beheerder']:
    # Admin functionaliteit
    pass

# Engels werkt ook (backwards compatible)
gebruiker_id = Sessie.get_gebruiker_id()

# Haal alle data (voor logging, etc.)
data = Sessie.get_alle_data()
logger.info(f"Gebruiker {data['gebruikersnaam']} ingelogd om {data['login_tijd']}")
```

**KRITIEK:** `get_alle_data()` retourneert een **COPY** - wijzigingen aan dict hebben geen effect op sessie.

---

### Sessie Flow

**Complete login/logout flow:**

```python
from src.kern.sessie import Sessie
from src.services.applicatie.authenticatie_service import AuthenticatieService

# 1. Login
succes, fout, sessie_data = AuthenticatieService.login(
    gebruikersnaam="jan.peeters",
    wachtwoord="geheim123"
)

if succes:
    # Sessie wordt automatisch gestart in AuthenticatieService
    print(f"Welkom {Sessie.get_volledige_naam()}!")

    # Check rol
    if Sessie.get_rol() == 'admin':
        print("Je hebt admin rechten")

# 2. Gebruik sessie tijdens applicatie
if Sessie.is_ingelogd():
    gebruiker_id = Sessie.get_gebruiker_id()
    # Gebruik gebruiker_id voor queries, logging, etc.

# 3. Logout
Sessie.logout()
```

---

## Database Configuratie

### Database Context Manager

**Locatie:** `src/kern/database.py`

#### `get_db()`

```python
@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager voor database connecties.

    Yields:
        sqlite3.Connection met row_factory = Row

    Raises:
        Exception: Bij database fouten
    """
```

**Gebruik:**
```python
from src.kern.database import get_db

# Altijd via context manager
with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gebruikers WHERE id = ?", (1,))
    row = cursor.fetchone()

    # Row factory geeft Dict-achtige toegang
    print(row['gebruikersnaam'])
    print(row['rol'])

# Connectie wordt automatisch gesloten
```

**KRITIEK:**
- **NOOIT** rechtstreeks `sqlite3.connect()` gebruiken
- **ALTIJD** via `get_db()` context manager
- Row factory = `sqlite3.Row` (dict-achtige toegang)

---

### Database Initialisatie

**Bij applicatie startup:**

```python
from src.kern.config import Config
from src.kern.migratie import Migratie

# 1. Controleer/creëer database structuur
Migratie.voer_alle_migraties_uit()

# Database is nu klaar voor gebruik
```

**Migratie systeem:**
- `v0.6.x_basis.sql` - Basis tabellen (gebruikers, planning, etc.)
- `v0.7.8_hr_regels.sql` - HR-validatie tabellen
- Automatisch uitgevoerd bij eerste start
- Idempotent (kan veilig meerdere keren uitgevoerd worden)

---

## Logging Configuratie

### Logging Setup

**Locatie:** Typisch in `main.py` of applicatie startup.

```python
import logging
from src.kern.config import Config

def setup_logging():
    """Setup applicatie-breed logging."""
    # Formaat
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler
    file_handler = logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # Console handler (voor development)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# Bij startup
setup_logging()
logger = logging.getLogger(__name__)
logger.info(f"Applicatie gestart: {Config.APP_NAAM} v{Config.APP_VERSIE}")
```

---

### Logger Gebruik

**In modules:**

```python
import logging

logger = logging.getLogger(__name__)

# Log levels
logger.debug("Debug info (zeer gedetailleerd)")
logger.info("Normale operatie info")
logger.warning("Waarschuwing (kan probleem worden)")
logger.error("Fout (functionaliteit werkt niet)", exc_info=True)
logger.critical("Kritieke fout (applicatie crash)")
```

**Voorbeeld:**

```python
# In service
logger = logging.getLogger(__name__)

def haal_gebruiker(gebruiker_id: int):
    try:
        logger.debug(f"Haal gebruiker op: ID {gebruiker_id}")
        row = GebruikerRepo.haal_gebruiker_op_id(gebruiker_id)

        if not row:
            logger.warning(f"Gebruiker niet gevonden: ID {gebruiker_id}")
            return None

        logger.info(f"Gebruiker opgehaald: {row['gebruikersnaam']}")
        return Gebruiker.van_database_row(row)

    except Exception as e:
        logger.error(f"Fout bij ophalen gebruiker {gebruiker_id}: {e}", exc_info=True)
        raise
```

**KRITIEK:** Gebruik `exc_info=True` bij error logging voor full stack trace.

---

## Environment Setup

### Vereiste Dependencies

**Locatie:** `requirements.txt`

```txt
PyQt6==6.7.1
bcrypt==4.2.1
pytest==8.3.4
```

**Installatie:**
```bash
pip install -r requirements.txt
```

---

### Python Versie

**Minimum:** Python 3.10+

**Check versie:**
```bash
python --version
# => Python 3.10.x of hoger
```

---

### Project Structuur

```
Planningtool7/
├── data/                       # Database & data files
│   ├── database.db
│   └── migraties/
│       ├── v0.6.x_basis.sql
│       └── v0.7.8_hr_regels.sql
├── logs/                       # Log files
│   └── applicatie.log
├── src/
│   ├── bronnen/               # Resources (images, icons)
│   ├── gui/                   # GUI laag
│   ├── kern/                  # Core (config, database, sessie)
│   └── services/              # Business logic
│       ├── applicatie/        # Application services
│       ├── domein/            # Domain logic
│       └── repo/              # Data access
├── tests/                     # Unit tests
├── docs/                      # Documentatie
│   ├── plannen/              # Implementation plans
│   └── referentie/           # Reference docs (dit document)
├── requirements.txt
└── main.py                    # Entry point
```

---

### Startup Sequence

**Bij applicatie start:**

1. **Import Config** → Mappen gecreëerd (`data/`, `logs/`)
2. **Setup Logging** → Log naar `logs/applicatie.log`
3. **Database Migratie** → Controleer/creëer database structuur
4. **Start GUI** → PyQt6 applicatie
5. **Toon Login** → Authenticatie

**Code:**
```python
# main.py
from src.kern.config import Config
from src.kern.migratie import Migratie
import logging

def main():
    # 1. Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info(f"Start {Config.APP_NAAM} v{Config.APP_VERSIE}")

    # 2. Database migratie
    try:
        Migratie.voer_alle_migraties_uit()
        logger.info("Database migratie compleet")
    except Exception as e:
        logger.critical(f"Database migratie gefaald: {e}", exc_info=True)
        sys.exit(1)

    # 3. Start GUI
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

---

## Constanten & Enums

### Theme Enum

**Locatie:** `src/gui/stijlen.py`

```python
from enum import Enum

class Theme(str, Enum):
    LIGHT = 'light'
    DARK = 'dark'
```

**Gebruik:**
```python
from src.gui.stijlen import Theme, Stijlen

# Switch theme
Stijlen.set_theme(Theme.DARK)

# Check current theme
if Stijlen.current_theme == Theme.LIGHT:
    # Light mode logica
```

---

### Rol Constanten

**In domein:** `src/services/domein/rol_domein.py`

```python
# Geldige rollen (hardcoded in domein)
ROLLEN = ['teamlid', 'planner', 'beheerder', 'admin']
```

**Gebruik:**
```python
from src.services.domein import rol_domein

# Valideer rol
if rol_domein.is_geldige_rol('planner'):
    # Toegestaan
```

---

### Prioriteit Constanten

**Voor notities:** `['laag', 'normaal', 'hoog']`

**Voor HR-validatie:** `['INFO', 'WARNING', 'CRITICAL']`

```python
# Notitie prioriteit
notitie = Notitie(
    prioriteit='hoog',  # laag, normaal, hoog
    # ...
)

# HR-validatie ernst
overtreding = RegelOvertreding(
    ernst='CRITICAL',  # INFO, WARNING, CRITICAL
    # ...
)
```

---

### Status Constanten

**Planning status:** `['concept', 'gepubliceerd']`

**Verlof status:** `['pending', 'goedgekeurd', 'geweigerd']`

```python
# Planning
shift = PlanningShift(
    status='concept',  # concept, gepubliceerd
    # ...
)

# Verlof
aanvraag = VerlofAanvraag(
    status='pending',  # pending, goedgekeurd, geweigerd
    # ...
)
```

**Let op:** De database heeft een CHECK constraint: `status IN ('pending', 'goedgekeurd', 'geweigerd')`

---

## Best Practices

### 1. Gebruik Config Voor Alle Paden

```python
# ❌ VERBODEN
with open("data/database.db", 'r') as f:
    data = f.read()

# ✅ CORRECT
from src.kern.config import Config

with open(Config.DB_PATH, 'r') as f:
    data = f.read()
```

---

### 2. Check Sessie Voor Protected Actions

```python
from src.kern.sessie import Sessie

def beschermde_actie():
    # Check login status
    if not Sessie.is_ingelogd():
        raise PermissionError("Niet ingelogd")

    # Check rol
    if Sessie.get_rol() not in ['admin', 'beheerder']:
        raise PermissionError("Onvoldoende rechten")

    # Voer actie uit
    gebruiker_id = Sessie.get_gebruiker_id()
    # ...
```

---

### 3. Logging Best Practices

```python
import logging

logger = logging.getLogger(__name__)

# Debug (development only)
logger.debug(f"Query params: {params}")

# Info (normale operaties)
logger.info(f"Gebruiker {gebruiker_id} aangemaakt")

# Warning (potentieel probleem)
logger.warning(f"Database query duurde {duration}s (>1s)")

# Error (met stack trace)
try:
    dangerous_operation()
except Exception as e:
    logger.error(f"Operatie gefaald: {e}", exc_info=True)
    raise

# Critical (applicatie crash)
logger.critical("Database connectie verloren - shutdown")
```

---

### 4. Environment-Specific Config

**Voor verschillende environments (dev, test, prod):**

```python
# src/kern/config.py
import os

class Config:
    # Default (development)
    DEBUG = True
    LOG_LEVEL = "DEBUG"

    # Override via environment variabele
    if os.getenv("ENV") == "production":
        DEBUG = False
        LOG_LEVEL = "INFO"
        DB_PATH = Path("/var/lib/planningtool/database.db")
```

**Gebruik:**
```bash
# Development
python main.py

# Production
ENV=production python main.py
```

---

## Zie Ook

- [Database Schema Referentie](./database_schema.md) - Database structuur
- [Domein Objecten Referentie](./domein_objecten.md) - Business logic
- [Services API Referentie](./services_api.md) - Service methodes
- [GUI Components Referentie](./gui_components.md) - UI componenten
- [Development Guide](../development_guide.md) - Development workflow

---

**Einde Configuratie Referentie**
