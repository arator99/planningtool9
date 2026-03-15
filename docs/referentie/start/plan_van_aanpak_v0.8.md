# Plan van Aanpak: Planning Tool v0.8

**Versie:** 1.0
**Datum:** 2026-03-01
**Status:** CONCEPT
**Auteur:** AI Assistent

---

## 0. Huidige Situatie & Transitiestrategie

### Versie Status

| Versie | Status | Database | App Broncode |
|--------|--------|----------|--------------|
| **v0.6** | **PRODUCTIE** | SQLite v0.6 | Deels beschadigd/verloren |
| **v0.7** | LIVE TEST | SQLite v0.7 | Volledig beschikbaar |
| **v0.8** | PLANNING | PostgreSQL | Nieuw te ontwikkelen |

### Database Migratie: Eenrichtingsverkeer

```
┌─────────────────────────────────────────────────────────────────┐
│  BELANGRIJK: Database migraties zijn ONOMKEERBAAR              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   v0.6 DB ────────► v0.7 DB ────────► v0.8 DB                  │
│      │                 │                  │                     │
│      │    upgrade      │     upgrade      │                     │
│      │    script       │     script       │                     │
│      │                 │                  │                     │
│      ▼                 ▼                  ▼                     │
│   GEEN WEG TERUG   GEEN WEG TERUG    GEEN WEG TERUG            │
│                                                                 │
│   v0.6 broncode deels verloren → geen nieuwe migraties          │
│   v0.7 DB niet leesbaar door v0.6 app                          │
│   v0.8 DB (PostgreSQL) niet leesbaar door v0.7 app (SQLite)    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Implicaties voor Rollback

| Scenario | Mogelijkheid | Oplossing |
|----------|--------------|-----------|
| v0.7 → v0.6 app | **Niet mogelijk** | Backup v0.6 DB bewaren vóór upgrade |
| v0.8 → v0.7 app | **Niet mogelijk** | Backup v0.7 DB bewaren vóór migratie |
| v0.8 bugs na go-live | App rollback, NIET DB | Fix in v0.8, geen data verlies |

### Transitiepad

```
v0.6 (productie) + v0.6 DB
    │
    ├── v0.7 live test #2 (op KOPIE van productie DB)
    │         │
    │         ▼
    │    issues? → fix → herhaal test
    │         │
    │         ▼
    │    v0.7 stabiel bevonden
    │         │
    ▼         ▼
BACKUP v0.6 DB (point of no return)
    │
    ▼
v0.7 naar productie (DB upgrade)
    │
    ├── v0.8 ontwikkeling parallel
    │
    ▼
BACKUP v0.7 DB (point of no return)
    │
    ▼
v0.8 live tests (op KOPIE)
    │
    ▼
