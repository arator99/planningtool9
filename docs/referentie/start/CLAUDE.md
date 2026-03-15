# CLAUDE.md — Planning Tool v0.8

Context en werkinstructies voor AI-assistenten die aan dit project werken.

---

## 1. Wat is dit project?

Planning Tool v0.8 is een **web-migratie** van een volwassen PyQt6/SQLite desktop applicatie (v0.7, ~52 versies). Het doel is dezelfde planningsfunctionaliteit aanbieden via een browser, zonder de business logica opnieuw uit te vinden.

**Stack:**
- **Backend:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.x ORM
- **Database:** PostgreSQL 16 (via Docker)
- **Templates:** Jinja2 3.1 + HTMX 1.9 (server-side rendering, geen SPA)
- **Styling:** Tailwind CSS (CDN) + CSS custom properties voor light/dark theming
- **Auth:** JWT (httpOnly cookie) + TOTP 2FA (pyotp)
- **Migraties:** Alembic

**Taal:** Alles is in het **Nederlands** — variabelenamen, functies, templates, commentaar, foutmeldingen.

---

## 2. Projectstructuur

```
v08/
├── CHANGELOG.md                    ← versiehistorie
├── CLAUDE.md                       ← dit bestand
├── docker-compose.yml              ← PostgreSQL + app containers
├── .env                            ← lokale omgevingsvariabelen (niet in git)
├── .env.example                    ← template voor .env
├── voorstellen/                    ← ruwe ideeën, nog niet goedgekeurd
├── plannen/
│   └── feature_gap_stappenplan.md  ← roadmap: welke features nog ontbreken
├── archief/                        ← voltooide plannen (historiek)
└── backend/
    ├── main.py                     ← FastAPI app, lifespan, router registratie, seed
    ├── config.py                   ← Instellingen via pydantic-settings (.env)
    ├── database.py                 ← SQLAlchemy engine + SessieKlasse + Basis
    ├── stijlen.py                  ← CSS thema generatie (light/dark variabelen)
    ├── requirements.txt
    ├── Dockerfile
    ├── alembic.ini
    ├── migrations/                 ← Alembic migratiescripts
    ├── api/
    │   ├── dependencies.py         ← haal_db, haal_huidige_gebruiker, vereiste_rol
    │   ├── sjablonen.py            ← Jinja2Templates instantie + globals
    │   └── routers/
    │       ├── auth.py             ← /login, /auth/uitloggen, /totp/*
    │       ├── account.py          ← /account/wachtwoord
    │       ├── gebruikers.py       ← /beheer/gebruikers (CRUD)
    │       ├── planning.py         ← /planning (grid, cel, publiceer, valideer, override)
    │       ├── verlof.py           ← /verlof (aanvragen, goedkeuren, weigeren)
    │       ├── shiftcodes.py       ← /shiftcodes (CRUD)
    │       ├── hr.py               ← /hr (HR regels + rode lijn)
    │       ├── notities.py         ← /notities (inbox, verzenden, gelezen)
    │       ├── rapporten.py        ← /rapporten (maandgrid, CSV)
    │       └── health.py           ← /health
    ├── models/
    │   ├── groep.py                ← Groep, GroepConfig
    │   ├── gebruiker.py            ← Gebruiker
    │   ├── planning.py             ← Werkpost, Shiftcode, ShiftTijd, Planning,
    │   │                               SpecialCode, PlanningOverride
    │   ├── hr.py                   ← HRRegel, RodeLijn
    │   ├── verlof.py               ← VerlofAanvraag
    │   ├── notitie.py              ← Notitie
    │   ├── competentie.py          ← Competentie, GebruikerCompetentie
    │   ├── audit_log.py            ← AuditLog
    │   └── notificatie.py          ← Notificatie
    ├── services/
    │   ├── auth_service.py         ← AuthService: login, token, 2FA, wachtwoord
    │   ├── gebruiker_service.py    ← GebruikerService: CRUD
    │   ├── planning_service.py     ← PlanningService: grid, UPSERT, publiceer
    │   ├── verlof_service.py       ← VerlofService: aanvragen, beheer
    │   ├── shiftcode_service.py    ← ShiftcodeService: CRUD
    │   ├── hr_service.py           ← HRService: regels + rode lijn
    │   ├── notitie_service.py      ← NotitieService: inbox, verzenden
    │   ├── rapport_service.py      ← RapportService: maandgrid, verlofoverzicht
    │   ├── validatie_service.py    ← ValidatieService: 7 HR validators
    │   └── domein/                 ← "Domein laag": pure Python, geen SQLAlchemy
    │       (nog leeg — wordt gevuld naarmate services complexer worden)
    ├── schemas/
    │   ├── auth.py                 ← Pydantic schemas voor auth
    │   └── gebruiker.py            ← Pydantic schemas voor gebruikers
    ├── templates/
    │   ├── layouts/
    │   │   └── app.html            ← Hoofd layout: navbar, dark mode, account dropdown
    │   ├── pages/
    │   │   ├── dashboard.html
    │   │   ├── login.html
    │   │   ├── account/wachtwoord.html
    │   │   ├── gebruikers/         ← lijst.html, formulier.html, wachtwoord.html
    │   │   ├── planning/
    │   │   │   ├── maand.html      ← planning grid + valideer knop + cel-markers
    │   │   │   └── _validatie_paneel.html  ← HTMX fragment: foutenpaneel
    │   │   ├── verlof/             ← lijst.html, formulier.html
    │   │   ├── shiftcodes/         ← lijst.html, formulier.html
    │   │   ├── hr/                 ← lijst.html, formulier.html
    │   │   ├── notities/           ← lijst.html (inbox + verzonden)
    │   │   └── rapporten/          ← index.html
    │   └── partials/               ← herbruikbare HTML-stukken
    └── scripts/
        └── migreer_sqlite.py       ← eenmalig: v0.7 SQLite → v0.8 PostgreSQL
```

