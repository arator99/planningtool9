# Planningtool v0.9 — Claude-gids

## Wat is dit project?

Webgebaseerde planningsapp voor een bedrijf met ~10 productielocaties verdeeld over 5 area's. Gebruikers plannen shifts, vragen verlof aan, en communiceren via een interne mailbox. De app draait op een Synology NAS via Docker Compose, bereikbaar via Cloudflare Tunnel.

**Strategie:** `code_v07/src/services/` = **primaire bron** voor businesslogica (port naar SQLAlchemy + FastAPI). `code_v08/backend/` = **infrastructuurreferentie** (Docker, Alembic, JWT-auth, FastAPI-patronen).
**Volledige plan:** `docs/plannen/plan_van_aanpak_v0.9.md`

## Werkwijze — plannen en voortgang

- Plannen die taken bevatten gebruiken **Markdown-checkboxes** (`- [ ]` / `- [x]`)
- **Vink taken af zodra ze afgewerkt zijn** — update `docs/plannen/plan_van_aanpak_v0.9.md` direct na voltooiing, niet achteraf in bulk
- Gebruik `- [x]` voor volledig afgeronde taken; laat `- [ ]` staan voor deels gedaan of nog te doen
- Huidige voortgang: **Fase 0 grotendeels afgerond** (zie plan voor openstaande items)

---

## Tech stack

| Component | Keuze |
|---|---|
| Backend | Python 3.12 + FastAPI 0.115 |
| ORM | SQLAlchemy 2.x + Alembic |
| Database | PostgreSQL 16 (Docker) |
| Frontend | HTMX 1.9 + Jinja2 + Tailwind CSS (CDN) |
| Auth | JWT httpOnly cookie + TOTP (pyotp) + argon2-cffi |
| Deploy | Docker Compose op Synology NAS + Cloudflare Tunnel |

**passlib is EOL — nooit meer toevoegen.** Wachtwoord hashing = argon2-cffi.

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
