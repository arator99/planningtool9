# Correctieplan — Security Audit 2026-03-16b

**Bron:** `docs/rapporten/audit_2026-03-16b.md`
**Prioriteit:** Groep A + B vóór Fase 3; Groep C als onderdeel van Fase 3; Groep D doorlopend

---

## Overzicht

| Correctie | Audit-ID | Omvang | Prioriteit | Ernst |
|---|---|---|---|---|
| A1 — Groepen-router verwijderen | SEC-01 | Klein | 🔴 Onmiddellijk | Kritiek |
| A2 — Changelog XSS sanitatie | SEC-02 | Klein | 🔴 Onmiddellijk | Kritiek |
| A3 — max_age op toegangs_token cookie | SEC-04 | Klein (2 plekken) | 🟠 Onmiddellijk | Hoog |
| A4 — HSTS header toevoegen | SEC-05 | Klein | 🟠 Onmiddellijk | Hoog |
| A5 — Seed-wachtwoord via env + productie-guard | SEC-08 + SEC-15 | Klein | 🟠 Onmiddellijk | Middel |
| A6 — Health endpoint info beperken | SEC-13 | Klein | 🟡 Onmiddellijk | Middel |
| A7 — Rate limiting IP achter Cloudflare Tunnel | SEC-16 | Klein | ⚪ Onmiddellijk | Laag |
| B1 — /planning/override integer ID → UUID + membership check | SEC-06 | Middel | 🟠 Hoog | Hoog |
| B2 — TOTP foutantwoord: CSRF-token + geheim niet hergeneren | SEC-07 | Klein | 🟠 Hoog | Hoog |
| C1 — BaseRepository met _locatie_filter() implementeren | Plan-afwijking 1 | Groot | 🔴 Fase 3 | Structureel |
| C2 — locatie_guard.py middleware implementeren | Plan-afwijking 2 | Middel | 🔴 Fase 3 | Structureel |
| C3 — vereiste_rol() migreren naar GebruikerRol tabel | SEC-03 | Groot | 🟠 Fase 3 | Hoog |
| D1 — Navigatiebalk rol-check via is_* variabelen | SEC-09 | Middel | 🟡 Doorlopend | Middel |
| D2 — CSP unsafe-inline → nonce-gebaseerd | SEC-10 | Groot | 🟡 Fase 5/6 | Middel |
| D3 — kaart.html \| safe documentatie | SEC-11 | Klein | 🟡 Doorlopend | Middel |
| D4 — URL querystring meldingen → vaste sleutels | SEC-12 | Middel | 🟡 Doorlopend | Middel |
| D5 — Ontbrekende AuditLog entries | SEC-18 | Middel | 🟡 Doorlopend | Laag |

---

## Groep A — Onmiddellijk (klein werk, groot risico)

---

## Correctie A1 — Groepen-router verwijderen

**Audit-ID:** SEC-01
**Ernst:** 🔴 Kritiek
**Omvang:** Klein — controleren of bestand nog op schijf staat + verwijderen

### Probleem

De `groepen`-router (legacy v0.8) staat **niet** meer in de `include_router`-aanroepen van `main.py`, maar `backend/api/routers/groepen.py` en `backend/models/groep.py` kunnen nog op schijf staan. Als ze nog bestaan, vormen ze een risico:

1. `groepen.py:38` — `db.query(Groep).order_by(Groep.naam).all()` zonder `locatie_id`-filter: cross-tenant datalekage als de router ooit hersteld wordt.
2. `groepen.py:115` — `db.query(Gebruiker).filter(Gebruiker.is_actief == True)` zonder locatie-filter.
3. Integer IDs in paden: `/groepen/{groep_id}/leden/{lid_gebruiker_id}` (regels 93, 134, 165).
4. Import van `models.groep.GebruikerGroep, Groep, GroepConfig` — verouderd model, vervangen door `GebruikerRol`.

CLAUDE.md is expliciet: *"Geen `Groep`/`groep` meer — hernoemd naar `Team`/`team` overal"* en *"Geen `GebruikerGroep` — vervangen door `GebruikerRol`"*.

### Oplossing

Controleer of de bestanden nog bestaan en verwijder of archiveer ze.

### Taken

