# Master Blueprint: Planning Tool v0.8 — Web Architectuur
Gebaseerd op de lessen uit v0.7 (PyQt6/SQLite) en de transitie naar een gehoste webapplicatie.

---

## 0. Filosofie & Kernprincipes

De overgang van v0.7 naar v0.8 is geen herschrijf, maar een **platformwissel**. De bewezen architectuurprincipes blijven behouden:

- **Strikte laagscheiding** — UI (frontend) praat nooit rechtstreeks met de database.
- **Services als motor** — Alle business logica zit in de service-laag, ongewijzigd qua structuur.
- **Zero Direct DB calls in UI** — In v0.7 gold dit voor PyQt6-schermen; in v0.8 geldt dit voor de frontend én voor de FastAPI routers.
- **Testen vóór UI** — Services worden unittest-getest onafhankelijk van routes of frontend.

Nieuw in v0.8:

- **Stateless backend** — De API-server bewaart geen sessiedata in geheugen. Alles loopt via JWT-tokens + database.
- **Multi-tenant bewustzijn** — Drie planningsgroepen (voorheen drie aparte SQLite-databases) draaien nu in één PostgreSQL-database met duidelijke scheiding via `group_id`.
- **Security by design** — 2FA/TOTP, HTTPS-only, password hashing, en rolgebaseerde toegang zijn geen afterthought maar zitten ingebakken van dag één.

---

## 1. Systeemoverzicht & Deployment (Docker op NAS)

De volledige applicatie draait als een set Docker containers, beheerd via `docker-compose`.

```
NAS
└── docker-compose.yml
    ├── service: app          (FastAPI backend — Python)
    ├── service: frontend     (Nginx — serveert de webpagina's)
    ├── service: db           (PostgreSQL)
    └── service: redis        (optioneel: sessie-blacklist / rate limiting)
```

### Aanbevolen mapstructuur (repository root)

```
planning-tool-v08/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── api/
│   │   ├── routers/          ← FastAPI routers (één per domein)
│   │   └── dependencies.py   ← Gedeelde dependencies (auth, db session)
│   ├── services/             ← Zelfde structuur als v0.7
│   ├── models/               ← SQLAlchemy ORM modellen
│   ├── schemas/              ← Pydantic schemas (request/response)
│   └── tests/
├── frontend/
│   ├── templates/            ← Jinja2 HTML (zie sectie 4)
│   ├── static/               ← CSS, JS, afbeeldingen
│   └── nginx.conf
├── migrations/               ← Alembic migratiescripts
├── docker-compose.yml
├── docker-compose.prod.yml
└── .env.example
```

### `docker-compose.yml` (basisstructuur)

```yaml
services:
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
    env_file: .env

  app:
    build: ./backend
    depends_on:
      - db
    env_file: .env
    ports:
      - "8000:8000"

  frontend:
    build: ./frontend
    depends_on:
      - app
    ports:
      - "80:80"
      - "443:443"

volumes:
  pgdata:
```

**Aanbeveling NAS-specifiek:** Gebruik een **reverse proxy** (bijv. Nginx Proxy Manager of Traefik als extra container) voor HTTPS-terminatie via Let's Encrypt, ook binnen een lokaal netwerk via een intern domein.

---

## 2. API Architectuur (FastAPI Routers)

### Principe: één router per domein

Elke planningsdomeein krijgt zijn eigen router-bestand. De router is dun — hij valideert de input via Pydantic en delegeert meteen naar de service-laag.

```
api/routers/
├── auth.py          ← login, logout, token refresh, TOTP setup/verify
├── users.py         ← gebruikersbeheer (beheerder)
├── planning.py      ← shifts, roosters, kalender
├── leaves.py        ← verlofaanvragen en -goedkeuring
├── hr_export.py     ← HR-exports (voorheen Excel naar SharePoint)
├── shift_codes.py   ← shiftcode beheer
└── admin.py         ← systeembeheer, groepsbeheer
```

### Router template (kopieerklaar)

```python
# api/routers/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.dependencies import get_db, require_role
from schemas.user import UserCreate, UserResponse
from services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("beheerder", "planner")),
):
    return UserService(db).get_all_users()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("beheerder")),
):
    return UserService(db).create_user(data)
```

### Dependencies (`api/dependencies.py`)

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import SessionLocal
from services.auth_service import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    return AuthService(db).verify_token(token)