---

## 3. Starten en draaien

### Omgevingen

| Omgeving | URL | Hoe |
|----------|-----|-----|
| Lokaal | `http://localhost:8000` | `docker compose up` op ontwikkelmachine |
| NAS (LAN) | `http://192.168.0.6:8000` | Docker op Synology NAS, altijd actief |
| Online | `https://planningtool.org` | Cloudflare Tunnel vanaf NAS, geen open poorten |

De NAS en online omgeving draaien dezelfde `docker-compose.yml`. De Cloudflare Tunnel draait als aparte container naast de app en maakt een uitgaande verbinding naar Cloudflare — er hoeven geen poorten open gezet te worden op de router.

Bestanden op de NAS staan in `/volume1/docker/planningtool/`. Wijzigingen deployen:
```bash
# Bestand uploaden via SSH (geen SFTP beschikbaar op deze NAS)
cat lokaal/bestand.py | ssh bob@192.168.0.6 "cat > /volume1/docker/planningtool/backend/pad/bestand.py"

# Container herstarten
ssh bob@192.168.0.6 "/usr/local/bin/docker-compose -f /volume1/docker/planningtool/docker-compose.yml restart app"
```

> **Let op:** de NAS heeft een ingebouwde PostgreSQL service die poort 5432 bezet. De `docker-compose.yml` mapt die poort daarom **niet** naar de host — de app container bereikt de db-container intern via het Docker netwerk.

### Lokaal starten

```bash
cd v08
docker compose up --build
```

API docs (development only): `http://localhost:8000/api/docs`

### Dependency lock-bestand

Na elke wijziging aan `requirements.txt` een lock-bestand genereren voor reproduceerbare builds:
```bash
pip freeze > requirements.lock
```

Het `docker-compose.override.yml` zorgt voor live code-mount op de ontwikkelmachine. Op de NAS wordt dit override-bestand **niet** gebruikt — de container draait op het gebouwde image.

### Standaard testaccount (automatisch aangemaakt bij lege DB)

| Veld | Waarde |
|------|--------|
| Gebruikersnaam | `admin` |
| Wachtwoord | `Admin1234!` |
| Rol | beheerder |
| Groep | Groep 1 (GRP1) |

### Omgevingsvariabelen (`.env`)

```
DATABASE_URL=postgresql://planningtool:planningtool_secret@db:5432/planningtool
GEHEIME_SLEUTEL=<willekeurige lange string>
TOEGANGS_TOKEN_VERLOPEN_MINUTEN=30
OMGEVING=development
APP_VERSIE=0.8.0
```

---

## 4. Architectuur & patronen

### Gelaagd model

v0.8 hanteert een strikte 3-laagse architectuur, overgenomen van v0.7 en vertaald naar de web-stack. **Dit is de meest kritieke regel van de codebase — nooit omzeilen.**