- [x] Controleer of `backend/api/routers/groepen.py` nog bestaat
- [x] Controleer of `backend/models/groep.py` nog bestaat
- [x] Zoek resterende referenties: `groepen` in `main.py`, `routers/`, `models/`
- [x] Verwijder `backend/api/routers/groepen.py` als het nog bestaat
- [x] Verwijder import van `models.groep` overal waar aanwezig
- [x] Verwijder `backend/models/groep.py` als het nog bestaat
- [ ] Herstart applicatie en verifieer dat er geen `ImportError` optreedt

---

## Correctie A2 — Changelog XSS sanitatie

**Audit-ID:** SEC-02
**Ernst:** 🔴 Kritiek
**Omvang:** Klein — 1 pip-pakket + 1 aanpassing in `help.py`

### Probleem

`backend/api/routers/help.py:31`:
```python
inhoud_html = markdown.markdown(tekst, extensions=["tables", "fenced_code"])
```

De HTML wordt ongesaniteerd doorgegeven aan `templates/pages/help/changelog.html:38` via `{{ inhoud_html | safe }}`. De `markdown`-bibliotheek converteert `<script>`-tags standaard **niet** weg — een regel `<script>alert(1)</script>` in `CHANGELOG.md` resulteert in een stored XSS voor alle ingelogde gebruikers, inclusief beheerders (session hijacking, cookie-diefstal).

### Oplossing

Gebruik `bleach` voor HTML-sanitatie na de Markdown-conversie:

```python
import bleach

TOEGESTANE_TAGS = [
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "strong", "em", "code", "pre",
    "ul", "ol", "li", "blockquote", "hr",
    "table", "thead", "tbody", "tr", "th", "td",
    "a",
]
TOEGESTANE_ATTRIBUTEN = {"a": ["href", "title"], "td": ["align"], "th": ["align"]}

inhoud_html = markdown.markdown(tekst, extensions=["tables", "fenced_code"])
inhoud_html = bleach.clean(inhoud_html, tags=TOEGESTANE_TAGS,
                           attributes=TOEGESTANE_ATTRIBUTEN, strip=True)
```

### Taken

- [x] Voeg `bleach>=6.0` toe aan `requirements.txt`
- [x] `backend/api/routers/help.py`: importeer `bleach` bovenaan
- [x] `backend/api/routers/help.py:31`: pas de `inhoud_html`-berekening aan met `bleach.clean(...)` conform bovenstaand patroon
- [ ] Test: voeg `<script>alert('xss')</script>` toe aan `CHANGELOG.md`, laad `/help/changelog`, verifieer dat het script niet uitvoert
- [ ] Overweeg de changelog-route te beperken tot `vereiste_rol("beheerder", "planner", "hr")` i.p.v. enkel `vereiste_login`

---

## Correctie A3 — max_age op toegangs_token cookie

**Audit-ID:** SEC-04
**Ernst:** 🟠 Hoog
**Omvang:** Klein — 2 aanpassingen in `auth.py`

### Probleem

De `toegangs_token` cookie wordt op twee plekken ingesteld zonder `max_age`:

**Plek 1** — `backend/api/routers/auth.py:94-95` (directe login, zonder TOTP):
```python
antwoord.set_cookie(key="toegangs_token", value=resultaat["token"],
                    httponly=True, samesite="strict", secure=_SECURE)
```

**Plek 2** — `backend/api/routers/auth.py:147-154` (na TOTP-verificatie):
```python
antwoord.set_cookie(
    key="toegangs_token",
    value=access_token,
    httponly=True,
    samesite="strict",
    secure=_SECURE,
)
```

De `taal`-cookie (regel 90, 96) heeft wel `max_age=60 * 60 * 24 * 365` — er is bewust nagedacht over cookie-levensduur, maar de beveiligingscookie ontbreekt een expiry. Het JWT-token vervalt na `toegangs_token_verlopen_minuten` (default 30 minuten, `config.py`), maar de browser houdt de cookie vast tot browserrestart. Bij session-restore blijft een verlopen cookie aanwezig.

### Oplossing

Voeg `max_age` toe aan beide aanroepen, gelijk aan de JWT-verlooptijd in seconden. `instellingen` is al geïmporteerd in `auth.py` (regel 10):