def require_role(*roles: str):
    def checker(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Onvoldoende rechten")
        return current_user
    return checker
```

### Pydantic schema's (request/response scheiding)

```python
# schemas/user.py
from pydantic import BaseModel, EmailStr
from enum import Enum

class UserRole(str, Enum):
    beheerder = "beheerder"   # Volledige toegang
    planner = "planner"
    hr = "hr"
    gebruiker = "gebruiker"   # Gewone medewerker — consistent met v0.7

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    role: UserRole
    group_id: int

class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    group_id: int
    totp_enabled: bool

    class Config:
        from_attributes = True
```

> **Naamgeving — definitieve keuze voor v0.8:** In v0.7 werden `'werknemer'`, `'gebruiker'` en `'medewerker'` door elkaar gebruikt voor de basisrol. In v0.8 is `beheerder` en `gebruiker` de enige correcte term in code en database. `Medewerker` mag als leesbare UI-tekst, maar nooit als rolwaarde in de database.

---

## 3. Authenticatie & TOTP/2FA

### Login flow (stap voor stap)

```
1. Gebruiker POST /auth/token  →  { username, password }
2. Server verifieert wachtwoord (bcrypt)
3. Als TOTP actief:
     → Server returnt { status: "totp_required", temp_token: "..." }
4. Gebruiker POST /auth/totp/verify  →  { temp_token, totp_code }
5. Server verifieert TOTP-code (pyotp)
6. Server returnt { access_token, refresh_token }
7. Frontend bewaart tokens (httpOnly cookie, NOOIT in localStorage)
```

### AuthService structuur

```python
# services/auth_service.py
import pyotp
import qrcode
from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

class AuthService:
    def __init__(self, db):
        self.db = db
        self.pwd_context = CryptContext(schemes=["bcrypt"])

    def login(self, username: str, password: str) -> dict:
        user = self._get_user(username)
        if not user or not self.pwd_context.verify(password, user.hashed_password):
            raise InvalidCredentialsError()
        if user.totp_enabled:
            return {"status": "totp_required", "temp_token": self._create_temp_token(user)}
        return self._create_token_pair(user)

    def verify_totp(self, temp_token: str, code: str) -> dict:
        user_id = self._decode_temp_token(temp_token)
        user = self._get_user_by_id(user_id)
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code, valid_window=1):
            raise InvalidTOTPError()
        return self._create_token_pair(user)

    def setup_totp(self, user_id: int) -> dict:
        secret = pyotp.random_base32()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name="Planning Tool"
        )
        # Sla secret op (nog NIET totp_enabled=True — pas na eerste verificatie)
        return {"secret": secret, "qr_uri": uri}

    def confirm_totp_setup(self, user_id: int, code: str):
        # Verificeer en zet totp_enabled=True
        ...
```

### JWT Token strategie

```python
# config.py
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
TEMP_TOKEN_EXPIRE_MINUTES = 5   # Voor TOTP-tussenstap
SECRET_KEY = "..."               # Uit .env, nooit hardcoded
ALGORITHM = "HS256"
```

### Rollen & rechten overzicht

| Rol        | Toegang                                                                 |
|------------|-------------------------------------------------------------------------|
| `beheerder`   | Alles — gebruikersbeheer, alle groepen, systeemconfiguratie             |
| `planner`  | Eigen groep — roosters aanmaken/wijzigen, verlof goed-/afkeuren         |
| `hr`       | Alle groepen — read-only kalender, HR-exports downloaden                |
| `gebruiker`   | Eigen rooster bekijken, verlof aanvragen                                |

---

## 4. Frontend / GUI Aanpak

### Aanbeveling: HTMX + Jinja2 templates

Voor een interne bedrijfsapplicatie is **HTMX + Jinja2** de meest pragmatische keuze:

- **Geen apart frontend-project** — De FastAPI backend serveert de HTML-pagina's zelf.
- **Geen complexe build-pipeline** — Geen Node.js, webpack, of npm nodig.
- **Dynamische interactie zonder full-page reloads** — HTMX laat je tabel-rijen verversen, formulieren submitten, en kalenders updaten via kleine HTTP-requests, met gewone HTML-attributen.
- **Vertrouwde structuur** — De template-hiërarchie (`base.html` → `layout.html` → pagina's) lijkt sterk op het `BaseScreen`-patroon uit v0.7.

**Wanneer toch React/Vue overwegen:** Als de kalender-/roosterwidget zo complex wordt dat je veel client-side state nodig hebt (drag & drop, real-time updates voor meerdere gebruikers tegelijk). Dit kan dan als een afgebakende component binnen de HTMX-app leven.

### Template hiërarchie (equivalent van BaseScreen)

```
templates/
├── base.html            ← HTML boilerplate, CSS/JS imports
├── layouts/
│   ├── app_layout.html  ← Navigatiebalk, sidebar, flash messages
│   └── auth_layout.html ← Minimale layout voor login/TOTP-pagina's
└── pages/
    ├── auth/
    │   ├── login.html
    │   └── totp_verify.html
    ├── planning/
    │   ├── calendar.html
    │   └── shift_detail.html
    ├── leaves/
    │   └── leave_requests.html
    └── hr/
        └── export.html
