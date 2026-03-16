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

## Broncode-strategie

- **`code_v07/src/services/`** = primaire bron voor businesslogica (port naar SQLAlchemy + FastAPI)
- **`code_v08/backend/`** = infrastructuurreferentie (Docker, Alembic, JWT, FastAPI-patronen)
- Zie `docs/plannen/plan_van_aanpak_v0.9.md` voor het volledige plan

## Nieuwe route checklist

Voor elke nieuwe route verplicht:

- [ ] `vereiste_rol()` of `vereiste_login` dependency
- [ ] CSRF token op alle POST-formulieren (`{{ csrf_token }}`)
- [ ] `locatie_id` filter op alle queries (nooit cross-locatie data lekken)
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
