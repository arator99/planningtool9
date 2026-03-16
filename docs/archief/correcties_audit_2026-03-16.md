# Correctieplan — Auditbevindingen 2026-03-16

**Bron:** `docs/rapporten/audit_2026-03-16.md`
**Prioriteit:** Vóór verder bouwen aan Fase 3 (Fase C is de blocker)

---

## Overzicht

| Correctie | Omvang | Prioriteit | Reden |
|---|---|---|---|
| A — Router→Domein imports | Klein (2 bestanden) | 🔴 Hoog | Architectuurschending, snel te fixen |
| B — `gebruiker.rol` voor autorisatie | Medium (5 bestanden) | 🔴 Hoog | Verkeerde autorisatiebron, veiligheidsrisico |
| C — UUID in API-paden | Groot (10+ routers) | 🔴 Hoog | Architectuurprincipe, groeit mee elke fase |
| D — Type hints | Triviaal (1 bestand) | ⚪ Laag | Kwaliteit |
| E — Hardcoded kleuren in templates | Groot (6+ templates) | 🟡 Middel | Functioneel OK, onderhoud/dark mode |
| F — Hardcoded tekst in templates | Medium (8+ templates) | 🟡 Middel | i18n-volledigheid |

**Volgorde:** A → B → C → D → E → F

---

## Correctie A — Router→Domein imports

**Omvang:** 2 bestanden, ~5 minuten werk

### Probleem

```python
# api/routers/verlof.py:11 — VERBODEN
from services.domein.planning_domein import MAAND_NAMEN, bereken_navigatie

# api/routers/planning.py:14 — VERBODEN
from services.domein.validatie_domein import VALIDATORS
```

Routers mogen de domeinlaag niet rechtstreeks importeren.

### Oplossing

**`MAAND_NAMEN` en `bereken_navigatie`:**
- Voeg `haal_navigatie(jaar, maand)` toe aan `PlanningService` die `bereken_navigatie` aanroept en het resultaat incl. `MAAND_NAMEN` teruggeeft als dict
- `verlof.py` roept `planning_service.haal_navigatie(jaar, maand)` aan

**`VALIDATORS`:**
- `ValidatieService` heeft al toegang tot de validators intern
- Vervang de directe import door `ValidatieService.haal_validator_namen()` of geef de lijst terug als onderdeel van het validatieresultaat

### Taken

- [ ] `PlanningService`: methode `haal_maand_navigatie(jaar: int, maand: int) -> dict` toevoegen
- [ ] `api/routers/verlof.py`: domein-import vervangen door service-aanroep
- [ ] `ValidatieService`: methode `haal_validator_namen() -> list[str]` toevoegen
- [ ] `api/routers/planning.py`: domein-import vervangen door service-aanroep

---

## Correctie B — `gebruiker.rol` voor Autorisatiebeslissingen

**Omvang:** 5 bestanden (4 Python, 1 template)

### Probleem

`Gebruiker.rol` is een gedenormaliseerd display-veld. Autorisatiebeslissingen binnen routes gebruiken het echter als bron van waarheid:

```python
# api/routers/dashboard.py:26
if gebruiker.rol in ("beheerder", "planner", "hr", "super_beheerder"):
    pending_verlof = VerlofService(db).haal_pending_count(...)

# api/routers/verlof.py:50, 96, 126
is_behandelaar = gebruiker.rol in BEHANDELAAR_ROLLEN
```

En in templates:
```html
{% if gebruiker.rol in ["beheerder", "planner"] %} ... {% endif %}
```

### Oplossing

**Principe:** routes berekenen booleans op basis van `heeft_rol_in_locatie()` / `heeft_rol_in_team()`, en geven die mee aan het template. Templates nemen zelf geen autorisatiebeslissingen.

```python
# ✅ Correct patroon in router
is_behandelaar = heeft_rol_in_locatie(
    gebruiker.id, gebruiker.locatie_id,
    ("planner", "hr", "beheerder", "super_beheerder"), db
)
return sjablonen.TemplateResponse("...", {
    ...,
    "is_behandelaar": is_behandelaar,
})
```

```html
<!-- ✅ Correct in template -->
{% if is_behandelaar %} ... {% endif %}
```

### Opmerking: `vereiste_rol()` in `dependencies.py`

`dependencies.py` gebruikt `gebruiker.rol` bewust voor snelle toegangscontrole op route-niveau — dit is de geaccepteerde use case (zoals gedocumenteerd in de docstring). Dat blijft ongewijzigd.

### Taken