```

### `base.html` patroon

```html
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>{% block title %}Planning Tool{% endblock %}</title>
    <link rel="stylesheet" href="/static/css/main.css">
    <script src="https://unpkg.com/htmx.org@1.9.x"></script>
</head>
<body>
    {% block content %}{% endblock %}

    {% with messages = get_flashed_messages() %}
        {% if messages %}
            <div class="flash-messages">
                {% for msg in messages %}<p>{{ msg }}</p>{% endfor %}
            </div>
        {% endif %}
    {% endwith %}
</body>
</html>
```

### HTMX voorbeeld: kalender cel verversen zonder page reload

```html
<!-- Shift-cel in de kalenderrij -->
<td id="cell-{{ user_id }}-{{ date }}"
    hx-get="/planning/cell/{{ user_id }}/{{ date }}"
    hx-trigger="click"
    hx-target="#cell-{{ user_id }}-{{ date }}"
    hx-swap="outerHTML">
    {{ shift_code }}
</td>
```


### PWA & Offline-weerbaarheid (Service Worker)

Omdat de app draait over een VDSL-lijn die af en toe kan haperen, is het zinvol om de browser een minimale cache te laten bijhouden van de basisinterface. Dit heet een **Progressive Web App (PWA)** — geen volwaardige offline app, maar een app die een VDSL-onderbreking netjes opvangt in plaats van te crashen met een lege pagina.

**Wat een Service Worker doet in deze context:**

De browser registreert een klein JavaScript-bestand dat op de achtergrond draait. Dit bestand onderschept netwerkrequests en kan beslissen: geef de gecachede versie terug (als de server niet bereikbaar is), of toon een nette offline-pagina.

Voor de Planning Tool is de meest zinvolle strategie **"Network First, Cache Fallback"**: probeer altijd de live data van de server te halen, maar als de server niet reageert, toon een gecachede versie van de pagina of een duidelijke melding.

#### Bestandsstructuur

```
frontend/static/
├── sw.js              ← De Service Worker (geregistreerd door base.html)
├── manifest.json      ← PWA manifest (icoontje, naam, kleur)
└── offline.html       ← Pagina die getoond wordt bij volledige verbindingsuitval
```

#### `sw.js` — Service Worker (kopieerklaar basisversie)

```javascript
const CACHE_NAME = 'planning-tool-v1';
const STATIC_ASSETS = [
    '/',
    '/static/css/main.css',
    '/offline.html',
];

// Bij installatie: cache de statische assets
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
});

// Bij activatie: verwijder oude caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
});

// Bij elke request: probeer netwerk, val terug op cache of offline.html
self.addEventListener('fetch', event => {
    // Alleen GET-requests cachen — POST/PUT/DELETE altijd live
    if (event.request.method !== 'GET') return;

    event.respondWith(
        fetch(event.request)
            .then(response => {
                // Sla een kopie op in de cache
                const copy = response.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
                return response;
            })
            .catch(() =>
                // Netwerk niet bereikbaar: probeer cache, anders offline.html
                caches.match(event.request).then(cached =>
                    cached || caches.match('/offline.html')
                )
            )
    );
});
```

#### `offline.html` — Nette melding bij verbindingsverlies

```html
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Verbinding verbroken — Planning Tool</title>
    <link rel="stylesheet" href="/static/css/main.css">
</head>
<body>
    <div class="offline-box">
        <h1>Verbinding verbroken</h1>
        <p>De Planning Tool is momenteel niet bereikbaar. Controleer uw internetverbinding.</p>
        <p><small>Uw gegevens zijn veilig. Probeer opnieuw zodra de verbinding hersteld is.</small></p>
        <button onclick="window.location.reload()">Opnieuw proberen</button>
    </div>
    <script>
        // Automatisch herladen zodra verbinding terug is
        window.addEventListener('online', () => window.location.reload());
    </script>
</body>
</html>
```

#### Registratie in `base.html`

```html
<script>
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js');
    }