```
┌─────────────────────────────────────────────────────────────┐
│  Browser / HTMX                                              │
└───────────────────────┬─────────────────────────────────────┘
                        ↓ HTTP request
┌─────────────────────────────────────────────────────────────┐
│  api/routers/              ← Laag 1: HTTP-afhandeling        │
│  Dun. Alleen: request parsen, auth check, service aanroepen, │
│  template renderen. GEEN business logica. GEEN db.query().   │
└───────────────────────┬─────────────────────────────────────┘
                        ↓ roept aan
┌─────────────────────────────────────────────────────────────┐
│  services/                 ← Laag 2: Use case orchestratie   │
│  Coördineert: DB lezen/schrijven + domeinlogica aanroepen.   │
│  Mag: models/ importeren, services/domein/ aanroepen.        │
│  GEEN: business rules, GEEN rechtstreekse berekeningen.      │
└──────────────┬──────────────────────────┬───────────────────┘
               ↓                          ↓
┌──────────────────────┐    ┌─────────────────────────────────┐
│  services/domein/    │    │  models/ + SQLAlchemy ORM        │
│  Laag 3a: Domein     │    │  Laag 3b: Data access            │
│  Pure Python.        │    │  ORM doet object mapping.        │
│  Geen SQLAlchemy.    │    │  Geen business logica.           │
│  Geen models import. │    │                                  │
└──────────────────────┘    └─────────────────────────────────┘
```

### Dependency regels (hard, nooit omzeilen)

| Van | Mag importeren uit | Verboden |
|-----|--------------------|---------|
| `api/routers/` | `services/` | `models/`, `services/domein/`, directe `db.query()` |
| `services/` | `models/`, `services/domein/`, `config` | `api/`, andere services\* |
| `services/domein/` | Python stdlib, `config` | `models/`, `services/`, SQLAlchemy |
| `models/` | SQLAlchemy Basis, andere models | `services/`, `api/` |

\* Services mogen **niet** elkaars methoden aanroepen. Als data van twee services gecombineerd moet worden, doet de router dat (twee aparte service-aanroepen) of komt er een nieuwe service.

### Wat hoort waar?

**Laag 1 — Router** (`api/routers/xxx.py`):
```python
@router.post("/verlof")
def maak_aanvraag(request, start: date = Form(...), ..., gebruiker = Depends(...), db = Depends(...)):
    aanvraag = VerlofService(db).maak_aanvraag(gebruiker.id, gebruiker.groep_id, start, ...)
    return sjablonen.TemplateResponse("...", {...})
```

**Laag 2 — Service** (`services/xxx_service.py`):
```python
def maak_aanvraag(self, gebruiker_id, groep_id, start_datum, eind_datum, ...):
    valideer_verlof_periode(start_datum, eind_datum)       # ← domeinlaag
    aantal = bereken_verlof_dagen(start_datum, eind_datum) # ← domeinlaag
    aanvraag = VerlofAanvraag(...)                          # ← ORM
    self.db.add(aanvraag)
    self.db.commit()
```

**Laag 3a — Domein** (`services/domein/xxx_domein.py`):
```python
def valideer_verlof_periode(start: date, eind: date) -> None:
    if eind < start:
        raise ValueError("Einddatum mag niet voor startdatum liggen.")

def bereken_verlof_dagen(start: date, eind: date) -> int:
    return (eind - start).days + 1
```

### Bestaande domeinmodules

| Module | Bevat |
|--------|-------|
| `planning_domein.py` | `SHIFT_TYPE_CONFIG`, `MAAND_NAMEN`, `DAG_NAMEN`, `RUST_CODES`, `STANDBY_CODES`, `bouw_dag_info()`, `bereken_navigatie()`, `groepeer_shiftcodes()` |
| `auth_domein.py` | `hash_wachtwoord()`, `verifieer_wachtwoord()`, `valideer_wachtwoord_sterkte()`, `maak_access_token()`, `maak_totp_temp_token()`, `verifieer_access_token()`, `verifieer_totp_temp_token()` |
| `gebruiker_domein.py` | `GEBRUIKERSNAAM_PATROON`, `valideer_gebruikersnaam_formaat()` |
| `verlof_domein.py` | `BEHANDELAAR_ROLLEN`, `valideer_verlof_periode()`, `bereken_verlof_dagen()` |
| `validatie_domein.py` | `ValidatieFout`, 6 shift-helpers, 7 validators als pure functies, `VALIDATORS` register, `sorteer_fouten()` |
| `rapport_domein.py` | `bouw_csv_inhoud()`, `groepeer_verlof_per_medewerker()` |
| `shiftcode_domein.py` | `SHIFT_TYPES`, `DAG_TYPES`, `normaliseer_shiftcode()` |
| `hr_domein.py` | `ERNST_NIVEAUS`, `valideer_ernst_niveau()`, `valideer_interval_dagen()` |
| `notitie_domein.py` | `PRIORITEITEN`, `valideer_bericht()`, `valideer_prioriteit()` |

### Wat hoort in de domeinlaag?

Verplaats naar `services/domein/` als de code:
- Alleen Python stdlib (+ eventueel `config.instellingen`) nodig heeft
- Geen `db: Session` nodig heeft
- Puur berekent, valideert of transformeert
- Herbruikbaar is door meerdere services of toekomstige Fase-features

