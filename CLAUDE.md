# Planningtool v0.9 — Claude-gids

## Wat is dit project?

Webgebaseerde planningsapp voor een bedrijf met ~10 productielocaties verdeeld over 5 area's. Gebruikers plannen shifts, vragen verlof aan, en communiceren via een interne mailbox. De app draait op een Synology NAS via Docker Compose, bereikbaar via Cloudflare Tunnel.

**Strategie:** `code_v07/src/services/` = **primaire bron** voor businesslogica (port naar SQLAlchemy + FastAPI). `code_v08/backend/` = **infrastructuurreferentie** (Docker, Alembic, JWT-auth, FastAPI-patronen).
**Volledige plan:** `docs/plannen/plan_van_aanpak_v0.9.md`

## Werkwijze — plannen en voortgang

- Plannen die taken bevatten gebruiken **Markdown-checkboxes** (`- [ ]` / `- [x]`)
- **Vink taken af zodra ze afgewerkt zijn** — update `docs/plannen/plan_van_aanpak_v0.9.md` direct na voltooiing, niet achteraf in bulk
- Gebruik `- [x]` voor volledig afgeronde taken; laat `- [ ]` staan voor deels gedaan of nog te doen
- Huidige voortgang: **v0.9.0 afgerond, v0.9.1 gestart** — nu in testfase (bugs opsporen en oplossen)

### Documentatieflow

```
Nieuw idee of RFC  →  docs/voorstellen/   (brainstorm, nog niet goedgekeurd)
Goedgekeurd        →  docs/plannen/       (uitwerken, in uitvoering)
Afgerond           →  docs/archief/       (historiek, niet meer bewerken)
```

---

## Tech stack

| Component | Keuze |
|---|---|
| Backend | Python 3.12 + FastAPI 0.115 |
| ORM | SQLAlchemy 2.x + Alembic |
| Database | PostgreSQL 16 (Docker) |
| Frontend | HTMX 1.9 + Jinja2 + Tailwind CSS (CLI build, geen CDN) |
| Auth | JWT httpOnly cookie + TOTP (pyotp) + argon2-cffi |
| Deploy | Docker Compose op Synology NAS + Cloudflare Tunnel |

**passlib is EOL — nooit meer toevoegen.** Wachtwoord hashing = argon2-cffi.

---

## CSS-systeem

**Één laag, twee lagen diep:**

```
backend/static/css/input.css     ← CSS variabelen (:root + html.dark) + @tailwind directives
backend/tailwind.config.js        ← kleurmapping: 'primair' → 'var(--primair)'
                                  ↓  (Tailwind CLI tijdens Docker build)
backend/static/css/output.css    ← gegenereerd, niet bewerken, staat in .gitignore
```

**Dark mode:** uitsluitend via `html.dark` class — overal hetzelfde mechanisme.

**Kleuren:** altijd semantische klassen, nooit hardcoded Tailwind-kleuren.
```html
✅  <button class="bg-primair hover:bg-primair-hover text-white">
✅  <div style="background: var(--achtergrond-widget)">   ← voor niet-Tailwind CSS
❌  <button class="bg-blue-600 text-white">
```

**CSS aanpassen:**
```bash
# Kleuren wijzigen → backend/static/css/input.css bewerken, dan:
docker compose build app
docker compose up -d
```

**Beschikbare semantische Tailwind-klassen** (zie `tailwind.config.js` voor volledig overzicht):
`bg-primair`, `bg-primair-hover`, `bg-primair-zacht`, `bg-achtergrond`, `bg-oppervlak`,
`text-tekst`, `text-tekst-zacht`, `text-succes`, `text-gevaar`, `text-waarschuwing`, `text-info`,
`border-rand`, `border-rand-sterk`, `bg-succes-zacht`, `bg-gevaar-zacht`, etc.

**Beschikbare CSS variabelen** (ook voor inline `style=`):
`--primair`, `--achtergrond`, `--achtergrond-widget`, `--tekst`, `--tekst-secundair`,
`--rand`, `--hover-bg`, `--nav-bg`, `--nav-rand`, `--fout`, `--succes`, `--waarschuwing`, `--info`,
`--msg-*-bg`, `--hr-*`, `--grid-*` (zie `input.css` voor volledig overzicht)

---

## Architectuur (NON-NEGOTIABLE)

```
Router (api/routers/)     — DUN: parse, auth-check, call service, render template
    ↓
Service (services/)       — Orchestratie: DB-toegang + domeinlogica aanroepen
    ↓
Domein (services/domein/) — Pure Python, geen DB, geen imports van models of services
Models (models/)          — SQLAlchemy ORM only, geen businesslogica
```