</script>
```

#### `manifest.json` (optioneel — maakt de app installeerbaar op mobiel en desktop)

```json
{
    "name": "Planning Tool",
    "short_name": "Planning",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#2c5f8a",
    "icons": [
        { "src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png" },
        { "src": "/static/img/icon-512.png", "sizes": "512x512", "type": "image/png" }
    ]
}
```

**Belangrijk aandachtspunt:** De Service Worker onderschept alleen GET-requests — schrijfacties (shift aanmaken, verlof indienen) gaan altijd live naar de server. Als de verbinding weg is op het moment van een schrijfactie, vangt HTMX de fout op via een event. Koppel dit aan een i18n-melding bovenaan de pagina:

```javascript
// In base.html — globale verbindingsfout opvangen
document.body.addEventListener('htmx:responseError', () => {
    document.getElementById('connection-banner').textContent = t('common.connection_lost');
    document.getElementById('connection-banner').classList.remove('hidden');
});
window.addEventListener('online', () => {
    document.getElementById('connection-banner').classList.add('hidden');
});
```

Voeg de bijbehorende i18n-sleutel toe aan alle taalbestanden:

```json
"common": {
    "connection_lost": "Verbinding verbroken. Wijzigingen worden niet opgeslagen tot de verbinding hersteld is."
}
```

---

## 5. Database Migratie (SQLite → PostgreSQL)

### Fase 1: Consolidatie (drie SQLite-databases → één PostgreSQL)

De drie planningsgroepen hadden elk hun eigen SQLite-database. In v0.8 komen ze samen in één PostgreSQL-database met `group_id` als scheidingslijn.

**Stappenplan:**

1. **Schema analyse** — Vergelijk de drie SQLite-schemas. Zijn er structuurverschillen tussen de groepen? Documenteer de afwijkingen.
2. **Unified PostgreSQL schema opstellen** — Voeg `group_id` toe aan alle relevante tabellen (users, shifts, leave_requests, etc.).
3. **Migratiescript per groep** — Exporteer elke SQLite-database naar CSV of SQL-dump en importeer met `group_id = 1/2/3`.
4. **Data validatie** — Controleer record-aantallen en referentiële integriteit na import.
5. **Parallel run** — Laat v0.7 en v0.8 tijdelijk naast elkaar draaien op een testomgeving.

### SQLAlchemy ORM model voorbeeld (met group_id)

```python
# models/user.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum("beheerder", "planner", "hr", "gebruiker"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    totp_secret = Column(String, nullable=True)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
```

### Alembic (database versiebeheer — vervangt de migration scripts uit v0.7)

```bash
# Initialisatie (eenmalig)
alembic init migrations

# Nieuwe migratie aanmaken na modelwijziging
alembic revision --autogenerate -m "add shift_code_color_column"

# Migratie uitvoeren
alembic upgrade head

# Terugdraaien
alembic downgrade -1
```

Alembic vervangt de handmatige SQL-migratiescripts uit v0.7 en integreert naadloos met Docker (voer `alembic upgrade head` uit als startup-commando in de container).

---

## 6. Beveiliging & Configuratie

### .env bestand (nooit in git)

```env
DATABASE_URL=postgresql://planningtool:secret@db:5432/planningtool
SECRET_KEY=genereer-een-lange-random-string
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
ENVIRONMENT=production
```

### `config.py` patroon

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 30
    environment: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()
```

### Security checklist

- [ ] HTTPS verplicht — configureer in Nginx, redirect HTTP → HTTPS
- [ ] httpOnly cookies voor tokens — geen localStorage
- [ ] CORS strikt beperkt tot eigen domein
- [ ] Rate limiting op `/auth/token` (zie subsectie hieronder)
- [ ] Wachtwoorden gehasht met bcrypt (cost factor ≥ 12)
- [ ] TOTP-secret versleuteld opgeslagen in DB (Fernet of pgcrypto)
- [ ] DB niet direct bereikbaar van buiten Docker-netwerk

### Rate Limiting op de login-route

Omdat de app nu publiek bereikbaar is via het internet, is de login-route een aantrekkelijk doelwit voor **brute-force aanvallen** — bots die automatisch duizenden wachtwoordcombinaties proberen. Rate limiting beperkt het aantal verzoeken per IP-adres per tijdseenheid en maakt dit soort aanvallen praktisch onmogelijk.

**Aanbevolen aanpak: `slowapi`** — de de-facto standaard rate limiting bibliotheek voor FastAPI, gebaseerd op `limits`.

```bash
pip install slowapi
```

#### Basisintegratie in `main.py`

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

#### Toepassen op de login-router