```python
antwoord.set_cookie(
    key="toegangs_token",
    value=resultaat["token"],
    httponly=True,
    samesite="strict",
    secure=_SECURE,
    max_age=instellingen.toegangs_token_verlopen_minuten * 60,
)
```

### Taken

- [x] `backend/api/routers/auth.py:94-95`: voeg `max_age=instellingen.toegangs_token_verlopen_minuten * 60` toe
- [x] `backend/api/routers/auth.py:147-154`: voeg dezelfde `max_age` toe
- [ ] Verifieer: na inloggen toont browser DevTools (Application → Cookies) een `Max-Age` op de `toegangs_token` cookie

---

## Correctie A4 — HSTS header toevoegen

**Audit-ID:** SEC-05
**Ernst:** 🟠 Hoog
**Omvang:** Klein — 1 regel in `security_headers.py`

### Probleem

`backend/api/middleware/security_headers.py` — de `dispatch`-methode voegt `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` en `Permissions-Policy` toe, maar **geen `Strict-Transport-Security`** (HSTS). De applicatie draait via Cloudflare Tunnel; Cloudflare's HSTS-configuratie is afhankelijk van accountinstellingen en is geen vervanging voor een applicatie-level header. Zonder HSTS zijn downgrade-aanvallen (SSL-stripping) mogelijk.

### Oplossing

Voeg de HSTS-header toe in het bestaande `if instellingen.omgeving != "development":` blok (na de CSP-regel):

```python
if instellingen.omgeving != "development":
    antwoord.headers["Content-Security-Policy"] = self._CSP_PRODUCTIE
    antwoord.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
```

`max-age=31536000` = 1 jaar, de aanbevolen standaard. **Niet** toevoegen in development — dit blokkeert lokale HTTP-ontwikkeling.

### Taken

- [x] `backend/api/middleware/security_headers.py`: voeg `antwoord.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"` toe in het `if omgeving != "development":` blok
- [ ] Verifieer in productie/staging: `curl -I https://<domein>/login` toont de header
- [ ] Overweeg later `preload` toe te voegen (onomkeerbaar — niet nu)

---

## Correctie A5 — Seed-wachtwoord via env + productie-guard

**Audit-ID:** SEC-08 + SEC-15
**Ernst:** 🟡 Middel + ⚪ Laag
**Omvang:** Klein — 3 aanpassingen in `seed.py` + `.env.example`

### Probleem

**SEC-08** — `backend/api/seed.py:39`:
```python
gehashed_wachtwoord=hash_wachtwoord("Admin1234!"),
```
Plaintext wachtwoord in broncode, zichtbaar in git-history.

**SEC-15** — `backend/main.py:38` roept `seed_test_data()` aan bij elke startup. De guard `db.query(Gebruiker).count() > 0` is zwak: bij een database-reset in productie worden testdata opnieuw aangemaakt.

### Oplossing

**Stap 1 — Productie-guard:**
```python
from config import instellingen

def seed_test_data() -> None:
    if instellingen.omgeving == "production":
        logger.info("Seeden overgeslagen (productie-omgeving).")
        return
    ...
```

**Stap 2 — Wachtwoord via omgevingsvariabele:**
```python
import os, secrets, string

seed_wachtwoord = os.environ.get("SEED_ADMIN_WACHTWOORD")
if not seed_wachtwoord:
    alfabet = string.ascii_letters + string.digits + "!@#$%"
    seed_wachtwoord = "".join(secrets.choice(alfabet) for _ in range(16))
    logger.warning("SEED_ADMIN_WACHTWOORD niet ingesteld — tijdelijk wachtwoord: %s", seed_wachtwoord)
```

### Taken

- [x] `backend/api/seed.py`: voeg productie-guard toe als eerste statement in `seed_test_data()`: `if instellingen.omgeving == "production": return`
- [x] `backend/api/seed.py`: vervang `hash_wachtwoord("Admin1234!")` door dynamische ophaling uit `os.environ.get("SEED_ADMIN_WACHTWOORD")` met willekeurige fallback + log
- [x] `.env.example`: voeg `SEED_ADMIN_WACHTWOORD=verander_dit_direct` toe
- [ ] `docker-compose.yml` of `.env`: voeg `SEED_ADMIN_WACHTWOORD` toe voor development
- [ ] Overweeg na voltooiing: git-history saneren voor de `Admin1234!`-string als de repo extern gedeeld wordt