**Dependency regels:**
- Router → Service ✅ | Router → Model ❌ | Router → Domein ❌
- Service → Model ✅ | Service → Domein ✅ | Service → andere Service ❌
- Domein → stdlib ✅ | Domein → Model ❌ | Domein → Service ❌

**Vuistregels voor plaatsing van logica:**

| Vraag | Antwoord JA → laag |
|---|---|
| Kan de check ook rechtstreeks in SQL? | **Service** (SQLAlchemy query) |
| Zou deze regel ook gelden als de DB anders is? | **Domein** (pure Python) |
| Is dit enkel orkestratie — geen businessregel? | **Service** (aanroepen, combineren) |
| Zit er HTTP-context in (request, response, status code)? | **Router** |

**Error bubbling:**
- Services gooien exceptions (`ValueError`, eigen `DomeinFout`) bij ongeldige invoer of gefaalde businessregels
- Routers vangen op en renderen een fouttemplate of retourneren een HTTP-fout — **nooit** omgekeerd

```python
# ✅ Service: gooi een exception
def sla_override_op(self, ...) -> LocatieHROverride:
    if not is_strenger(richting, nationale_waarde, override_waarde):
        raise ValueError("Override moet strenger zijn dan de nationale waarde.")
    ...

# ✅ Router: vang op, toon aan gebruiker
try:
    hr_service.sla_override_op(...)
except ValueError as fout:
    return sjablonen.TemplateResponse("...", {"fout": str(fout), ...})
```

---

## Drie-domein datamodel

Elk nieuw model hoort in precies één domein:

```
ORGANISATIE        AUTORISATIE       OPERATIES
───────────        ───────────       ─────────
Locatie            GebruikerRol      Planning + PlanningWijziging
Team                                 Verlof + VerlofTeamStatus
Gebruiker                            Notitie
                                     NationaleHRRegel + LocatieHROverride
                                     Shiftcode
                                     NationaleHRRegel + LocatieHROverride
                                     RodeLijnConfig (nationaal, exact 1 record)
                                     AuditLog
```

**Regel:** Operationele modellen verwijzen naar Organisatie, nooit naar GebruikerRol. Permissies horen in de service/router, niet in de data.

---

## Rolmodel

Rollen zijn **niet hiërarchisch** — één gebruiker kan meerdere rollen hebben met verschillende scopes.

```python
class GebruikerRol:
    gebruiker_id → Gebruiker
    rol          # super_beheerder | beheerder | hr | planner | teamlid
    scope_id     # team_id (teamlid/planner) | locatie_id (beheerder/hr)
                 # NOOIT None — super_beheerder krijgt scope_id van Locatie(code='NAT')
    is_reserve   # bool — enkel relevant bij rol=teamlid; True = uitfilterbaar in grid
    is_actief
```

**scope_id is polymorfisch** (team_id OF locatie_id afhankelijk van rol) — de DB kan dit niet afdwingen.

### VERBODEN:
```python
# ❌ Nooit rechtstreeks op scope_id filteren
db.query(GebruikerRol).filter(GebruikerRol.scope_id == x)
```

### VERPLICHT:
```python
# ✅ Altijd via helpers
heeft_rol(gebruiker_id, ["planner"], scope_id=team_id)
heeft_rol_in_locatie(gebruiker_id, ["teamlid", "planner"], locatie_id=locatie_id)
interpreteer_scope(rol, scope_id)  # → ('team', obj) of ('locatie', obj)
```

**Vaste systeemlocatie:** `Locatie(code='NAT', naam='Nationaal')` — aangemaakt bij init, nooit verwijderbaar. scope_id van super_beheerder wijst altijd naar dit record.

---

## Tenant-leak preventie (NON-NEGOTIABLE)

Elke DB-query op locatiegebonden data gebruikt `BaseRepository._locatie_filter()`.

```python
class BaseRepository:
    def __init__(self, db, locatie_id: int | None):
        # locatie_id=None = super_beheerder, geen filter
```

- Repositories erven altijd van `BaseRepository`
- Services instantiëren repositories met `locatie_id` uit de JWT-context
- Security middleware (`api/middleware/locatie_guard.py`) is het tweede vangnet
- `PlanningWijziging` heeft een **gedenormaliseerde `locatie_id`** (via team) voor directe filtering

---

## Modelconventies (gelden voor alle nieuwe modellen)