```python
# api/routers/auth.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

@router.post("/token")
@limiter.limit("5/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return AuthService(db).login(form_data.username, form_data.password)

@router.post("/totp/verify")
@limiter.limit("5/minute")
async def verify_totp(request: Request, data: TOTPVerifyRequest, db: Session = Depends(get_db)):
    return AuthService(db).verify_totp(data.temp_token, data.code)
```

**Let op:** Pas de rate limit toe op zowel `/auth/token` als `/auth/totp/verify`. Anders kan een aanvaller na een geslaagde eerste stap alsnog de TOTP-codes brute-forcen.

#### Configuratie in `.env`

```env
# Rate limiting (optioneel: gebruik Redis als storage voor persistentie over restarts)
RATELIMIT_STORAGE_URL=redis://redis:6379/0
```

Zonder Redis-backend slaat `slowapi` de tellers op in geheugen — dat werkt prima, maar de tellers worden gereset bij elke herstart van de container. Met Redis (die al optioneel in je `docker-compose.yml` staat) blijven de tellers bewaard.

#### Aanbevolen limieten

| Route                  | Limiet          | Reden                                              |
|------------------------|-----------------|----------------------------------------------------|
| `POST /auth/token`     | 5 / minuut      | Voorkomt wachtwoord brute-force per IP             |
| `POST /auth/totp/verify` | 5 / minuut   | Voorkomt TOTP brute-force na geslaagde login       |
| Overige API-routes     | 60 / minuut     | Algemene bescherming tegen geautomatiseerd misbruik |

---

## 7. Service-laag (ongewijzigde filosofie, nieuwe implementatie)

De service-laag uit v0.7 blijft structureel identiek. Het enige verschil: in plaats van `get_db()` als SQLite context manager, injecteert FastAPI nu een SQLAlchemy `Session` via dependency injection.

### Service template (kopieerklaar)

```python
# services/planning_service.py
import logging
from sqlalchemy.orm import Session
from models.shift import Shift
from schemas.planning import ShiftCreate

logger = logging.getLogger(__name__)


class PlanningService:
    def __init__(self, db: Session):
        self.db = db

    def get_shifts_for_group(self, group_id: int, year: int, month: int) -> list[Shift]:
        try:
            return (
                self.db.query(Shift)
                .filter(Shift.group_id == group_id, Shift.year == year, Shift.month == month)
                .all()
            )
        except Exception as e:
            logger.error(f"Fout bij ophalen shifts: group={group_id}, {year}-{month}: {e}")
            raise

    def create_shift(self, data: ShiftCreate) -> Shift:
        try:
            shift = Shift(**data.model_dump())
            self.db.add(shift)
            self.db.commit()
            self.db.refresh(shift)
            return shift
        except Exception as e:
            self.db.rollback()
            logger.error(f"Fout bij aanmaken shift: {data}: {e}")
            raise
```

---

## 8. Ontwikkelings-Checklist voor Nieuwe Features

Houd dezelfde werkwijze aan als in v0.7, uitgebreid voor de webcontext:

1. **Model** — Definieer het SQLAlchemy ORM model (+ Alembic migratie).
2. **Schema** — Maak Pydantic schemas voor request en response.
3. **Service** — Implementeer de business logica in de service-laag.
4. **Unit Tests** — Test de service onafhankelijk (mock de database).
5. **Router** — Maak de FastAPI router endpoint (dun — delegeer naar service).
6. **Template** — Bouw de HTML-pagina met Jinja2 (+ HTMX waar nuttig).
7. **Offline** — Controleer of de nieuwe pagina correct werkt als gecachede fallback (geen schrijfacties vereist bij offline).
8. **Rechten** — Controleer of de juiste `require_role()` dependency aanwezig is.
9. **i18n** — Voeg alle gebruikersteksten toe aan `locales/nl.json` (en later `en.json`/`fr.json`), gebruik `t()` in router én template.
10. **Audit** — Voeg een `AuditLog`-entry toe voor elke schrijfactie die voor een gebruiker zichtbaar is.
11. **Logging** — Voeg logging toe in alle `except`-blokken van de service.

---

## 9. Foutafhandeling (web-grade)

### HTTP foutcodes als standaard

```python
# api/exceptions.py
from fastapi import HTTPException, status

class InvalidCredentialsError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ongeldige inloggegevens")

class InsufficientRightsError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="Onvoldoende rechten")

class NotFoundError(HTTPException):
    def __init__(self, resource: str):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} niet gevonden")
```

### Global exception handler

```python
# main.py
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error(f"Onverwachte fout: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Interne serverfout"})
```