---

## Correctie A6 — Health endpoint info beperken

**Audit-ID:** SEC-13
**Ernst:** 🟡 Middel
**Omvang:** Klein — 1 aanpassing in `health.py`

### Probleem

Het health-endpoint retourneert publiek versie en omgeving: `{"status": "ok", "versie": "0.9.0", "omgeving": "development"}`. Versie-informatie helpt aanvallers bij het identificeren van bekende kwetsbaarheden.

### Oplossing

```python
@router.get("/health")
def health_check():
    if instellingen.omgeving == "development":
        return {"status": "ok", "versie": instellingen.app_versie, "omgeving": instellingen.omgeving}
    return {"status": "ok"}
```

### Taken

- [x] `backend/api/routers/health.py`: beperk versie en omgeving tot development-omgeving
- [ ] Test: in development geeft `/health` alle velden; in productie enkel `{"status": "ok"}`

---

## Correctie A7 — Rate limiting IP achter Cloudflare Tunnel

**Audit-ID:** SEC-16
**Ernst:** ⚪ Laag
**Omvang:** Klein — 1 aanpassing in `rate_limiter.py`

### Probleem

`backend/api/rate_limiter.py:4`:
```python
limiter = Limiter(key_func=get_remote_address)
```

`get_remote_address` leest `request.client.host`. Achter Cloudflare Tunnel geeft dit het IP van de proxy — alle gebruikers delen dezelfde rate-limit bucket. Login-bescherming (5/min) werkt dan effectief als 5 requests per minuut voor alle gebruikers samen.

### Oplossing

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

def _haal_client_ip(request) -> str:
    """Leest het werkelijke client-IP achter Cloudflare Tunnel."""
    return (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or get_remote_address(request)
    )

limiter = Limiter(key_func=_haal_client_ip)
```

`CF-Connecting-IP` is betrouwbaar als de applicatie **uitsluitend** via Cloudflare Tunnel bereikbaar is (Cloudflare stelt deze header altijd in en verwijdert gespoofde versies).

### Taken

- [x] `backend/api/rate_limiter.py`: voeg `_haal_client_ip`-functie toe en gebruik als `key_func`
- [ ] Verifieer dat Cloudflare Tunnel `CF-Connecting-IP` doorgeeft (test via header-logging op een protected endpoint)
- [ ] Documenteer in deployment-instructies dat directe toegang buiten Cloudflare Tunnel afgeschermd moet zijn

---

## Groep B — Hoog (meer werk, security-kritisch)

---

## Correctie B1 — /planning/override integer ID → UUID + team-membership check

**Audit-ID:** SEC-06
**Ernst:** 🟠 Hoog
**Omvang:** Middel — 1 route + template-aanpassing

### Probleem

`backend/api/routers/planning.py:306-309`:
```python
gebruiker_id: int = Form(...)   # ← intern integer ID, geen UUID
```

Een kwaadaardige planner kan willekeurige integers proberen om overrides aan te maken voor gebruikers van andere teams of locaties. Er is geen controle of de doelgebruiker lid is van het team van de ingelogde planner. Alle andere planning-routes gebruiken al UUID's (`/cel/{gebruiker_uuid}`, `/suggestie/{gebruiker_uuid}`, `/reserve/{reserve_uuid}`).

### Oplossing

**Stap 1 — Formulierveld vervangen:**
```python
# Voor:
gebruiker_id: int = Form(...)
# Na:
gebruiker_uuid: str = Form(...)
```

**Stap 2 — UUID-lookup:**
```python
try:
    doel = GebruikerService(db).haal_op_uuid(gebruiker_uuid)
except ValueError:
    raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
```

**Stap 3 — Team-membership check** (vóór `maak_override`-aanroep):
```python
from api.dependencies import heeft_rol_in_team

if not heeft_rol_in_team(doel.id, team_id, ("teamlid", "planner"), db):
    raise HTTPException(status_code=403, detail="Gebruiker behoort niet tot dit team")