- [ ] `api/routers/dashboard.py`: `pending_verlof`-check via `heeft_rol_in_locatie()`; bool meegeven aan template
- [ ] `api/routers/verlof.py`: `is_behandelaar` via `heeft_rol_in_locatie()`; alle 3 plekken (regels 50, 96, 126)
- [ ] `templates/pages/dashboard.html`: alle `gebruiker.rol`-checks vervangen door template-booleans (`is_behandelaar`, `is_planner`, `is_beheerder`, ...)
- [ ] Controleer overige templates op `gebruiker.rol`-checks en vervang door booleans

---

## Correctie C — UUID in API-paden

**Omvang:** 10+ routers, ~37 routes

### Principe

- API-paden: `/{uuid}` (string) — extern zichtbaar
- Intern: service zoekt op `uuid`, werkt verder op `id` (integer)
- Alle betrokken modellen hebben al een `uuid` veld

### Stap 1 — Controleer UUID-velden op alle betrokken modellen

Niet elk model heeft hetzelfde veldnaam. Inventariseer:

| Model | UUID-veld | Actie |
|---|---|---|
| `Gebruiker` | `gebruiker_uuid` | Hernoemen naar `uuid` OF service accepteert `gebruiker_uuid` |
| `Team` | controleren | Toevoegen indien ontbreekt + Alembic migratie |
| `VerlofAanvraag` | controleren | Toevoegen indien ontbreekt + Alembic migratie |
| `NationaleHRRegel` | controleren | Toevoegen indien ontbreekt + Alembic migratie |
| `Competentie` | controleren | Toevoegen indien ontbreekt + Alembic migratie |
| `Shiftcode` | `uuid` ✅ | OK |
| `Werkpost` | `uuid` ✅ | OK |
| `Planning` | `uuid` ✅ | OK |
| `Notitie` | controleren | Toevoegen indien ontbreekt + Alembic migratie |

### Stap 2 — Alembic migratie voor ontbrekende UUID-velden

- [ ] Check welke modellen nog geen `uuid` hebben
- [ ] Migratie `004_uuid_velden.py`: voeg `uuid` toe aan ontbrekende tabellen
- [ ] Seed-script: vul `uuid` voor bestaande records (via `gen_random_uuid()` of Python `uuid4`)

### Stap 3 — Service-methodes aanpassen

Per service: voeg `haal_op_uuid(uuid: str)` toe (of hernoem bestaande `haal_op_id` tot accepteert beide):

```python
def haal_op_uuid(self, uuid: str) -> Team:
    """Zoek op extern uuid; retourneert 404 als niet gevonden."""
    team = self.db.query(Team).filter(Team.uuid == uuid, Team.is_actief == True).first()
    if not team:
        raise ValueError(f"Team niet gevonden: {uuid}")
    return team
```

Betrokken services: `GebruikerService`, `TeamService`, `VerlofService`, `PlanningService`,
`ShiftcodeService`, `WerkpostService`, `HRService`, `NotitieService`, `CompetentieService`.

### Stap 4 — Routers aanpassen

Per router: `{id: int}` → `{uuid: str}`, service-aanroep via `haal_op_uuid()`.

**Volgorde (klein → groot):**

- [ ] `api/routers/beheer_hr.py` — 2 routes (`/{regel_id}`)
- [ ] `api/routers/notities.py` — 2 routes (`/{notitie_id}`)
- [ ] `api/routers/hr.py` — 3 routes (`/{nationale_regel_id}`)
- [ ] `api/routers/competenties.py` — 3 routes (`/{competentie_id}`)
- [ ] `api/routers/werkposten.py` — 4 routes (`/{werkpost_id}`)
- [ ] `api/routers/shiftcodes.py` — 3 routes (`/{shiftcode_id}`)
- [ ] `api/routers/verlof.py` — 3 routes (`/{aanvraag_id}`)
- [ ] `api/routers/teams.py` — 5 routes (`/{team_id}`, `/{lid_gebruiker_id}`)
- [ ] `api/routers/gebruikers.py` — 5 routes (`/{gebruiker_id}`)
- [ ] `api/routers/planning.py` — 3 routes (`/cel/{gebruiker_id}`, `/suggestie/{user_id}`, `/reserve/{reserve_id}`)

### Stap 5 — Templates en HTMX-aanroepen bijwerken

Alle `hx-post`, `hx-get`, `action=` en `href=` attributen die integer IDs bevatten moeten `{{ obj.uuid }}` gebruiken.

- [ ] Alle templates in `templates/pages/` en `templates/partials/` doorlopen
- [ ] Zoekterm: `{{ .id }}` en `f"/{obj.id}"` in templates en routers