---

## 10. Versiebeheer & Releases

| Constante         | Locatie     | Doel                                              |
|-------------------|-------------|---------------------------------------------------|
| `APP_VERSION`     | `config.py` | Huidige applicatieversie (bijv. "0.8.0")          |
| `MIN_DB_VERSION`  | `config.py` | Minimaal vereiste Alembic migratie-revision       |
| Alembic revision  | migrations/ | Automatisch beheerd — altijd in sync met modellen |

Bij opstarten controleert de app of de database volledig gemigreerd is (`alembic current == head`). Zo niet: crash met een duidelijke foutmelding in de logs, zodat de NAS-beheerder weet wat er mist.


---

## 11. Internationalisatie / Meertaligheid (i18n)

Omdat de app nu via een browser bereikbaar is voor medewerkers van verschillende taalgroepen, is het zinvol om alle gebruikersteksten centraal te beheren en meertalig te maken. In v0.7 waren foutmeldingen, menulabels en validatieteksten hardcoded in het Nederlands door de hele codebase. In v0.8 vervangen we elke hardcoded string door een opzoeksleutel.

### Het principe

In plaats van:

```python
show_error("Fout wachtwoord of gebruikersnaam")
```

Schrijf je:

```python
show_error(t("auth.login.invalid_credentials"))
```

De functie `t()` zoekt de juiste vertaling op op basis van de actieve taal van de ingelogde gebruiker. Parameters zoals aantallen of namen zijn dynamisch invulbaar:

```python
t("planning.validation.max_days_without_rest", max=7, current=9)
# NL → "Maximaal 7 dagen zonder rustdag overschreden (9 dagen)."
# FR → "Maximum de 7 jours sans jour de repos dépassé (9 jours)."
```

### Bestandsstructuur

```
locales/
├── nl.json    ← Nederlands (standaard, altijd volledig)
├── en.json    ← Engels
└── fr.json    ← Frans
```

### Sleutelstructuur in de JSON-bestanden

Gebruik hiërarchische stip-notatie: `module.scherm.boodschap`. Vermijd generieke sleutels zoals `error_1` — die zijn onleesbaar na een paar weken.

```json
{
  "auth": {
    "login": {
      "invalid_credentials": "Fout wachtwoord of gebruikersnaam.",
      "account_locked": "Account geblokkeerd na te veel mislukte pogingen.",
      "totp_required": "Voer uw authenticatiecode in.",
      "totp_invalid": "Ongeldige authenticatiecode. Probeer opnieuw."
    }
  },
  "planning": {
    "validation": {
      "max_days_without_rest": "Maximaal {max} dagen zonder rustdag overschreden ({current} dagen).",
      "max_weekly_hours": "Maximaal {max} uur per week overschreden ({current} uur).",
      "min_rest_between_shifts": "Minimum rust van {min} uur tussen shifts niet gerespecteerd.",
      "max_days_per_cycle": "Maximum van {max} gewerkte dagen per 28-dagencyclus overschreden."
    }
  },
  "leave": {
    "request": {
      "submitted": "Verlofaanvraag ingediend.",
      "approved": "Verlofaanvraag goedgekeurd.",
      "rejected": "Verlofaanvraag geweigerd.",
      "insufficient_balance": "Onvoldoende verlofsaldo ({available} dagen beschikbaar, {requested} gevraagd)."
    }
  },
  "navigation": {
    "dashboard": "Dashboard",
    "planning": "Planning",
    "leave_requests": "Verlofaanvragen",
    "settings": "Instellingen",
    "logout": "Uitloggen"
  },
  "common": {
    "save": "Opslaan",
    "cancel": "Annuleren",
    "confirm": "Bevestigen",
    "delete": "Verwijderen",
    "edit": "Bewerken",
    "error": "Fout",
    "success": "Gelukt",
    "loading": "Laden...",
    "yes": "Ja",
    "no": "Nee"
  }
}
```

### De `I18n`-klasse (kopieerklaar)