```

`heeft_rol_in_team` is beschikbaar in `backend/api/dependencies.py:119-142`.

**Stap 4 — Service-aanroep bijwerken:**
```python
ValidatieService(db).maak_override(
    team_id=team_id,
    gebruiker_id=doel.id,   # ← intern ID na UUID-lookup
    ...
)
```

**Stap 5 — Template bijwerken** (`templates/pages/planning/_validatie_paneel.html`):
```html
<!-- Voor: -->
<input type="hidden" name="gebruiker_id" value="{{ fout.gebruiker_id }}">
<!-- Na: -->
<input type="hidden" name="gebruiker_uuid" value="{{ fout.gebruiker_uuid }}">
```

Dit vereist dat `ValidatieFout`-objecten ook een `gebruiker_uuid` bevatten.

### Taken

- [x] `backend/api/routers/planning.py:306`: vervang `gebruiker_id: int = Form(...)` door `gebruiker_uuid: str = Form(...)`
- [x] Voeg na het datum-parseerblok een UUID-lookup toe via `GebruikerService(db).haal_op_uuid(gebruiker_uuid)`
- [x] Voeg team-membership check toe via `heeft_rol_in_team(doel.id, team_id, ("teamlid", "planner"), db)` met HTTPException 403 bij ontbrekend lidmaatschap
- [x] Pas `ValidatieService(db).maak_override(gebruiker_id=doel.id, ...)` aan
- [x] Controleer of `ValidatieFout`-objecten een `gebruiker_uuid` bevatten; voeg toe indien nodig
- [x] Vervang het `gebruiker_id`-veld in het override-formuliertemplate door `gebruiker_uuid`

---

## Correctie B2 — TOTP foutantwoord: CSRF-token + geheim niet hergeneren bij fout

**Audit-ID:** SEC-07
**Ernst:** 🟠 Hoog
**Omvang:** Klein — 1 handler in `auth.py` + 1 service-methode

### Probleem

`backend/api/routers/auth.py:197-211`:
```python
except ValueError as fout:
    resultaat = AuthService(db).start_totp_instelling(huidige_gebruiker.id)  # ← NIEUW geheim!
    return sjablonen.TemplateResponse(
        "pages/totp_instellen.html",
        {
            ...
            "totp_geheim": resultaat["geheim"],
            "fout": str(fout),
            # GEEN csrf_token!   ← formulier werkt niet na fout
        },
        status_code=400,
    )
```

**Probleem 1:** `csrf_token` ontbreekt in het foutantwoord. De GET-handler (regel 163-184) stuurt wel `csrf_token` mee. Zonder token faalt de volgende formuliersubmissie met "Ongeldige of ontbrekende CSRF-token" — de gebruiker kan niet verder na een typfout.

**Probleem 2:** `start_totp_instelling()` genereert bij elke mislukte poging een nieuw TOTP-geheim en overschrijft het vorige. De gebruiker moet elke keer de QR-code opnieuw scannen.

### Oplossing

**Stap 1 — Service-methode toevoegen** die bestaand geheim teruggeeft zonder nieuw te genereren:
```python
# AuthService:
def haal_bestaand_totp(self, gebruiker_id: int) -> dict:
    """Geeft het bestaande (nog niet bevestigde) TOTP-geheim terug."""
    gebruiker = self.db.query(Gebruiker).filter(Gebruiker.id == gebruiker_id).first()
    if not gebruiker or not gebruiker.totp_geheim:
        raise ValueError("Geen TOTP-geheim beschikbaar — start instelling opnieuw")
    totp = pyotp.TOTP(gebruiker.totp_geheim)
    return {
        "geheim": gebruiker.totp_geheim,
        "uri": totp.provisioning_uri(
            name=gebruiker.gebruikersnaam,
            issuer_name=instellingen.totp_issuer,
        ),
    }
```

**Stap 2 — Foutantwoord corrigeren:**
```python
from services.domein.csrf_domein import genereer_csrf_token

except ValueError as fout:
    resultaat = AuthService(db).haal_bestaand_totp(huidige_gebruiker.id)
    return sjablonen.TemplateResponse(
        "pages/totp_instellen.html",
        {
            "request": request,
            "gebruiker": huidige_gebruiker,
            "totp_uri": resultaat["uri"],
            "totp_geheim": resultaat["geheim"],
            "fout": str(fout),
            "csrf_token": genereer_csrf_token(str(huidige_gebruiker.id)),  # ← toegevoegd
        },
        status_code=400,
    )