Typische kandidaten: validators, berekeningen (FIFO, uren, saldo), constanten die door meerdere services gebruikt worden, data-transformaties (CSV, groepering).

**Nieuwe features checklist voor de domeinlaag:**
- Fase 2 FIFO-berekening → `services/domein/verlof_domein.py` uitbreiden
- Fase 4 balansberekening → `services/domein/balans_domein.py`
- Fase 5 auto-scheduling scoring → `services/domein/suggestie_domein.py`

### Request flow (concreet)

```
Browser → FastAPI Router → Service → SQLAlchemy ORM → PostgreSQL
                       ↓ (bij complexe logica)
               services/domein/ (pure berekeningen)
                       ↓
               Jinja2 Template → HTML response
```

### Strategie: kopieer domeinlogica uit v0.7

De domeinlaag (`services/domein/`) is per definitie framework-agnostisch — pure Python zonder SQLite, SQLAlchemy of PyQt6. De v0.7 codebase bevat jaren aan bewezen, geteste business logica. **Herschrijf die niet — kopieer ze.**

**Wat kan direct overgenomen worden uit v0.7:**

| v0.8 domeinmodule | Zoek in v0.7 |
|---|---|
| Validators, HR-regels | `src/services/domein/hr_validators.py`, `docs/referentie/hr_validatie.md` |
| FIFO-verlofberekening (Fase 2) | `docs/plannen/plan_fifo_verlof_saldo.md` + verlof-service |
| Balansberekening (Fase 4) | Rapportage-service v0.7 |
| Auto-scheduling scoring (Fase 5) | `src/services/domein/suggestie_service.py` — niet herschrijven |
| Datumvalidatie, dagberekeningen | Verlof- en planningservice v0.7 |

**Wat niet overgenomen kan worden** (framework-specifiek):

| Laag | Reden |
|------|-------|
| `api/routers/` | Bestond niet — was PyQt6 event handlers |
| `services/` (applicatielaag) | Data access was raw SQLite, niet SQLAlchemy ORM |
| `models/` | SQLAlchemy ORM bestaat niet in v0.7 |
| Templates | Was PyQt6 widgets, nu Jinja2/HTMX |

**Werkwijze bij nieuwe fases:**
1. Zoek de v0.7 implementatie op via `docs/referentie/` of in `src/services/`
2. Kopieer de pure Python logica naar `services/domein/xxx_domein.py`
3. Pas alleen de datafeed aan (v0.7 gebruikt `dict` uit SQLite, v0.8 geeft ORM-objecten mee)
4. Schrijf alleen de service (ORM-queries) en router opnieuw

Zo begin je met bewezen logica in plaats van edge cases opnieuw te ontdekken.

### Multi-tenant via `groep_id`

Elke query filtert op `groep_id` van de ingelogde gebruiker. Nooit cross-groep data teruggeven. De `groep_id` zit op: `Gebruiker`, `Planning`, `Shiftcode`, `HRRegel`, `RodeLijn`, `VerlofAanvraag`, `Notitie`, `Werkpost`.

### Authenticatie

- JWT opgeslagen als httpOnly cookie `toegangs_token`
- Dependency: `vereiste_rol("beheerder", "planner")` → geeft `Gebruiker` terug of HTTP 403
- Dependency: `vereiste_login` → elke ingelogde gebruiker (alle rollen)
- Dependency: `haal_db` → geeft SQLAlchemy `Session` terug, sluit na request

### HTMX patronen

- Cel opslaan: `hx-post` met `hx-swap="none"` → 204 No Content (geen DOM update)
- Validatiepaneel: `hx-get` op `#validatie-paneel` → server stuurt HTML fragment terug
- Override formulier: `hx-post` → server hervalideert en stuurt bijgewerkt paneel terug
- HTMX fragmenten (partiële templates) staan in `templates/pages/*/` met `_` prefix

### Theming

`stijlen.py` genereert een CSS-blok met custom properties (`--primair`, `--tekst`, `--achtergrond`, etc.) voor zowel light als dark mode. Gebruik **altijd** `style="color: var(--tekst);"` in templates, nooit hardcoded kleuren.

---

## 5. Modellen — belangrijke velden

### `Gebruiker`
- `rol`: `"beheerder"` | `"planner"` | `"hr"` | `"medewerker"`
- `groep_id`: FK naar `Groep`
- `totp_actief`: bool
- `is_actief`: bool — inactieve gebruikers worden gefilterd in planning queries