```python
# core/i18n.py
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES = ["nl", "en", "fr"]
DEFAULT_LOCALE = "nl"


class I18n:
    def __init__(self, locale: str = DEFAULT_LOCALE):
        self._strings: dict = {}
        self._locale: str = DEFAULT_LOCALE
        self.set_locale(locale)

    def set_locale(self, locale: str):
        if locale not in SUPPORTED_LOCALES:
            logger.warning(f"Niet-ondersteunde taal '{locale}', terugvallen op '{DEFAULT_LOCALE}'")
            locale = DEFAULT_LOCALE
        path = Path(f"locales/{locale}.json")
        if not path.exists():
            logger.error(f"Taalbestand niet gevonden: {path}, terugvallen op Nederlands")
            path = Path(f"locales/{DEFAULT_LOCALE}.json")
        with open(path, encoding="utf-8") as f:
            self._strings = json.load(f)
        self._locale = locale

    def t(self, key: str, **kwargs) -> str:
        """
        Haal vertaalde tekst op via stip-notatie sleutel.

        Voorbeeld:
            t("planning.validation.max_days_without_rest", max=7, current=9)
        """
        parts = key.split(".")
        value = self._strings
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                logger.warning(f"Ontbrekende vertaalsleutel: '{key}' voor taal '{self._locale}'")
                return key    # Geef de sleutel terug als noodoplossing — zichtbaar in de UI
        if isinstance(value, str):
            try:
                return value.format(**kwargs) if kwargs else value
            except KeyError as e:
                logger.error(f"Ontbrekende parameter {e} voor sleutel '{key}'")
                return value
        return key


# Globale instantie — aangemaakt bij app-start, taal wordt per request ingesteld
i18n = I18n()
t = i18n.t
```

### Integratie met FastAPI: taal per gebruiker

De taalvoorkeur wordt opgeslagen per gebruiker in de database en geladen bij elke request via een FastAPI dependency.

```python
# In het User model
locale = Column(String(5), default="nl", nullable=False)
```

```python
# api/dependencies.py — taal instellen per request
def get_translator(current_user=Depends(get_current_user)) -> callable:
    """Geeft een t()-functie terug die geconfigureerd is voor de taal van de ingelogde gebruiker."""
    request_i18n = I18n(locale=current_user.locale)
    return request_i18n.t
```

```python
# Gebruik in een router
@router.post("/shifts")
def create_shift(
    data: ShiftCreate,
    db: Session = Depends(get_db),
    t: callable = Depends(get_translator),
    current_user=Depends(get_current_user),
):
    try:
        return PlanningService(db).create_shift(data)
    except MaxDaysWithoutRestError as e:
        raise HTTPException(400, detail=t("planning.validation.max_days_without_rest", max=e.max, current=e.current))
```

### Taalkeuze in de UI

In de gebruikersinstellingen voeg je een eenvoudige selector toe:

```html
<!-- templates/pages/settings/profile.html -->
<form hx-post="/users/me/locale" hx-swap="none">
    <label>Taal / Language / Langue</label>
    <select name="locale">
        <option value="nl" {% if user.locale == "nl" %}selected{% endif %}>Nederlands</option>
        <option value="en" {% if user.locale == "en" %}selected{% endif %}>English</option>
        <option value="fr" {% if user.locale == "fr" %}selected{% endif %}>Français</option>
    </select>
    <button type="submit">{{ t("common.save") }}</button>
</form>
```

### Migratie vanuit v0.7: werkwijze

De meest efficiënte aanpak is: maak eerst `nl.json` volledig op basis van alle bestaande v0.7-teksten, vóór je ook maar één regel andere v0.8-code schrijft. Dat geeft je meteen een volledige inventaris van alles wat vertaald moet worden. Daarna kunnen de Engelse en Franse versies aangevuld worden door iemand zonder technische kennis — ze werken enkel in de JSON-bestanden.

Migratie-checklist per module:

- [ ] Inventariseer alle hardcoded strings in de v0.7-module
- [ ] Maak sleutels aan in `nl.json` met beschrijvende hiërarchische namen
- [ ] Vervang elke hardcoded string door `t("sleutel")`
- [ ] Voeg dezelfde sleutels toe in `en.json` en `fr.json`
- [ ] Test met alle drie de talen ingesteld

---

## 12. Aanvullende Suggesties voor v0.8

De volgende punten zijn geen vereisten voor de basiswerking van v0.8, maar zijn de moeite waard om nu al op te nemen in de architectuurbeslissingen — ze zijn achteraf veel moeilijker in te bouwen.

### 12.1 Audit Trail (Wie heeft wat gewijzigd?)

In een planningsapplicatie met meerdere planners en HR-toegang is het waardevol om bij te houden wie een wijziging heeft aangebracht. Niet voor sancties, maar voor praktische vragen zoals "wie heeft deze shift aangepast?" of "wanneer is dit verlof goedgekeurd?".

```python
# models/audit_log.py
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)   # bijv. "shift.create", "leave.approve"
    target_type = Column(String(50))              # bijv. "Shift", "LeaveRequest"
    target_id = Column(Integer)
    detail = Column(Text)                         # JSON-string met voor/na waarden
```