v0.8 naar productie (DB migratie naar PostgreSQL)
```

### Belangrijke Principes

1. **Altijd backup vóór upgrade**: DB backup is de enige rollback optie
2. **Test op kopie**: Live tests altijd op kopie van productie DB
3. **Geen haast**: v0.6 draait stabiel, geen urgentie om te forceren
4. **Point of no return**: Duidelijk communiceren wanneer upgrade onomkeerbaar is

### v0.7 Verbeteringen t.o.v. v0.6 (behouden in v0.8)

| Aspect | v0.6 (vermoedelijk) | v0.7 | v0.8 Aanpak |
|--------|---------------------|------|-------------|
| **Validatie scope** | Hele jaar | Per maand | Per maand (API endpoint) |
| **Validatie caching** | Geen/beperkt | Per (jaar, maand) | Redis of DB query cache |
| **Rode lijn berekening** | Statisch hele jaar | Dynamisch op basis van shifts | Idem, in service |
| **Maandovergang context** | Niet | ValidatieContext | Pydantic model |

**v0.7 Validatie architectuur (te behouden):**
- `valideer_planning_maand(jaar, maand)` — valideert alleen de gevraagde maand
- Rode lijn validator berekent periodes dynamisch (`min_datum` tot `max_datum`)
- Cache invalidatie per maand bij wijzigingen
- In-memory validatie met `valideer_met_shifts()` voor realtime feedback
- `ValidatieContext` per gebruiker voor maandovergang (zie `docs/plannen/plan_validatie_context.md`)

**ValidatieContext → v0.8 mapping:**

| v0.7 | v0.8 |
|------|------|
| `@dataclass ValidatieContext` | Pydantic `BaseModel` |
| `_bereken_validatie_context()` | Identiek (in service) |
| Validators met `context` param | Identiek |
| `PlanningRepo.haal_shifts_voor_periode()` | SQLAlchemy query |

---

## 1. Executive Summary

Dit document beschrijft de migratie van Planning Tool v0.7 (PyQt6/SQLite desktop applicatie) naar v0.8 (FastAPI/PostgreSQL webapplicatie). De migratie is geen herschrijving, maar een **platformwissel** waarbij bewezen architectuurprincipes behouden blijven.

### Kernpunten

| Aspect | v0.7 (Huidige) | v0.8 (Doel) |
|--------|---------------|-------------|
| Frontend | PyQt6 Desktop | HTMX + Jinja2 Web |
| Backend | Python Services | FastAPI + Pydantic |
| Database | 3x SQLite (per groep) | 1x PostgreSQL (multi-tenant) |
| Authenticatie | Lokale login | JWT + TOTP/2FA |
| Deployment | PyInstaller executable | Docker Compose op NAS |
| Bereikbaarheid | Alleen lokaal netwerk | Internet (HTTPS) |

---

## 2. Scope & Uitgangspunten

### Wat WEL migreeert

- Alle business logica uit de service-laag
- Database schema (geconverteerd naar PostgreSQL)
- Gebruikersrollen en rechtenmodel
- HR validatieregels
- Auto-scheduling algoritme
- Rapportage functionaliteit

### Wat NIET migreeert (vervangt wordt)

- PyQt6 GUI code (vervangen door HTMX/Jinja2)
- SQLite specifieke code (vervangen door SQLAlchemy ORM)
- Lokale caching strategie (vervangen door stateless + optioneel Redis)
- Desktop deployment (vervangen door Docker)

### v0.7 Items die VERVALLEN

Uit `docs/plannen/` blijkt dat de volgende items uitgesteld zijn naar v0.8 en nu vervallen:

| Item | Reden Verval |
|------|--------------|
| Caching strategie refactoring | v0.8 is stateless |
| Event Bus implementatie | Web gebruikt andere patterns |
| GUI schermen mixins | GUI wordt volledig vervangen |
| Code quality fixes | Niet relevant voor nieuwe codebase |

---

## 3. Fasering

De migratie wordt uitgevoerd in **5 fasen**, elk met duidelijke deliverables.

### Fase 0: Voorbereiding (Week 1-2)

**Doel:** Fundament leggen voor de migratie

#### Taken

1. **Development omgeving opzetten**
   - Docker Desktop installeren
   - PostgreSQL lokaal draaien
   - FastAPI skeleton project aanmaken

2. **Repository structuur aanmaken**
   ```
   planning-tool-v08/
   ├── backend/
   │   ├── main.py
   │   ├── config.py
   │   ├── database.py
   │   ├── api/routers/
   │   ├── services/
   │   ├── models/
   │   ├── schemas/
   │   └── tests/
   ├── frontend/
   │   ├── templates/
   │   ├── static/
   │   └── nginx.conf
   ├── migrations/
   ├── locales/
   ├── docker-compose.yml
   └── .env.example
   ```

3. **Tooling configureren**
   - Alembic voor database migraties
   - pytest voor backend tests
   - Pre-commit hooks

4. **i18n voorbereiding**
   - `nl.json` aanmaken met alle v0.7 hardcoded strings
   - Hiërarchische sleutelstructuur definiëren

#### Deliverables

- [ ] Werkende Docker Compose setup (db + app containers)
- [ ] FastAPI "Hello World" endpoint
- [ ] Alembic geïnitialiseerd
- [ ] `locales/nl.json` met basis vertalingen

---

### Fase 1: Database Migratie (Week 3-4)

**Doel:** Data overzetten van 3 SQLite databases naar 1 PostgreSQL database

#### Taken

1. **Schema analyse**
   - Vergelijk schemas van de 3 SQLite databases
   - Documenteer verschillen
   - Ontwerp unified schema met `group_id`

2. **SQLAlchemy ORM modellen**
   - `User` model (met TOTP velden)
   - `Group` model
   - `GroupConfig` model
   - Alle planning gerelateerde modellen
   - `AuditLog` model

3. **Alembic migraties**
   - Initial migration met volledig schema
   - Seed data voor groups

4. **Data migratie script**
   - Export SQLite naar CSV
   - Import met group_id toekenning
   - Validatie script (record counts, integriteit)

5. **Rollen consolidatie**
   - v0.7: `beheerder`, `planner`, `gebruiker` (+ inconsistent `werknemer`/`medewerker`)
   - v0.8: `beheerder`, `planner`, `hr`, `gebruiker`

#### Deliverables

- [ ] SQLAlchemy modellen voor alle entiteiten
- [ ] Alembic migratie scripts
- [ ] Data migratie script (SQLite → PostgreSQL)
- [ ] Validatie rapport

---

### Fase 2: Backend Services (Week 5-8)

**Doel:** Service-laag migreren naar FastAPI

#### Sub-fase 2A: Authenticatie (Week 5)

1. **AuthService implementeren**
   - Login flow (wachtwoord verificatie)
   - JWT token creatie (access + refresh)
   - TOTP setup en verificatie
   - Token refresh mechanisme

2. **Dependencies implementeren**
   - `get_db()` — SQLAlchemy session
   - `get_current_user()` — JWT verificatie
   - `require_role(*roles)` — Rol-gebaseerde toegang

3. **Rate limiting**
   - slowapi integratie
   - Limiet op `/auth/token` en `/auth/totp/verify`

4. **Routers**
   - `POST /auth/token`
   - `POST /auth/totp/verify`
   - `POST /auth/totp/setup`
   - `POST /auth/refresh`

#### Sub-fase 2B: Core Services (Week 6-7)

Per domein de volgende stappen:

1. **Pydantic schemas** (request/response)
2. **Service class** (business logica)
3. **FastAPI router** (endpoints)
4. **Unit tests**

| Router | Endpoints | Prioriteit |
|--------|-----------|------------|
| `users.py` | CRUD gebruikers | Hoog |
| `planning.py` | Shifts, roosters | Hoog |
| `leaves.py` | Verlofaanvragen | Hoog |
| `shift_codes.py` | Shiftcode beheer | Medium |
| `hr_export.py` | HR exports | Medium |
| `admin.py` | Systeembeheer | Laag |

#### Sub-fase 2C: Aanvullende Services (Week 8)

1. **NotificationService** — In-app meldingen
2. **AuditService** — Audit trail logging
3. **HealthService** — Health check endpoint
4. **ExportService** — CSV/Excel exports

#### Deliverables

- [ ] Werkende authenticatie met JWT + TOTP
- [ ] Alle core routers geïmplementeerd
- [ ] Unit tests (>80% coverage)
- [ ] API documentatie (Swagger/OpenAPI)

---

### Fase 3: Frontend Ontwikkeling (Week 9-12)

**Doel:** HTMX/Jinja2 webinterface bouwen

#### Sub-fase 3A: Fundament (Week 9)

1. **Template structuur**
   ```
   templates/
   ├── base.html            # HTML boilerplate
   ├── layouts/
   │   ├── app_layout.html  # Navigatie, sidebar
   │   └── auth_layout.html # Login pagina's
   └── pages/
       └── ...
   ```

2. **Styling**
   - CSS framework kiezen (Tailwind / Bootstrap / custom)
   - Responsive design basis
   - Thema (licht/donker)

3. **HTMX integratie**
   - Globale error handling
   - Loading indicators
   - Flash messages

4. **PWA setup**
   - Service Worker
   - manifest.json
   - offline.html

#### Sub-fase 3B: Auth Pagina's (Week 9)

- Login pagina
- TOTP verificatie pagina
- TOTP setup pagina (QR code)

#### Sub-fase 3C: Dashboard & Navigatie (Week 10)

- Dashboard per rol
- Navigatiebalk met rolgebaseerde menu's
- Account menu (profiel, taal, uitloggen)

#### Sub-fase 3D: Planning Module (Week 10-11)

- Kalender weergave
- Shift editing (HTMX partial updates)
- Maand navigatie
- HR alerts panel

#### Sub-fase 3E: Verlof & Rapporten (Week 11-12)

- Verlofaanvraag formulier
- Verlof overzicht (planner view)
- Goedkeuring workflow
- Rapportage tabbladen

#### Deliverables

- [ ] Werkende login flow incl. TOTP
- [ ] Dashboard per rol
- [ ] Planning kalender met HTMX
- [ ] Verlof module compleet
- [ ] Rapporten beschikbaar
- [ ] PWA basis (offline melding)

---

### Fase 4: Deployment & Testen (Week 13-14)

**Doel:** Productie-ready maken en uitrollen op NAS

#### Taken

1. **Docker configuratie finaliseren**
   - `docker-compose.prod.yml`
   - Environment variables
   - Volumes voor persistente data

2. **Nginx configuratie**
   - HTTPS terminatie (Let's Encrypt)
   - Reverse proxy naar FastAPI
   - Static files serving

3. **Security hardening**
   - CORS configuratie
   - CSP headers
   - httpOnly cookies voor tokens

4. **Monitoring setup**
   - Health check endpoint in Docker
   - Log aggregatie (optioneel: Loki)
   - Correlatie-ID middleware

5. **Acceptatie testen**
   - Testplan per rol
   - Data validatie na migratie
   - Performance tests

6. **Parallel run**
   - v0.7 en v0.8 naast elkaar
   - Data synchronisatie script (indien nodig)

#### Deliverables

- [ ] Docker images gebouwd en getest
- [ ] NAS deployment script
- [ ] HTTPS werkend
- [ ] Acceptatie testrapport
- [ ] Go/No-go besluit documentatie

---

### Fase 5: Go-Live & Nazorg (Week 15-16)

**Doel:** Productie overstap en stabilisatie

#### Week 15: Go-Live

1. Finale data migratie
2. DNS/routing aanpassen
3. v0.8 live zetten
4. Monitoring intensiveren
5. Gebruikers informeren

#### Week 16: Nazorg

1. Bug fixes
2. Performance optimalisatie
3. Gebruikersfeedback verwerken
4. Documentatie afronden

#### Deliverables

- [ ] v0.8 in productie
- [ ] Geen kritieke bugs
- [ ] Gebruikersdocumentatie
- [ ] Technische documentatie

---

## 4. Tijdlijn Overzicht

```
Week  1-2   Fase 0: Voorbereiding
Week  3-4   Fase 1: Database Migratie
Week  5-8   Fase 2: Backend Services
Week  9-12  Fase 3: Frontend Ontwikkeling
Week 13-14  Fase 4: Deployment & Testen
Week 15-16  Fase 5: Go-Live & Nazorg
```

**Totale doorlooptijd:** 16 weken

---

## 5. Risico's & Mitigaties

| Risico | Impact | Kans | Mitigatie |
|--------|--------|------|-----------|
| Data verlies tijdens migratie | Hoog | Laag | Meerdere backups, validatie scripts, rollback plan |
| TOTP setup te complex voor gebruikers | Medium | Medium | Duidelijke instructies, QR code, backup codes |
| VDSL instabiliteit | Medium | Hoog | PWA Service Worker, nette offline melding |
| Performance issues PostgreSQL | Medium | Laag | Query optimalisatie, indexen, connection pooling |
| Scope creep nieuwe features | Hoog | Medium | Strict houden aan blueprint, features parkeren voor v0.9 |
| Docker kennis ontbreekt | Medium | Medium | Documentatie, training, eenvoudige compose setup |

---

## 6. Dependencies

### Externe Dependencies

| Dependency | Versie | Doel |
|------------|--------|------|
| Python | 3.11+ | Runtime |
| FastAPI | 0.109+ | Web framework |
| SQLAlchemy | 2.0+ | ORM |
| Pydantic | 2.x | Validatie |
| Alembic | 1.13+ | Migraties |
| PostgreSQL | 16 | Database |
| HTMX | 1.9+ | Frontend interactiviteit |
| pyotp | 2.9+ | TOTP |
| slowapi | 0.1+ | Rate limiting |
| Docker | 24+ | Containerisatie |

### Interne Dependencies (v0.7 → v0.8)

| v0.7 Component | v0.8 Equivalent |
|----------------|-----------------|
| `src/services/applicatie/` | `backend/services/` |
| `src/services/domein/` | Geïntegreerd in services |
| `src/services/repo/` | SQLAlchemy ORM |
| `src/gui/schermen/` | `frontend/templates/pages/` |
| `src/kern/config.py` | `backend/config.py` + `.env` |

---

## 7. Team & Verantwoordelijkheden

| Rol | Verantwoordelijkheid |
|-----|---------------------|
| Lead Developer | Architectuur, code reviews, deployment |
| Backend Developer | Services, API, database |
| Frontend Developer | Templates, styling, HTMX |
| Tester | Test scripts, acceptatie tests |
| Systeembeheerder | NAS configuratie, Docker, HTTPS |

---

## 8. Success Criteria

### Functioneel

- [ ] Alle v0.7 functionaliteit beschikbaar in v0.8
- [ ] Login met TOTP/2FA werkt correct
- [ ] Multi-tenant scheiding (3 groepen) correct
- [ ] HR exports beschikbaar
- [ ] Rapporten genereerbaar

### Non-Functioneel

- [ ] Response tijd < 500ms voor normale operaties
- [ ] Beschikbaarheid > 99% (excl. gepland onderhoud)
- [ ] Werkt op Chrome, Firefox, Safari (mobiel + desktop)
- [ ] Nette offline melding bij verbindingsverlies
- [ ] Audit trail voor alle mutaties

### Technisch

- [ ] Unit test coverage > 80%
- [ ] Geen kritieke security issues
- [ ] Docker images < 500MB
- [ ] Database migratie reversible

---

## 9. Communicatieplan

| Moment | Doelgroep | Medium |
|--------|-----------|--------|
| Start Fase 0 | Team | Kickoff meeting |
| Einde elke fase | Team | Demo + retrospective |
| Week 12 | Stakeholders | Acceptatie test invite |
| Week 14 | Gebruikers | Informatiebrief go-live |
| Go-live | Alle gebruikers | Handleiding + support kanaal |

---

## 10. Referenties

| Document | Locatie |
|----------|---------|
| Blueprint v0.8 | `docs/voorstellen/Blueprint_v0.8.md` |
| Blueprint v0.7 | `docs/blueprint_master.md` |
| Development Guide | `docs/development_guide.md` |
| TODO items (uitgesteld) | `docs/plannen/todo_*.md` |

---

## Bijlage A: Checklist Nieuwe Feature (v0.8)

Voor elke nieuwe feature in v0.8:

1. [ ] **Model** — SQLAlchemy ORM + Alembic migratie
2. [ ] **Schema** — Pydantic request/response
3. [ ] **Service** — Business logica
4. [ ] **Unit Tests** — pytest
5. [ ] **Router** — FastAPI endpoint
6. [ ] **Template** — Jinja2 + HTMX
7. [ ] **Offline** — Controle PWA fallback
8. [ ] **Rechten** — `require_role()` dependency
9. [ ] **i18n** — Teksten in `locales/*.json`
10. [ ] **Audit** — AuditLog entry
11. [ ] **Logging** — Error logging in services

---

## Bijlage B: Rollback & Recovery Strategie

### Belangrijk: Database rollback is NIET mogelijk

Na migratie naar v0.8 (PostgreSQL) kan de database niet terug naar v0.7 (SQLite).
De app kan wel teruggedraaid worden, maar dan zonder recente data.

### Scenario 1: v0.8 App Bugs (database intact)

**Oplossing:** Fix in v0.8, geen rollback nodig

1. **Analyseren** — Root cause bepalen
2. **Hotfix** — Fix ontwikkelen en testen
3. **Deploy** — Nieuwe v0.8 versie uitrollen
4. **Communiceren** — Gebruikers informeren over fix

### Scenario 2: Kritieke v0.8 Problemen (app onbruikbaar)

**Oplossing:** Tijdelijk handmatig werken, v0.8 fixen

1. **Stoppen** — v0.8 containers stoppen
2. **Communiceren** — Gebruikers informeren, tijdelijke procedures
3. **Fixen** — Root cause oplossen
4. **Testen** — Grondig testen voor re-deploy
5. **Hervatten** — v0.8 opnieuw live

### Scenario 3: Data Corruptie in v0.8

**Oplossing:** Restore van backup + data recovery

1. **Stoppen** — v0.8 containers stoppen
2. **Analyseren** — Omvang corruptie bepalen
3. **Restore** — Laatste goede PostgreSQL backup terugzetten
4. **Recovery** — Verloren data reconstrueren (indien mogelijk)
5. **Fixen** — Oorzaak corruptie oplossen
6. **Hervatten** — Na grondige test

### Preventieve Maatregelen

| Maatregel | Frequentie | Doel |
|-----------|------------|------|
| PostgreSQL backup | Dagelijks | Point-in-time recovery |
| v0.7 DB backup bewaren | Eenmalig (pre-migratie) | Absolute noodoplossing |
| Transaction logs | Continu | Audit trail |
| Health monitoring | Continu | Vroegtijdige detectie |

### Absolute Noodscenario: Terug naar v0.7

**Let op:** Dit betekent VERLIES van alle data na de migratie naar v0.8.

Alleen te overwegen als:
- v0.8 fundamenteel onherstelbaar is
- Data verlies acceptabel is (of reconstrueerbaar uit andere bronnen)

Stappen:
1. v0.7 SQLite backup terugzetten
2. v0.7 app opnieuw installeren
3. Alle v0.8 wijzigingen handmatig invoeren (indien mogelijk)

---

**Document Einde**