```python
# Soft delete — nooit fysiek verwijderen
is_actief:          bool        # default True
verwijderd_op:      datetime | None
verwijderd_door_id: int | None  # FK → Gebruiker

# UUID voor API-paden — integers intern, uuid extern
uuid: str  # uuid4, server-side gegenereerd, geïndexeerd
```

- API-paden: `/teams/{uuid}`, `/gebruikers/{uuid}` (nooit `/teams/1`)
- Interne JOINs: altijd op integer `id`
- `BaseRepository` filtert standaard op `is_actief=True` en `verwijderd_op IS NULL`

---

## Codeorganisatie (NON-NEGOTIABLE)

**Streefzone: 500–800 regels. Harde limiet: 1000 regels.**

- Bestand nadert **800 regels** → maak een splitsvoorstel in `docs/voorstellen/` vóór verdere uitbreiding
- Bestand overschrijdt **1000 regels** → onmiddellijk opsplitsen, niets toevoegen totdat dit gedaan is

### Wanneer splitsen

| Situatie | Aanpak |
|---|---|
| Bestand > 1000 regels | Splits op logische grens (niet willekeurig halveren) |
| Zelfde logica in 2+ plaatsen | Extraheer naar gedeeld module |
| Router heeft businesslogica | Verplaats naar service of domein |
| Template heeft herhaalde UI | Extraheer naar `templates/components/` |
| Validator van 3+ regels lang | Eigen bestand in `services/domein/validators/` |

### Gedeelde basisklassen en mixins

Herbruikbare basisklassen horen in een apart bestand — niet kopiëren:

```
api/
  middleware/          — elke middleware zijn eigen bestand
  dependencies.py      — gedeelde FastAPI Depends-functies
services/
  domein/
    basis_validator.py — BasisValidator ABC (alle validators erven hiervan)
  repository.py        — BaseRepository (alle repositories erven hiervan)
templates/
  components/          — herbruikbare Jinja2 macro's en partials
  layouts/             — basislayouts (app.html, auth.html)
```

### Naamgeving bij opsplitsing

- `hr_service.py` te groot → `hr_service.py` + `hr_validatie.py` + `hr_rapportage.py`
- `planning.py` (router) te groot → `planning_lezen.py` + `planning_schrijven.py` + `planning_export.py`
- Gebruik altijd beschrijvende namen — `utils.py` of `helpers.py` zijn verboden (te vaag)

---

## Codekwaliteit (NON-NEGOTIABLE)

### Type hints — verplicht in service-lagen

Alle parameters en return-waardes in `services/` en `api/routers/` krijgen type hints:

```python
# ✅
def haal_effectieve_waarde(self, regel_code: str, locatie_id: int) -> int | None: ...

# ❌
def haal_effectieve_waarde(self, regel_code, locatie_id): ...
```

In templates en `main.py` zijn type hints optioneel.

### Docstrings — verplicht op services

Elke publieke methode in een service krijgt een korte docstring: doel + parameters:

```python
def sla_override_op(self, nationale_regel_id: int, locatie_id: int, waarde: int) -> LocatieHROverride:
    """Sla een lokale HR-override op. Waarde moet strenger zijn dan de nationale waarde."""
```

Eén zin is genoeg. Geen roman schrijven.

### DRY — geen kopieerwerk

Zelfde logica op 2+ plaatsen? Extraheer:
- Python helpers → `services/domein/` (puur) of een gedeelde service-methode
- Jinja2 partials → `templates/components/`
- FastAPI dependencies → `api/dependencies.py`

### Geen placeholders

Schrijf altijd volledige, uitvoerbare code. Verboden:

```python
# ❌
def valideer(self, ...):
    # ... validatielogica hier ...
    pass
```

### Geen complexe lambda's

`lambda` uitsluitend voor simpele expressies (`key=lambda x: x.naam`).
Logica, vertakkingen of meerdere acties → gebruik een benoemde functie.

```python
# ❌
sorted(items, key=lambda x: x.datum if x.is_actief else date.max)

# ✅
def _sorteer_sleutel(x): return x.datum if x.is_actief else date.max
sorted(items, key=_sorteer_sleutel)
```

---

## Stijlregels (templates)

**Nooit hardcoded Tailwind-kleurcodes.** Altijd semantische klassen:

```html
<!-- ✅ -->
<div class="bg-oppervlak border border-rand text-tekst">
<button class="bg-primair hover:bg-primair-hover text-white">

<!-- ❌ -->
<div class="bg-white text-gray-900">
```

Kleuren worden gedefinieerd in `static/css/theme.css` als CSS custom properties (light + dark). Dark mode via `html.dark` class (Tailwind `darkMode: 'class'`).