Dit is een eenvoudige tabel die je als service-mixin kunt aanroepen. De implementatie kost weinig moeite op het moment van bouwen, maar is erg moeilijk toe te voegen als de app al in productie draait.

### 12.2 Notificaties (In-app meldingen)

Medewerkers die een verlofaanvraag indienen verwachten feedback. Planners willen een signaal als er nieuwe aanvragen zijn. Een lichtgewicht notificatiesysteem — geen e-mail, gewoon een badge in de navigatie — lost dit op zonder externe afhankelijkheden.

```python
# models/notification.py
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_key = Column(String(100), nullable=False)   # i18n-sleutel
    message_params = Column(JSON)                        # Parameters voor de sleutel
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

Merk op dat `message_key` een i18n-sleutel is, geen hardcoded tekst — de notificatie wordt in de taal van de ontvanger getoond, niet in de taal van degene die de actie uitvoerde.

### 12.3 Configuratie per Planningsgroep

De drie planningsgroepen hebben elk hun eigen regels (shift codes, HR-drempelwaarden, typetabel). In v0.7 zat dit deels hardcoded of in aparte databases. In v0.8 sla je dit op als configuratie per groep:

```python
# models/group_config.py
class GroupConfig(Base):
    __tablename__ = "group_configs"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), unique=True, nullable=False)
    max_weekly_hours = Column(Integer, default=50)
    max_days_per_cycle = Column(Integer, default=19)
    cycle_length_days = Column(Integer, default=28)
    min_rest_hours = Column(Integer, default=12)
    locale = Column(String(5), default="nl")       # Standaardtaal voor de groep
```

Dit maakt de applicatie flexibel genoeg om een vierde groep toe te voegen zonder ook maar één regel code te wijzigen.

### 12.4 Gestructureerde Logging met Correlatie-ID's

In een webapplicatie met meerdere gelijktijdige gebruikers is het moeilijk om logregels van dezelfde request samen te houden. Een correlatie-ID lost dit op: elke request krijgt een uniek ID dat in elke logregel voor die request verschijnt.

```python
# middleware/logging_middleware.py
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

class RequestLoggingMiddleware:
    async def __call__(self, request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request_id_var.set(request_id)
        # Voeg request_id toe aan alle logregels van deze request
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

In de logs zie je dan meteen welke regels bij dezelfde request horen, ook als drie gebruikers tegelijk een fout genereren.

### 12.5 Health Check Endpoint

Een minimaal endpoint dat Docker en monitoring-tools kunnen aanroepen om te weten of de app draait en de database bereikbaar is:

```python
# api/routers/health.py
@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "version": settings.app_version}
    except Exception:
        raise HTTPException(503, detail="Database niet bereikbaar")
```

Docker Compose kan dit gebruiken als `healthcheck`, zodat de frontend-container pas opstart als de backend-database écht klaar is — en niet bij een race condition tijdens het opstarten van de NAS.

---

## Samenvatting: v0.7 → v0.8 mapping

| v0.7 (PyQt6/SQLite)         | v0.8 (FastAPI/PostgreSQL)            |
|-----------------------------|--------------------------------------|
| `BaseScreen`                | `base.html` + Jinja2 layout          |
| `get_db()` context manager  | SQLAlchemy `Session` via DI          |
| `UserService(conn)`         | `UserService(db)` — identiek         |
| SQLite migration scripts    | Alembic autogenerate                 |
| PyInstaller deployment      | Docker Compose op NAS                |
| 3 aparte SQLite databases   | 1 PostgreSQL met `group_id`          |
| Lokale .log bestanden        | Docker logging + optioneel Loki/Seq  |
| bcrypt wachtwoorden         | bcrypt — identiek                    |
| Rollen inconsistent (werknemer/gebruiker/medewerker) | Rollen definitief: `beheerder`/`planner`/`hr`/`gebruiker` |
| Hardcoded NL strings door hele codebase | Centrale i18n via `locales/*.json` + `t()`-functie |
| Desktop app — geen verbindingsproblemen | PWA Service Worker — nette offline-melding bij VDSL-uitval |
| Geen audit trail | `audit_log` tabel — wie heeft wat gewijzigd |
| HR-drempelwaarden deels hardcoded | `GroupConfig` per planningsgroep in database |
| Rollen: `beheerder`/`planner`/`gebruiker` (+ inconsistent `werknemer`/`medewerker`) | Rollen: `beheerder`/`planner`/`hr`/`gebruiker` — definitief vastgelegd |