---

## Correctie D — Type Hints

**Omvang:** 1 bestand, 2 functies — triviaal

### Taken

- [ ] `api/routers/auth.py:44` — `def toon_login(...) -> HTMLResponse:`
- [ ] `api/routers/auth.py:52` — `def toon_totp_verificatie(...) -> HTMLResponse:`

---

## Correctie E — Hardcoded Tailwind-kleuren

**Omvang:** 6+ templates, 50+ kleuren

### Principe

`static/css/theme.css` definieert CSS custom properties. Tailwind's `@layer utilities` maakt er semantische klassen van. Templates gebruiken alleen die semantische klassen.

### Bestaande semantische klassen (uit theme.css)

Inventariseer eerst welke semantische klassen al bestaan, dan uitbreiden wat ontbreekt:

```css
/* Toe te voegen aan theme.css als ze ontbreken: */
.bg-gevaar       { background-color: var(--kleur-gevaar); }
.text-gevaar     { color: var(--kleur-gevaar); }
.bg-waarschuwing { background-color: var(--kleur-waarschuwing); }
.bg-succes       { background-color: var(--kleur-succes); }
.text-subtiel    { color: var(--kleur-subtiel); }
.border-rand-zacht { border-color: var(--kleur-rand-zacht); }
```

### Taken

- [ ] `static/css/theme.css` lezen — inventariseer welke semantische klassen al bestaan
- [ ] Ontbrekende semantische klassen toevoegen aan `theme.css` (light + dark waarden)
- [ ] `templates/partials/cel_weergave.html` — alle concrete kleuren vervangen
- [ ] `templates/partials/cel_bewerk.html` — alle concrete kleuren vervangen
- [ ] `templates/layouts/app.html` — alle concrete kleuren vervangen
- [ ] `templates/pages/dashboard.html` — alle concrete kleuren vervangen
- [ ] `templates/pages/login.html` — alle concrete kleuren vervangen
- [ ] Overige templates doorlopen op resterende hardcoded kleuren

---

## Correctie F — Hardcoded Tekst in Templates

**Omvang:** 8+ templates, 20+ labels

### Aanpak

Generieke labels (`Code`, `Naam`, `Annuleer`, `Opslaan`) zijn herbruikbaar over alle schermen. Eén keer toevoegen aan `locales/nl.json`, `en.json`, `fr.json` onder de namespace `algemeen.*`.

### Nieuwe i18n-sleutels (namespace `algemeen`)

```json
{
  "algemeen.code": "Code",
  "algemeen.naam": "Naam",
  "algemeen.eenheid": "Eenheid",
  "algemeen.waarde": "Waarde",
  "algemeen.richting": "Richting",
  "algemeen.beschrijving": "Beschrijving",
  "algemeen.annuleer": "Annuleer",
  "algemeen.opslaan": "Opslaan",
  "algemeen.bewerk": "Bewerken",
  "algemeen.verwijder": "Verwijderen",
  "algemeen.nieuw": "Nieuw",
  "algemeen.wachtwoord": "Wachtwoord",
  "algemeen.gebruikersnaam": "Gebruikersnaam"
}
```

### Taken

- [ ] Bovenstaande sleutels toevoegen aan `locales/nl.json`, `en.json`, `fr.json`
- [ ] `templates/pages/beheer/hr_nationaal_formulier.html` — labels vervangen
- [ ] `templates/pages/hr/override_formulier.html` — labels vervangen
- [ ] `templates/pages/gebruikers/lijst.html` — tabelheaders vervangen
- [ ] `templates/pages/teams/lijst.html` — tabelheaders vervangen
- [ ] `templates/pages/shiftcodes/lijst.html` — tabelheaders vervangen
- [ ] `templates/pages/account/wachtwoord.html` — labels vervangen
- [ ] `templates/pages/dashboard.html` — badge "Nieuw" vervangen
- [ ] Overige templates doorlopen op resterende hardcoded tekst

---

## Verificatie na alle correcties

Na voltooiing van alle correcties: herhaal de audit.

```bash
# Controleer op domein-imports in routers
grep -r "from services.domein" backend/api/routers/

# Controleer op integer route-parameters
grep -r "{[a-z_]*_id}" backend/api/routers/

# Controleer op gebruiker.rol in conditionele logica
grep -rn "gebruiker\.rol" backend/api/routers/ backend/templates/

# Controleer op hardcoded kleuren
grep -rn "bg-blue\|text-gray\|bg-gray\|bg-red\|border-gray" backend/templates/
```

Doel: alle vier grep-commando's geven geen resultaten meer.