```

### Taken

- [x] `backend/services/auth_service.py`: voeg `haal_bestaand_totp(gebruiker_id: int) -> dict` toe
- [x] `backend/api/routers/auth.py:200`: vervang `AuthService(db).start_totp_instelling(...)` door `AuthService(db).haal_bestaand_totp(...)` in het `except`-blok
- [x] `backend/api/routers/auth.py:201-211`: voeg `"csrf_token": genereer_csrf_token(str(huidige_gebruiker.id))` toe aan het fout-antwoord
- [x] Controleer of `genereer_csrf_token` al geïmporteerd is in `auth.py`; voeg import toe indien nodig
- [ ] Test: foutief TOTP ingeven → pagina toont zelfde QR-code → CSRF-token aanwezig → volgende poging werkt

---

## Groep C — Plan-afwijkingen (structureel, voor Fase 3)

---

## Correctie C1 — BaseRepository met _locatie_filter() implementeren

**Audit-ID:** Plan-afwijking 1
**Ernst:** 🔴 Structureel
**Omvang:** Groot — nieuw bestand + refactor van alle services
**Fase:** Fase 3 (start)

### Probleem

Het plan (`plan_van_aanpak_v0.9.md:682`) beschrijft een `BaseRepository` als verplicht patroon. `backend/services/repository.py` bestaat niet. Services doen momenteel ad-hoc `locatie_id`-filtering — correct, maar zonder gecentraliseerde garantie. Als een service de filter vergeet, is er geen fallback.

### Oplossing

```python
# backend/services/repository.py
from sqlalchemy.orm import Session

class BaseRepository:
    def __init__(self, db: Session, locatie_id: int | None):
        self.db = db
        self.locatie_id = locatie_id  # None = super_beheerder, geen filter

    def _locatie_filter(self, query, model):
        """Pas locatie-filter toe. Geen filter als locatie_id is None (super_beheerder)."""
        if self.locatie_id is not None:
            query = query.filter(model.locatie_id == self.locatie_id)
        return query

    def _basis_filter(self, query, model):
        """Voeg standaard soft-delete + locatie filter toe."""
        query = query.filter(model.is_actief == True)
        if hasattr(model, 'verwijderd_op'):
            query = query.filter(model.verwijderd_op.is_(None))
        return self._locatie_filter(query, model)
```

### Taken

- [ ] Maak `backend/services/repository.py` aan met `BaseRepository`
- [ ] Definieer concrete repositorieklassen: `TeamRepository`, `GebruikerRepository`, `PlanningRepository`, `VerlofRepository`
- [ ] Refactor services om repositories te gebruiken i.p.v. directe `db.query()`-aanroepen
- [ ] Documenteer het `locatie_id=None`-patroon voor super_beheerder
- [ ] Pas aan: `GebruikerService`, `PlanningService`, `VerlofService`, `TeamService`, `HRService`

---

## Correctie C2 — locatie_guard.py middleware implementeren

**Audit-ID:** Plan-afwijking 2
**Ernst:** 🔴 Structureel
**Omvang:** Middel — nieuw middleware-bestand + registratie in `main.py`
**Fase:** Fase 3 (na C1)

### Probleem

Het plan (`plan_van_aanpak_v0.9.md:692`) beschrijft `api/middleware/locatie_guard.py` als tweede vangnet voor tenant-isolatie. Het bestand bestaat niet. Als een service vergeet een `locatie_id`-filter toe te passen, is er geen fallback.

### Oplossing

```python
# backend/api/middleware/locatie_guard.py
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
import logging

logger = logging.getLogger(__name__)

class LocatieGuardMiddleware(BaseHTTPMiddleware):
    """
    Tweede vangnet voor tenant-isolatie.
    Verifieert dat de ingelogde gebruiker een locatie_id heeft
    en logt super_beheerder-bypasses in AuditLog.
    """
    _PUBLIEKE_PADEN = {"/login", "/auth/", "/health", "/static"}

    async def dispatch(self, request: Request, call_next) -> Response:
        pad = request.url.path
        if any(pad.startswith(p) for p in self._PUBLIEKE_PADEN):
            return await call_next(request)
        # Verdere implementatie in Fase 3 samen met GebruikerRol-migratie
        return await call_next(request)