### `Shiftcode`
- `shift_type`: `"vroeg"` | `"laat"` | `"nacht"` | `"dag"` | `None`
- `is_kritisch`: bool — kritieke shifts moeten altijd bezet zijn (validatie)
- `start_uur` / `eind_uur`: `"HH:MM"` formaat, `None` voor rustcodes

### `Planning`
- `datum`: `date`
- `shift_code`: string (code van de shiftcode, bijv. `"D"`, `"N"`, `"RXW"`)
- `is_gepubliceerd`: bool
- Uniek: `(groep_id, gebruiker_id, datum)`
- Relatie: `overrides` → lijst van `PlanningOverride`

### `PlanningOverride`
- Koppelt aan `planning_shift_id` (FK naar `Planning.id`)
- `regel_code`: bijv. `"MAX_DAGEN_OP_RIJ"`, `"MIN_RUSTTIJD"`, ...
- `reden_afwijking`: tekst ingegeven door planner
- `goedgekeurd_door`: FK naar `Gebruiker.id`

### `HRRegel`
- `code`: bijv. `"MAX_DAGEN_OP_RIJ"`, `"NACHT_OPVOLGING"`, `"MAX_WEEKENDS_OP_RIJ"`, `"RODE_LIJN_MAX_WERK"`, `"MAX_UREN_PER_WEEK"`, `"MIN_RUSTTIJD"`, `"KRITIEKE_SHIFT"`
- `waarde`: numerieke drempelwaarde (bijv. 7 voor max dagen op rij)
- `ernst_niveau`: `"INFO"` | `"WARNING"` | `"CRITICAL"`
- `groep_id`: per groep configureerbaar

### `RodeLijn`
- `start_datum`: begin van de eerste cyclus
- `interval_dagen`: typisch 28 dagen
- `groep_id`

---

## 6. i18n — Meertaligheid

### Architectuur

Vertalingen staan in JSON-bestanden onder `backend/i18n/`:

| Bestand | Inhoud |
|---------|--------|
| `i18n/nl.json` | Master vertaalbestand — alle sleutels verplicht aanwezig |
| `i18n/fr.json` | Frans — ontbrekende sleutels vallen terug op Nederlands |
| `i18n/en.json` | Engels — ontbrekende sleutels vallen terug op Nederlands |

De module `i18n/__init__.py` biedt drie functies:

```python
from i18n import vertaal, maak_vertaler

vertaal("nav.planning", "fr")        # → "Planning" (directe aanroep)
t = maak_vertaler("fr")              # → gebonden functie
t("nav.planning")                    # → "Planning"
```

Bestanden worden lazy geladen met `@lru_cache` — na wijzigen van een JSON-bestand is een container restart nodig.

### Gebruik per context

**In routers** — elke `_context()` functie geeft `t` mee:
```python
from i18n import maak_vertaler

def _context(request, gebruiker, **extra):
    return {"request": request, "gebruiker": gebruiker,
            "t": maak_vertaler(gebruiker.taal if gebruiker else "nl"), **extra}
```

