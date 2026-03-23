# Bijdragen aan Planningtool v0.9

## Architectuur — VERPLICHT LEZEN

De app volgt een **strikte 3-laags architectuur**:

```
Router (api/routers/)   — dun: parse request, auth, call service, render template
    ↓
Service (services/)     — orchestratie: DB + domeinlogica
    ↓
Domein (services/domein/) — pure Python, geen DB, geen imports van service/model
Models (models/)          — SQLAlchemy ORM, geen businesslogica
```

**Dependency-regels (nooit schenden):**

| Van → Naar | Toegestaan? |
|---|---|
| Router → Service | ✅ |
| Router → Model | ❌ |
| Router → Domein | ❌ |
| Service → Model | ✅ |
| Service → Domein | ✅ |
| Service → andere Service | ❌ |
| Domein → Python stdlib | ✅ |
| Domein → Model / Service | ❌ |

## Datamodel — kernconcepten

### Organisatie-laag

```
Area          → groepeert locaties (voor HR-scoping)
Locatie       → fysieke vestiging; area_id (nullable FK → Area)
Team          → afdeling binnen een locatie; locatie_id FK → Locatie
Gebruiker     → geen locatie_id — context afgeleid via Lidmaatschap → Team → locatie_id
```

### Lidmaatschap (vervangt `teamlid`/`planner` rollen)

```python
class Lidmaatschap:
    gebruiker_id  FK → Gebruiker
    team_id       FK → Team          # echte DB-constraint, geen polymorfisme
    is_planner    bool (default False)
    type          enum: Vast | Reserve | Detachering
    is_actief     bool
    verwijderd_op, verwijderd_door_id
```

- Elke gebruiker heeft **minstens 1 actief lidmaatschap** — invariant
- Gebruiker aanmaken zonder `team_id` → service weigert (atomische transactie)
- Partial unique index: `(gebruiker_id, team_id) WHERE verwijderd_op IS NULL`

### GebruikerRol (enkel admin-rollen)

```python
class GebruikerRol:
    gebruiker_id     FK → Gebruiker
    rol              # super_beheerder | beheerder | hr   (teamlid/planner niet meer hier)
    scope_locatie_id # nullable FK → Locatie  (beheerder: verplicht)
    scope_area_id    # nullable FK → Area     (hr area-scope: verplicht)
    is_actief
```

Scoperegels:
- `super_beheerder`: beide scope-velden `NULL`
- `beheerder`: `scope_locatie_id` ingevuld, `scope_area_id = NULL`
- `hr` (area): `scope_area_id` ingevuld
- `hr` (nationaal): beide scope-velden `NULL`

### Locatie-context ophalen

**Nooit** `Gebruiker.locatie_id` lezen — dat veld bestaat niet meer.
Gebruik altijd de `haal_actieve_locatie_id()` FastAPI-dependency:

```python
actieve_locatie_id: int = Depends(haal_actieve_locatie_id)
```

### Gebruikers in een locatie opvragen

```python
# ✅ Correct
db.query(Gebruiker)
  .join(Lidmaatschap, Lidmaatschap.gebruiker_id == Gebruiker.id)
  .join(Team, Team.id == Lidmaatschap.team_id)
  .filter(
      Team.locatie_id == locatie_id,
      Lidmaatschap.is_actief == True,
      Lidmaatschap.verwijderd_op == None,
      Gebruiker.is_actief == True,
  ).distinct().all()

# ❌ Nooit
db.query(Gebruiker).filter(Gebruiker.locatie_id == locatie_id)
```

## Nieuwe route checklist

Voor elke nieuwe route verplicht:

- [ ] `vereiste_rol()` of `vereiste_login` dependency
- [ ] CSRF token op alle POST-formulieren (`{{ csrf_token }}`)
- [ ] `actieve_locatie_id = Depends(haal_actieve_locatie_id)` — nooit `gebruiker.locatie_id`
- [ ] Gebruikers-in-locatie via Lidmaatschap → Team JOIN (zie patroon hierboven)
- [ ] `team_id` filter voor planning-specifieke queries
- [ ] Rate limiting op gevoelige endpoints (`@limiter.limit(...)`)
- [ ] `AuditLog` entry bij elke mutatieactie

## i18n — verplicht

Alle zichtbare tekst in templates via `{{ t("sleutel") }}`:

```jinja2
{{ t("verlof.aanvragen") }}
{{ t("algemeen.opgeslagen", naam=gebruiker.volledige_naam) }}
```

Nieuwe sleutels toevoegen in **alle drie** taalbestanden: `backend/i18n/nl.json`, `fr.json`, `en.json`.
fr/en mogen tijdelijk de Nederlandse tekst kopiëren als vertaling ontbreekt.

## Stijlconventies

- **Python**: PEP 8, variabelenamen in het Nederlands (services/modellen), Engelse namen enkel voor Python-idioom
- **Templates**: Tailwind CSS utility classes, geen inline `style=` tenzij CSS custom properties (`var(--...)`)
- **Commits**: korte imperatieve zin in het Nederlands, geen `Co-Authored-By` tag
- **Geen `passlib`** — wachtwoord hashing via argon2-cffi

## Lokale ontwikkelomgeving

```bash
# Vereisten: Docker Desktop

# Kopieer .env.example en pas aan
cp .env.example .env

# Start (bouwt images + voert migraties uit)
docker compose up --build

# App bereikbaar op http://localhost:8000
# Testaccount: admin / Admin1234!
```

## Alembic migraties

```bash
# Nieuwe migratie aanmaken (vanuit backend container)
docker compose exec app alembic revision --autogenerate -m "omschrijving"

# Migraties uitvoeren
docker compose exec app alembic upgrade head
```

Migraties draaien automatisch bij `docker compose up` via de init-container.

## Tests

```bash
# (nog op te zetten in Fase 0)
docker compose exec app pytest
```