Herbruikbare UI-elementen staan in `templates/components/` — gebruik die, schrijf geen inline stijlen.

---

## i18n (verplicht vanaf dag 1)

**Nooit hardcoded tekst** in templates of Python-code.

```html
{{ _('verlof.aanvragen') }}
```
```python
from services.i18n import t
raise VerlofFout(t('verlof.overlap', taal=gebruiker.taal))
```

- Taal per gebruiker (`Gebruiker.taal`: `nl | fr | en`, default `nl`)
- Nieuwe sleutel → toevoegen in **alle drie** taalbestanden
- Ontbrekende sleutel → fallback naar `nl`, nooit crash

---

## Security checklist (elke nieuwe route)

- [ ] `vereiste_rol()` of `vereiste_login` dependency
- [ ] CSRF token op alle POST-formulieren (`{{ csrf_token }}`)
- [ ] `locatie_id` filter via `BaseRepository` op alle queries
- [ ] `team_id` filter voor planning-data
- [ ] `super_beheerder` bypass is bewust en gelogd
- [ ] Rate limiting op gevoelige endpoints
- [ ] `AuditLog` entry bij elke mutatieactie

---

## Mobile vs. Desktop

| View | Platform | Voorbeelden |
|---|---|---|
| Consumptie | Mobile-first | Dashboard, Mijn Planning, Verlof, Notities |
| Productie | Desktop only | Planning grid, Admin, Rapporten |

Productie-views tonen een melding op schermen < 768px. Probeer geen planninggrid op mobile te bouwen.

---

## Caching in services

Gebruik `lru_cache` (stateless functies) of een instantie-dict (per-request cache) voor dure queries:

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def haal_effectieve_waarde(regel_code: str, locatie_id: int) -> int | None: ...
```

**Invalidatieregel:** elke `bewaar_*` of `verwijder_*` methode die data muteert, maakt de bijbehorende cache ongeldig. Nooit vergeten — anders krijg je verouderde data na een wijziging.

---

## Checklist nieuwe feature

Bij elke nieuwe route + service:

- [ ] Logica zit in de juiste laag (Router dun, Service orchestreert, Domein pure regels)
- [ ] Service-methodes hebben type hints + docstring
- [ ] Route heeft `vereiste_rol()` of `vereiste_login` dependency
- [ ] CSRF token op alle POST-formulieren
- [ ] `locatie_id` filter via `BaseRepository` op alle queries
- [ ] `AuditLog` entry bij elke mutatieactie
- [ ] Nieuwe i18n-sleutels toegevoegd in **alle drie** taalbestanden
- [ ] Bestandsomvang gecontroleerd (nog onder 800 regels?)
- [ ] Foutafhandeling: service gooit exception, router vangt op

---

## Wat NIET te doen

- Geen `Groep`/`groep` meer — hernoemd naar `Team`/`team` overal
- Geen `Gebruiker.rol` veld — rollen zitten in `GebruikerRol`
- Geen `GebruikerGroep` — vervangen door `GebruikerRol` met `is_reserve` vlag
- Geen `passlib` importeren
- Geen directe `WHERE scope_id = X` queries
- Geen hardcoded tekst in templates
- Geen hardcoded Tailwind-kleurcodes (`bg-white`, `text-gray-900`, ...)
- Geen secrets in code of git
- Geen physical deletes — altijd soft delete
- Geen integer IDs in API-paden — altijd uuid

---

## Referentiebestanden

| Pad | Doel |
|---|---|
| `docs/plannen/plan_van_aanpak_v0.9.md` | Volledig plan met alle fases |
| `code_v07/src/services/applicatie/` | **PRIMAIRE BRON** — 34 applicatieservices om te porten |
| `code_v07/src/services/domein/` | **PRIMAIRE BRON** — 23 domeinbestanden (grotendeels direct herbruikbaar) |
| `code_v07/src/services/domein/validators/` | **PRIMAIRE BRON** — 10 validators (grotendeels direct herbruikbaar) |
| `code_v07/src/services/repo/` | **PRIMAIRE BRON** — 18 repositories (herschrijven voor SQLAlchemy 2.x) |
| `code_v08/backend/` | Infrastructuurreferentie: Docker, Alembic, FastAPI-patronen, JWT-auth |
| `backend/services/repository.py` | BaseRepository (tenant-filter) |
| `backend/api/dependencies.py` | heeft_rol, heeft_rol_in_locatie, interpreteer_scope |
| `backend/static/css/theme.css` | CSS custom properties light/dark |
| `backend/templates/components/` | Herbruikbare UI-componenten |
| `backend/locales/` | Vertalingen nl/fr/en |