```

### Taken

- [ ] Maak `backend/api/middleware/locatie_guard.py` aan
- [ ] Implementeer middleware conform CLAUDE.md-patroon
- [ ] Registreer in `backend/main.py` na `SecurityHeadersMiddleware`
- [ ] Voeg logging toe bij super_beheerder-bypasses
- [ ] Implementeer volledige locatie-validatie in Fase 3 (samen met C3)

---

## Correctie C3 — vereiste_rol() migreren naar GebruikerRol tabel

**Audit-ID:** SEC-03
**Ernst:** 🟠 Hoog
**Omvang:** Groot — `dependencies.py` + alle routers
**Fase:** Fase 3 (samen met rolmodel-werk)

### Probleem

`backend/api/dependencies.py:68-116` — `vereiste_rol()`, `vereiste_super_beheerder()`, `vereiste_beheerder_of_hoger()`, `vereiste_planner_of_hoger()`, `vereiste_hr_of_hoger()` controleren allemaal `gebruiker.rol` (het gedenormaliseerde display-veld). De architectuurregels stellen: **autorisatie altijd via `GebruikerRol`**.

De helpers `heeft_rol_in_locatie()` (regel 159) en `heeft_rol_in_team()` (regel 119) bestaan al en bevragen de `GebruikerRol`-tabel correct. Ze worden **niet** gebruikt door de centrale dependency-functies.

**Risico:** Scope-bypass — een gebruiker met `gebruiker.rol="beheerder"` voor locatie A heeft ook toegang tot locatie B als de locatie-check ontbreekt.

### Oplossing

```python
def vereiste_beheerder_of_hoger(
    gebruiker: Gebruiker = Depends(haal_huidige_gebruiker),
    db: Session = Depends(haal_db),
) -> Gebruiker:
    if not heeft_rol_in_locatie(
        gebruiker.id,
        gebruiker.locatie_id,
        ("beheerder", "super_beheerder"),
        db,
    ):
        raise HTTPException(status_code=403, detail="Onvoldoende rechten")
    return gebruiker