**In templates (ingelogde pagina's)** — gebruik altijd `t()`:
```jinja2
{{ t("nav.planning") }}
{{ t("algemeen.opslaan") }}
```

**In `layouts/app.html`** — ook `t()`, want alle authenticated routers geven `t` mee via `_context()`.

**In `main.py` (dashboard)** — expliciete `t` meegeven:
```python
from i18n import maak_vertaler
{"t": maak_vertaler(gebruiker.taal or "nl"), ...}
```

**Op de loginpagina** (geen ingelogde gebruiker) — gebruik `t_global`:
```jinja2
{{ t_global("auth.inloggen", geselecteerde_taal) }}
```
`t_global` is een Jinja2 global ingesteld in `api/sjablonen.py`. Voor JavaScript op de loginpagina: bouw een dict in de router en geef mee via `| tojson` (voorkomt HTML-escaping van apostrofs):
```python
# router
from i18n import vertaal
js_vertalingen = {code: {"sleutel": vertaal("auth.sleutel", code)} for code in ["nl","fr","en"]}
# template
const vertalingen = {{ js_vertalingen | tojson }};
```

### Sleutelstructuur

| Prefix | Gebruik |
|--------|---------|
| `nav.*` | Navigatiekoppelingen en menu-items |
| `algemeen.*` | Knoppen, labels, statussen die overal voorkomen |
| `auth.*` | Login, wachtwoord, 2FA |
| `rol.*` | Rolnamen (beheerder, planner, hr, medewerker) |
| `taal.*` | Taalnamen |
| `dashboard.*` | Dashboard-specifieke teksten |
| `verlof.*` | Verlofmodule |
| `planning.*` | Planningmodule |
| `gebruiker.*` | Gebruikersbeheer |
| `shiftcode.*` | Shiftcodes |
| `hr.*` | HR Regels |
| `rapport.*` | Rapporten |
| `werkpost.*` | Werkposten |
| `competentie.*` | Competenties |
| `fout.*` | Foutmeldingen |

### Regels

- **Nooit hardcoded strings** in templates die al via `t()` beschikbaar zijn
- **Altijd eerst toevoegen aan `nl.json`** — daarna optioneel aan `fr.json` en `en.json`
- **Ontbrekende sleutels** in fr/en vallen automatisch terug op Nederlands — geen lege strings invullen
- **Nieuwe module** → voeg een nieuw prefix-blok toe aan alle drie de JSON-bestanden

---

## 7. ValidatieService

`services/validatie_service.py` — HR validatie engine met 7 validators:

| Validator | HR Regel code | Standaard |
|-----------|--------------|-----------|
| `_kritieke_shifts` | `KRITIEKE_SHIFT` | altijd CRITICAL |
| `_max_dagen_op_rij` | `MAX_DAGEN_OP_RIJ` | max 7 dagen |
| `_nachtshift_opvolging` | `NACHT_OPVOLGING` | verboden |
| `_max_weekends_op_rij` | `MAX_WEEKENDS_OP_RIJ` | max 6 weekenden |
| `_rode_lijn` | `RODE_LIJN_MAX_WERK` | max 19/28 dagen |
| `_max_uren_week` | `MAX_UREN_PER_WEEK` | max 50 uur |
| `_min_rusttijd` | `MIN_RUSTTIJD` | min 11 uur |

- **Lookback:** 14 dagen vóór de doelmaand worden meegeladen voor cross-maand detectie
- **Return:** gesorteerde lijst van `ValidatieFout` (CRITICAL eerst, dan datum)
- **Overrides:** `ValidatieService.maak_override()` schrijft naar `PlanningOverride`

---

## 8. Nieuwe feature toevoegen — checklist

1. **Idee** → maak een notitie in `v08/voorstellen/` als het niet triviaal is
2. **Model** (indien nieuwe tabel): `models/<naam>.py`, erft van `Basis`. Registreer in `models/__init__.py`.
3. **Domeinlogica** (indien complexe berekeningen): pure functies of dataclasses in `services/domein/<naam>_domein.py`. Geen SQLAlchemy imports.
4. **Service**: `services/<naam>_service.py`. Klasse die `db: Session` ontvangt in `__init__`. Stateless. Roept ORM + domeinlaag aan. Type hints verplicht.
5. **Router**: `api/routers/<naam>.py`. Gebruik `vereiste_rol(...)` of `vereiste_login`. Filter altijd op `groep_id`. Geen business logica, geen directe `db.query()`. Voeg `_context()` toe met `t = maak_vertaler(gebruiker.taal or "nl")`.
6. **Registreer router** in `main.py` via `app.include_router(...)`.
7. **i18n**: voeg alle nieuwe UI-strings toe aan `i18n/nl.json` onder een passend prefix. Voeg vertalingen toe aan `fr.json` en `en.json` waar mogelijk (ontbrekende sleutels vallen terug op Nederlands).
8. **Template**: `templates/pages/<module>/`. Extend `layouts/app.html`. Stel `actief_menu` in. Gebruik `t("sleutel")` voor alle teksten — geen hardcoded strings.
9. **Security** (zie sectie 11 voor details):
   - GET-handlers met formulier: `csrf_token: str = Depends(haal_csrf_token)` + meegeven aan context
   - POST-handlers: `_csrf: None = Depends(verifieer_csrf)`
   - Templates: `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">` in elke form
   - HTMX-knoppen zonder form: `hx-vals='{"csrf_token": "{{ csrf_token }}"}'`
   - Foutmeldingen in redirects: vaste codes, nooit `fout={fout}`
10. **Navbar link** toevoegen in `templates/layouts/app.html` (met rolcontrole indien nodig).
11. **Plan afgerond** → verplaats naar `v08/archief/`

### Error handling patroon (identiek aan v0.7)

```python
# Service: gooit exceptions
def sla_shift_op(self, ...):
    if not geldige_code:
        raise ValueError("Ongeldige shiftcode.")
    ...

# Router: vangt op, stuurt HTTP response
try:
    PlanningService(db).sla_shift_op(...)
except ValueError as fout:
    return templates.TemplateResponse("...", {"fout": str(fout)})
```

### Documentatieflow

Identiek aan v0.7: **`voorstellen/` → `plannen/` → `archief/`**

| Map | Inhoud | Wanneer |
|-----|--------|---------|
| `v08/voorstellen/` | Ruwe ideeën, RFC's, nog niet goedgekeurd | Bij nieuw idee |
| `v08/plannen/` | Goedgekeurde blauwdrukken, in uitvoering | Na akkoord |
| `v08/archief/` | Voltooide plannen, historiek | Na implementatie |

---

## 9. Referentiedocumentatie

| Document | Locatie | Inhoud |
|----------|---------|--------|
| Feature roadmap | `v08/plannen/feature_gap_stappenplan.md` | Fases 1–7, prioriteiten, afhankelijkheden |
| Changelog | `v08/CHANGELOG.md` | Wat is al gebouwd per versie |
| v0.7 DB schema | `docs/referentie/database_schema.md` | Alle v0.7 tabellen — nuttig als referentie voor business logica |
| v0.7 Services API | `docs/referentie/services_api.md` | Alle v0.7 service methodes — blauwdruk voor v0.8 services |
| v0.7 HR validatie | `docs/referentie/hr_validatie.md` | Gedetailleerde uitleg van alle validators |
| v0.7 Blueprint | `docs/blueprint_master.md` | Architectuuroverzicht van v0.7 |
| v0.8 Architectuur | `docs/voorstellen/Blueprint_v0.8.md` | Web architectuurplan |
| FIFO Verlof Saldo | `docs/plannen/plan_fifo_verlof_saldo.md` | **Blauwdruk voor Fase 2** — FIFO logica, gesplitste weergave, 3 testscenario's |
| Validatie Context | `docs/plannen/plan_validatie_context.md` | Referentie voor lookback-venster validators (geïmplementeerd in v0.7, deels in v0.8) |

> **Tip:** De v0.7 referentiedocumenten (in `docs/`) zijn de beste bron voor business logica die nog geïmplementeerd moet worden. Ze beschrijven hoe de validators, berekeningen en workflows werken in de volwassen versie.

---

## 10. Bestandsgrootte richtlijnen

De architectuur van v0.8 splitst verantwoordelijkheden al van nature (router / service / template). Splits alleen op als er een **logische grens** is, niet om de regel te halen.

| Laag | Richtlijn | Signaal om te splitsen |
|------|-----------|------------------------|
| `api/routers/*.py` | max ~200 regels | Route-handler bevat business logica |
| `services/*.py` | max ~400 regels | Service behandelt meerdere losstaande onderwerpen |
| `models/*.py` | max ~150 regels | Model bevat > 5 klassen of business logica |
| `templates/pages/*.html` | max ~200 regels | Template bevat herbruikbare blokken → `{% include %}` |

**Hoe splitsen per laag:**
- **Router te groot** → logica verplaatsen naar service, niet de router opdelen
- **Service te groot** → aparte module per domeingroep (bijv. `validatie/validators.py`)
- **Template te groot** → Jinja2 `{% include 'partials/_naam.html' %}` voor herbruikbare stukken

---

## 11. Security — vereisten en patronen

### CSRF-beveiliging

**Alle** state-muterende POST-endpoints zijn CSRF-beschermd via het synchronizer token pattern (`itsdangerous`). Dit is verplicht voor elke nieuwe POST-handler.

**Patroon voor een nieuwe route met formulier:**

```python
# GET-handler: genereer token en geef mee aan template
@router.get("/iets/nieuw", response_class=HTMLResponse)
def toon_formulier(
    request: Request,
    gebruiker: Gebruiker = Depends(vereiste_login),
    csrf_token: str = Depends(haal_csrf_token),   # ← verplicht
):
    return sjablonen.TemplateResponse("...", _context(request, gebruiker, csrf_token=csrf_token))

# POST-handler: valideer token
@router.post("/iets/nieuw")
def verwerk_formulier(
    ...,
    _csrf: None = Depends(verifieer_csrf),   # ← verplicht
):
    ...
```

**Patroon voor template (formulier):**
```html
<form method="post" action="/iets/nieuw">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <!-- overige velden -->
</form>
```

**Patroon voor HTMX-knoppen zonder `<form>`:**
```html
<button hx-post="/iets/actie"
        hx-vals='{"csrf_token": "{{ csrf_token }}"}'>
    Actie
</button>
```

**Uitzonderingen (bewust geen CSRF):**
- `POST /auth/inloggen` — geen ingelogde gebruiker aanwezig
- `POST /auth/totp/verifieer` — gebruikt `totp_temp_token`, nog geen `toegangs_token`

**Imports:**
```python
from api.dependencies import haal_csrf_token, verifieer_csrf
```

---

### Rate limiting

Login-endpoints zijn beschermd via `slowapi`. Gebruik `@limiter.limit(...)` op gevoelige endpoints:

```python
from api.rate_limiter import limiter

@router.post("/gevoelig-endpoint")
@limiter.limit("5/minute")
def handler(request: Request, ...):
    ...
```

`request: Request` moet altijd aanwezig zijn als parameter bij rate-limited handlers.

---

### Redirect-URLs en foutmeldingen

Zet **nooit** vrije tekst van een exception rechtstreeks in een redirect-URL. Gebruik vaste foutcodes en log intern:

```python
# ✗ Fout:
except ValueError as fout:
    return RedirectResponse(url=f"/pagina?fout={fout}", status_code=303)

# ✓ Correct:
except ValueError as fout:
    logger.warning("Actie mislukt: %s", fout)
    return RedirectResponse(url="/pagina?fout=actie_mislukt", status_code=303)
```

---

### Security headers

`SecurityHeadersMiddleware` in `main.py` zet automatisch op elke response:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Content-Security-Policy` (alleen in productie)

Geen actie nodig in routers — werkt automatisch.

---

### Sessiecookies

Cookies worden gezet via `_SECURE = instellingen.omgeving != "development"`:
- Sessiecookies (`toegangs_token`, `totp_temp_token`): `samesite="strict"`, `secure=_SECURE`
- Taalcookie: `samesite="lax"`, `secure=_SECURE`

---

### Nieuwe router checklist (security)

Bij elke nieuwe router met POST-formulieren:
1. `csrf_token: str = Depends(haal_csrf_token)` toevoegen aan GET-handlers
2. `"csrf_token": csrf_token` meegeven aan template context
3. `_csrf: None = Depends(verifieer_csrf)` toevoegen aan POST-handlers
4. `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">` in elke `<form method="post">`
5. `hx-vals='{"csrf_token": "{{ csrf_token }}"}'` op HTMX-knoppen zonder form
6. Vaste foutcodes in redirect-URLs, geen vrije tekst

---

## 12. Guardrails 🚫

- **Geen cross-groep queries** — filter altijd op `groep_id` van de ingelogde gebruiker
- **Geen hardcoded kleuren** in templates — gebruik CSS custom properties (`var(--primair)`, etc.)
- **Geen SQL buiten services** — routers mogen alleen services aanroepen, nooit direct `db.query()`
- **Geen nieuwe dependencies** toevoegen aan `requirements.txt` zonder expliciet akkoord
- **Geen placeholders** — schrijf werkende code, geen `# TODO: implementeer dit`
- **Geen threading** — FastAPI is async, gebruik geen extra threads
- **Altijd `groep_id` meegeven** bij aanmaken van nieuwe records
- **Geen vrije tekst in redirect-URLs** — gebruik vaste foutcodes, log intern

---

## 13. v0.7 UI Pariteit

Bij implementatie van elk nieuw of bestaand scherm: **controleer eerst `v08/referentie/v07_ui_features.md`** en neem alle filters, zoekfuncties, bulk-acties en footer-statistieken mee.

### Checklist per scherm (verplicht)
- Zoekbalk aanwezig indien v0.7 dit had
- Status-tabs / rol-filter aanwezig indien v0.7 dit had
- Footer-statistieken (aantallen) aanwezig
- Bulk-acties aanwezig voor behandelaar-schermen
- Maandnavigatie (vorige/volgende) aanwezig op kalender/grid-schermen

### Status per scherm

| Scherm | URL | Filters | Bulk | Footer |
|--------|-----|---------|------|--------|
| Gebruikers lijst | `/beheer/gebruikers` | ✅ zoek + rol + status | — | ✅ actieve teller |
| Verlof lijst | `/verlof` | ✅ status tabs | ✅ bulk goedkeuren | — |
| Verlof overzicht | `/verlof/overzicht` | ✅ maandnavigatie | — | ✅ capaciteitsrij |
| Notities | `/notities` | ✅ inbox filter | — | — |
| Shiftcodes | `/shiftcodes` | ✅ zoekbalk (JS) | — | — |
| Werkposten | `/werkposten` | ✅ zoekbalk (JS) | — | — |

---

## 14. Wat nog niet geïmplementeerd is

Zie `v08/plannen/feature_gap_stappenplan.md` voor het volledige overzicht. Samenvatting:

| Fase | Feature | Status |
|------|---------|--------|
| 1 | HR Validatie Engine | ✅ Gereed |
| 2 | Verlof Saldo & FIFO | ✅ Gereed |
| 3 | Werkposten & Competenties | ✅ Gereed |
| 4 | Balans Monitor | ✅ Gereed |
| 5 | Auto-Scheduling Systeem | ✅ Gereed |
| 6 | Excel Export + uitgebreide rapporten | ✅ Gereed |
| 7 | UX Polish (badge, Mijn Planning, Logboek, Instellingen, Voorkeuren) | ✅ Gereed |