```

### Taken

- [ ] `backend/api/dependencies.py`: pas `vereiste_super_beheerder()` aan voor `GebruikerRol`-check
- [ ] `backend/api/dependencies.py`: pas `vereiste_beheerder_of_hoger()` aan
- [ ] `backend/api/dependencies.py`: pas `vereiste_planner_of_hoger()` aan
- [ ] `backend/api/dependencies.py`: pas `vereiste_hr_of_hoger()` aan
- [ ] `backend/api/dependencies.py`: pas de generieke `vereiste_rol()` factory aan
- [ ] Test: gebruiker met `gebruiker.rol="beheerder"` maar zonder actieve `GebruikerRol`-rij → 403
- [ ] Test: super_beheerder bypass werkt correct (scope_id → Locatie(code='NAT'))
- [ ] Voer samen uit met Fase 3 rolmodel-werk om dubbele refactoring te vermijden

---

## Groep D — Middel/Laag (kwaliteitsverbetering, doorlopend)

---

## Correctie D1 — Navigatiebalk rol-check via is_* variabelen

**Audit-ID:** SEC-09
**Ernst:** 🟡 Middel
**Omvang:** Middel — `app.html` + dashboard-router

### Taken

- [ ] Inventariseer alle `gebruiker.rol`-checks in `backend/templates/layouts/app.html`
- [ ] Voeg `is_beheerder`, `is_planner`, `is_hr`, `is_super_beheerder` toe aan de template-context in de dashboard-router
- [ ] Vervang alle `gebruiker.rol`-checks in `app.html` door de corresponderende `is_*` booleans
- [ ] Controleer overige templates op `gebruiker.rol`-checks en vervang

---

## Correctie D2 — CSP unsafe-inline → nonce-gebaseerd

**Audit-ID:** SEC-10
**Ernst:** 🟡 Middel
**Omvang:** Groot
**Geplande fase:** Fase 5/6

### Taken

- [ ] **Nu uitvoerbaar:** bereken SRI-hashes voor HTMX en Tailwind CDN-versies; voeg `integrity="sha384-..."` toe aan CDN-script-tags in `app.html`
- [ ] **Fase 5/6:** migreer naar nonce-gebaseerde CSP (nonce per request genereren in middleware, `nonce="{{ request.state.nonce }}"` op inline scripts)
- [ ] Overweeg HTMX en Tailwind te bundelen als lokale statische bestanden

---

## Correctie D3 — kaart.html | safe documentatie

**Audit-ID:** SEC-11
**Ernst:** 🟡 Middel
**Omvang:** Klein

### Taken

- [ ] `backend/templates/components/kaart.html:19`: voeg veiligheidscommentaar toe bij `{{ inhoud | safe }}`
- [ ] `backend/templates/components/formulier_veld.html:37,45,61`: veiligheidscommentaar bij `{{ extra | safe }}`
- [ ] `backend/templates/components/knop.html:31`: veiligheidscommentaar bij `{{ extra | safe }}`
- [ ] Controleer alle aanroepende templates: bevat `inhoud`/`extra` ooit gebruikersinvoer?

---

## Correctie D4 — URL querystring meldingen → vaste sleutels

**Audit-ID:** SEC-12
**Ernst:** 🟡 Middel
**Omvang:** Middel

### Probleem

Routers zoals `account.py:88`, `gebruikers.py:138`, `verlof.py:139` zetten vrije tekst (incl. `str(fout)`) in redirect-querystrings. Jinja2 escapet standaard, maar dit lekt interne foutmeldingen in URL-logs en is onprofessioneel.

### Taken

- [ ] Inventariseer alle `RedirectResponse` aanroepen met vrije tekst in querystring
- [ ] Definieer vaste foutsleutels per router (`account.fout.*`, `gebruikers.fout.*`, etc.)
- [ ] Voeg sleutels toe aan `i18n/nl.json`, `en.json`, `fr.json`
- [ ] Vervang vrije tekst in routers door vaste sleutels
- [ ] Pas templates aan om sleutels te vertalen via `t()`

---

## Correctie D5 — Ontbrekende AuditLog entries

**Audit-ID:** SEC-18
**Ernst:** ⚪ Laag
**Omvang:** Middel

### Taken

- [ ] `backend/api/routers/hr.py`: voeg `AuditLog` toe bij override aanmaken
- [ ] `backend/api/routers/hr.py`: voeg `AuditLog` toe bij override verwijderen
- [ ] `backend/api/routers/hr.py`: voeg `AuditLog` toe bij rode lijn opslaan
- [ ] `backend/api/routers/instellingen.py`: voeg `AuditLog` toe bij instelling opslaan
- [ ] `backend/api/routers/verlof.py:300-325`: voeg `AuditLog` toe bij saldo aanpassen, jaar-overdracht, 1-mei verval

---

## Verificatie na Groep A + B

```bash
# A1: geen groepen-bestanden meer
ls backend/api/routers/groepen.py 2>/dev/null && echo "BESTAAT NOG" || echo "OK"
ls backend/models/groep.py 2>/dev/null && echo "BESTAAT NOG" || echo "OK"

# A2: bleach aanwezig in help.py
grep -n "bleach" backend/api/routers/help.py

# A3: max_age aanwezig op toegangs_token cookie (beide plekken)
grep -c "max_age" backend/api/routers/auth.py  # verwacht: >= 2

# A4: HSTS header aanwezig
grep -n "Strict-Transport-Security" backend/api/middleware/security_headers.py

# A5: geen hardcoded wachtwoord in seed.py
grep -n "Admin1234" backend/api/seed.py  # verwacht: geen output

# A6: health endpoint zonder versie/omgeving in productie
grep -n "omgeving" backend/api/routers/health.py

# A7: CF-Connecting-IP in rate_limiter
grep -n "CF-Connecting-IP" backend/api/rate_limiter.py

# B1: geen integer gebruiker_id in planning/override
grep -n "gebruiker_id.*int.*Form" backend/api/routers/planning.py  # verwacht: geen output

# B2: csrf_token in totp foutantwoord
grep -n "csrf_token" backend/api/routers/auth.py  # verwacht: meerdere hits incl. foutpad
```

Doel: alle commando's geven het verwachte resultaat.
