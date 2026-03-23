# Plan: Organisatiestructuur + Rechten Refactor (v0.9)

**Status:** Goedgekeurd, nog niet gestart
**Aangemaakt:** 2026-03-23
**Bronnen:** `docs/voorstellen/Organisatiestructuur-voorstel.md` + `docs/voorstellen/autorisatie-rechten.md`
**Referentie:** `docs/referentie/autorisatie_model.md`

---

## Aanleiding

- `GebruikerRol.scope_id` is polymorfisch (soms `team_id`, soms `locatie_id`) → permissiebugs
- Planner = dubbel record (`teamlid` + `planner`) voor hetzelfde team
- HR kan enkel per locatie scopen, niet per area
- Rechten zijn niet consistent afgedwongen over alle routers

---

## Datamodel wijzigingen

### Nieuw: `Area`

```python
class Area(Base):
    __tablename__ = "areas"
    id: int (PK)
    uuid: str (uuid4, uniek, geïndexeerd)
    naam: str (uniek)
    code: str (uniek)
    is_actief: bool (default True)
    verwijderd_op: datetime | None
    verwijderd_door_id: int | None (FK → Gebruiker)
```

### Nieuw: `Lidmaatschap`

Vervangt `teamlid` + `planner` rollen in `GebruikerRol`.

```python
class LidmaatschapType(enum.Enum):
    vast = "Vast"
    reserve = "Reserve"
    detachering = "Detachering"

class Lidmaatschap(Base):
    __tablename__ = "lidmaatschappen"
    id: int (PK)
    gebruiker_id: int (FK → Gebruiker)
    team_id: int (FK → Team)
    is_planner: bool (default False)           # vervangt aparte "planner" rol
    type: LidmaatschapType (SQLAlchemy Enum)   # vervangt is_reserve bool
    is_actief: bool (default True)
    verwijderd_op: datetime | None
    verwijderd_door_id: int | None (FK → Gebruiker)

    __table_args__ = (
        # Partial unique index — laat re-activatie toe na soft-delete
        Index("uq_lidmaatschap_actief", "gebruiker_id", "team_id",
              unique=True, postgresql_where=text("verwijderd_op IS NULL")),
        # Ledenlijst per team (hot path)
        Index("ix_lidmaatschappen_team_id", "team_id",
              postgresql_where=text("is_actief = TRUE AND verwijderd_op IS NULL")),
        # Alle actieve teams voor gebruiker X — dekt ook Rode Lijn (index-only scan)
        Index("ix_lidmaatschappen_gebruiker_actief", "gebruiker_id", "team_id",
              postgresql_where=text("is_actief = TRUE AND verwijderd_op IS NULL")),
    )
```

> Geen `UniqueConstraint` — vervangen door de partial unique index. Een soft-deleted
> rij blokkeert anders re-activatie van hetzelfde (gebruiker_id, team_id) paar.

**Invariant:** elke gebruiker heeft altijd minstens 1 actief lidmaatschap.
Aanmaken van gebruiker + eerste lidmaatschap = atomische transactie in `GebruikerService`.

### Gewijzigd: `Locatie`

```python
+ area_id: int | None  # FK → Area, ON DELETE SET NULL, geïndexeerd
                       # Index: (area_id) WHERE is_actief AND verwijderd_op IS NULL
                       # → gebruikt door HR area-scope resolutie
```

### Gewijzigd: `GebruikerRol` — alleen nog admin-rollen

```python
class GebruikerRolType(enum.Enum):
    super_beheerder = "super_beheerder"
    beheerder = "beheerder"
    hr = "hr"
```

Rollen: `super_beheerder | beheerder | hr` (Python Enum + SQLAlchemy Enum kolom)

```python
- scope_id: int                # verwijderen — polymorfisch
+ scope_locatie_id: int | None # FK → Locatie, ON DELETE RESTRICT (voor: beheerder)
+ scope_area_id: int | None    # FK → Area,    ON DELETE RESTRICT (voor: hr)
```

DB constraints (beide als aparte `ALTER TABLE`):
```sql
-- Scope-combinatie per rol
CONSTRAINT chk_scope_combinatie CHECK (
    (rol = 'super_beheerder' AND scope_locatie_id IS NULL AND scope_area_id IS NULL)
    OR (rol = 'beheerder'    AND scope_locatie_id IS NOT NULL AND scope_area_id IS NULL)
    OR (rol = 'hr'           AND scope_locatie_id IS NULL)
)
-- Voorkomt stale rollen na migratie
CONSTRAINT chk_rol_geldig CHECK (rol IN ('super_beheerder', 'beheerder', 'hr'))
```

| Rol | scope_locatie_id | scope_area_id |
|---|---|---|
| `beheerder` | locatie_id | NULL |
| `hr` (area) | NULL | area_id |
| `hr` (nationaal) | NULL | NULL |
| `super_beheerder` | NULL | NULL |

### Gewijzigd: `Gebruiker`

```python
- locatie_id: int | None  # verwijderen — context afgeleid via Lidmaatschap → Team → Locatie
```

> `PlanningWijziging.locatie_id` blijft (afgeleid van team, niet van gebruiker).

---

## Rechtenmatrix

| Rol | Scope | Personeelsbeheer | Planning (shifts) | Verlof & Notities |
|---|---|---|---|---|
| super_beheerder | Nationaal | Full CRUD | Full CRUD | Full CRUD |
| hr (geen scope) | Nationaal | Read-only | Read-only | Read-only |
| hr (scope_area_id) | Area | Read-only (area) | Read-only | Read-only |
| beheerder | Locatie | Full CRUD incl. `is_planner` toekennen | **Read-only** (audit) | Read/Write (locatie) |
| planner (is_planner=True) | Team | Zoek-en-Koppel, `is_planner=False` only | Read/Write (team) | Read/Write (team) |
| werknemer (is_planner=False) | Eigen data | Geen | Read (team) | Read/Write (eigen) |

**Beheerder schrijft nooit planning** — enkel planners doen dat.
**Planner kent nooit `is_planner=True` toe** — enkel de beheerder doet dat.

---

## Planner Zoek-en-Koppel

Planners beheren zelf de bezetting van hun team, zonder tussenkomst van een beheerder.
De beheerder behoudt toezicht via het audit-log en is verantwoordelijk voor het toekennen van plannerrechten.

### Stroom

1. Planner zoekt op `gebruikersnaam` (nationaal uniek)
2. Gebruiker bestaat (ook op andere locatie) → `Lidmaatschap` aanmaken voor zijn team, `is_actief=True` direct
3. Gebruiker bestaat niet → basisprofiel aanmaken + `Lidmaatschap` (atomisch), `is_actief=True` direct
4. Nieuwe gebruiker krijgt altijd `is_planner=False` — planner kan dit niet zelf verhogen

### Autorisatieregels (security op bestemming, niet op bron)

- `LidmaatschapService` verifieert: heeft de uitvoerende planner `is_planner=True` op het doel-`team_id`?
- Herkomst van de gebruiker (bron-locatie) vormt geen blokkade
- Planner kan uitsluitend koppelen aan teams waarop hijzelf planner is
- Planner kan `is_planner` nooit op `True` zetten — ook niet via directe API-aanroep

### Privilege separation: wie mag wat

| Actie | Planner | Beheerder |
|---|---|---|
| Teamlid zoeken (nationaal) | ✅ | ✅ |
| Bestaande gebruiker koppelen aan team | ✅ (`is_planner=False`) | ✅ |
| Nieuw basisprofiel aanmaken + koppelen | ✅ (`is_planner=False`) | ✅ |
| `is_planner=True` toekennen | ❌ | ✅ |
| Rol `beheerder` / `hr` toekennen | ❌ | ✅ (eigen locatie/area) |
| Lidmaatschap verwijderen | ✅ (eigen team) | ✅ (hele locatie) |

### Audit-zichtbaarheid voor beheerder

Elke koppeling/aanmaak door een planner genereert een `AuditLog`-entry met:
`actie`, `planner_id`, `team_id`, `doelgebruiker_id`, `doelgebruiker_naam`, `bron_locatie_id`, `timestamp`.

`bron_locatie_id` maakt direct zichtbaar of een gebruiker van een andere locatie werd gekoppeld,
zonder dat de beheerder een tweede query nodig heeft.

Beheerder ontvangt een push-notificatie per nieuwe koppeling en heeft een dashboard-view
met alle recente lidmaatschapswijzigingen binnen zijn locatie. Binnen 24u kan hij een
koppeling annuleren via één actie (`verwijder_lid`).

### Service-methodes

- `LidmaatschapService.koppel_gebruiker(planner_id, team_id, gebruikersnaam, type)` — zoek bestaande gebruiker + koppel
- `GebruikerService.maak_en_koppel_als_planner(planner_id, team_id, naam, gebruikersnaam, type)` — aanmaken + koppel atomisch

> `maak_en_koppel` leeft in `GebruikerService`, **niet** in `LidmaatschapService`.
> Reden: aanmaken van een `Gebruiker` + eerste `Lidmaatschap` is één transactie waarvan
> `GebruikerService` eigenaar is (invariant). `LidmaatschapService` aanroepen vanuit
> `LidmaatschapService` zou een verboden Service→Service dependency zijn.

### Push-notificatie architectuur

`LidmaatschapService` mag `NotificatieService` niet aanroepen (Service→Service verboden).
Gekozen aanpak: **callback-parameter** (Option A):

```python
# LidmaatschapService.koppel_gebruiker() accepteert een optionele callback
def koppel_gebruiker(self, ..., on_voltooid: Callable[[Lidmaatschap], None] | None = None):
    ...
    if on_voltooid:
        on_voltooid(nieuw_lidmaatschap)

# Router wired de callback aan NotificatieService
def koppel_teamlid(request, ...):
    def stuur_notificatie(lid): notificatie_svc.stuur_push_beheerder(lid)
    lidmaatschap_svc.koppel_gebruiker(..., on_voltooid=stuur_notificatie)
```

De callback-aanpak houdt `LidmaatschapService` puur terwijl de notificatie gegarandeerd
afvuurt bij elke koppeling.

---

## Locatie-context (multi-locatie)

`Gebruiker.locatie_id` verdwijnt. `haal_actieve_locatie_id()` bepaalt de context per rol:

| Rol | Bron |
|---|---|
| planner / teamlid | `Lidmaatschap → Team → locatie_id` (cookie als override bij meerdere) |
| beheerder | `GebruikerRol.scope_locatie_id` |
| hr (area) | cookie, beperkt tot locaties in `scope_area_id` |
| hr (nationaal) / super_beheerder | cookie, alle locaties |

Locatie-switcher UI toont enkel als gebruiker > 1 locatie heeft.
`BaseRepository` interface **ongewijzigd** — ontvangt nog steeds `locatie_id: int | None`.

**Caching:** `haal_actieve_locatie_id()` doet bij HIGH-1 validatie een DB-lookup
(alle locaties voor de gebruiker via `Lidmaatschap → Team`). Gebruik `lru_cache` op de
allow-list query, gekeyed op `gebruiker_id`. Invalideren bij elke mutatie in
`LidmaatschapService` (`koppel_gebruiker`, `verwijder_lid`, reactivatie). TTL van 60s
als fallback. Niet cachen op `locatie_id` zelf — cookie kan per request verschillen.

---

## Rode Lijn — cross-locatie validatie

CAO-check valideert altijd op de **totale set** van de gebruiker over alle locaties, ongeacht de
actieve locatie-context. Zo worden conflicten bij detachering of reserve-werk onderschept.

```python
# ✅ Altijd alle lidmaatschappen meenemen in de Rode Lijn
alle_team_ids = lidmaatschap_service.haal_alle_actieve_team_ids(gebruiker_id)
```

---

## Multi-role perspectief (beheerder + planner)

Wanneer een gebruiker beide rollen heeft, schakelt de UI tussen twee perspectieven:
- **Operationeel (planner):** gefilterd op `team_id` waar `is_planner=True`
- **Beheer (beheerder):** gefilterd op `scope_locatie_id`

Implementatie: `actief_perspectief` cookie of query-param op relevante views.

---

## Migratie (Alembic — één script)

> **Verplichte volgorde:** `dependencies.py` en alle routers herschrijven *vóór* de migratie
> draait. Stap 6 verwijdert `scope_id` — code die die kolom nog raadpleegt crasht dan runtime.

1. `Area` tabel aanmaken
2. `Locatie.area_id` nullable FK toevoegen (`ON DELETE SET NULL`) + index aanmaken
3. `Lidmaatschap` tabel aanmaken inclusief alle indexes (partial unique + team + gebruiker)
4. `GebruikerRol.scope_locatie_id` + `scope_area_id` toevoegen (`ON DELETE RESTRICT`)
5. Data migreren:
   - Backup: `CREATE TABLE _backup_gr_teamlid_planner AS SELECT * FROM gebruiker_rollen WHERE rol IN ('teamlid', 'planner')` — vóór elke destructieve stap
   - `GebruikerRol` waar `rol IN ('teamlid', 'planner')` → `Lidmaatschap`
   - `GebruikerRol` beheerder/hr: `scope_id` → `scope_locatie_id`
6. CHECK constraints toevoegen op `GebruikerRol` (`chk_scope_combinatie` + `chk_rol_geldig`)
7. `GebruikerRol.scope_id` verwijderen
8. `GebruikerRol` records met `rol IN ('teamlid', 'planner')` verwijderen
   *(backup tabel uit stap 5 blijft staan tot verificatie is afgerond)*
9. `Gebruiker.locatie_id` verwijderen
10. `Gebruiker.rol` denormalisatieveld: update logica aanpassen — enkel nog hoogste `GebruikerRol.rol`
    (niet meer `teamlid`/`planner`); apart display veld voor `is_planner` afleiden uit `Lidmaatschap`

---

## Nieuwe bestanden

- [ ] `backend/models/area.py`
- [ ] `backend/models/lidmaatschap.py`
- [ ] `backend/api/routers/lidmaatschappen.py` — CRUD + Zoek-en-Koppel
- [ ] `backend/services/lidmaatschap_service.py`
- [ ] `backend/templates/components/locatie_switcher.html`
- [ ] Alembic migratie

## Gewijzigde bestanden

- [ ] `backend/models/locatie.py` — `area_id` toevoegen
- [ ] `backend/models/gebruiker_rol.py` — `scope_id` vervangen, rollen enum aanpassen
- [ ] `backend/models/gebruiker.py` — `locatie_id` verwijderen
- [ ] `backend/models/__init__.py` — nieuwe modellen registreren
- [ ] `backend/api/dependencies.py` — scope-functies + `haal_actieve_locatie_id` herschrijven
- [ ] `backend/services/gebruiker_service.py` — `maak_gebruiker_aan` vereist `team_id`; nieuw: `maak_en_koppel_als_planner()`
- [ ] `backend/templates/layouts/app.html` — locatie-switcher inladen
- [ ] `backend/seed.py` — seed aanpassen
- [ ] Alle 14+ routers die `heeft_rol_in_team` / `gebruiker.locatie_id` gebruiken

## Ongewijzigd (bewust)

- `BaseRepository._locatie_filter()` — interface gelijk
- Operationele modellen (Planning, Verlof, etc.)
- `PlanningWijziging.locatie_id`

> ⚠️ `LocatieGuardMiddleware` staat hier bewust NIET als "ongewijzigd" — zie security-blok hieronder.

---

## Security vereisten (pre-implementatie verplicht)

*Voortgekomen uit security audit op 2026-03-23. Alle HIGH-items zijn blokkerend voor go-live.*

### HIGH-1 — `locatie_context` cookie valideren tegen server-side allow-list

Cookie-waarde mag nooit blind als `locatie_id` doorgegeven worden aan `BaseRepository`.
`haal_actieve_locatie_id()` moet na het lezen van de cookie valideren of de waarde
voorkomt in de server-computed allow-list van de gebruiker:

- planner/teamlid: locaties bereikbaar via actieve `Lidmaatschap → Team → locatie_id`
- hr (area): locaties binnen `scope_area_id`
- hr (nationaal) / super_beheerder: alle actieve locaties

Bij ongeldige cookie-waarde: fallback naar primaire locatie + verdacht event loggen.
Validatie = DB-lookup (of `lru_cache`), nooit cookie-trust.

### HIGH-2 — `actief_perspectief` is een UI-hint, geen authorization oracle

De cookie/query-param die bepaalt of een beheerder+planner in "operationeel" of "beheer"
perspectief zit, mag **nooit** bepalen welke schrijfrechten worden uitgevoerd.
Elke route verifieert altijd de onderliggende rol opnieuw:

```python
# ✅ Elke mutatieactie verifieert zelf
if not heeft_rol_in_team(gebruiker.id, team_id, is_planner=True, db):
    raise HTTPException(403)

# ❌ Nooit
if request.cookies.get("actief_perspectief") == "planner":
    # ... schrijf planning
```

Perspectief-cookie mag uitsluitend UI-layout en default-filters sturen.
De cookie-waarde zelf moet ook gevalideerd worden: `beheerder`-perspectief alleen
toegestaan als de gebruiker een actieve `GebruikerRol(rol='beheerder')` heeft.

### HIGH-3 — `LocatieGuardMiddleware` afronden als onderdeel van déze refactor

`backend/api/middleware/locatie_guard.py` is momenteel een no-op (pass-through).
De middleware **moet** afgewerkt worden in deze refactor — niet daarna.

Minimale vereisten na refactor:
- Extraheer `locatie_id` uit JWT-context op elke geauthenticeerde request
- Sla op in `request.state.locatie_id` zodat routers niet opnieuw resolven
- Log elke super_beheerder-bypass expliciet (audittrail)
- Behandel ontbrekende `locatie_id` (orphan user) als HTTP 403, niet als None-filter

### HIGH-4 — Zoek-en-Koppel: validatieregels en privilege separation

**a) Security op bestemming, niet op bron:**
`LidmaatschapService` verifieert dat de uitvoerende planner `is_planner=True` heeft
op het doel-`team_id`. De herkomst van de gebruiker (bron-locatie) vormt geen blokkade.
Een planner kan uitsluitend koppelen aan teams waarop hijzelf planner is.

**b) Privilege separation — planner kan `is_planner` nooit verhogen:**
`maak_en_koppel()` en `koppel_gebruiker()` forceren altijd `is_planner=False`.
Geen parameter, geen override. Alleen `beheerder` en `super_beheerder` mogen
`is_planner=True` toekennen — via een aparte route met `vereiste_rol("beheerder")`.

**c) Directe activatie + push-notificatie + omkeervenster:**
Planner-aangemaakte accounts starten met `is_actief=True` — geen beheerder-goedkeuring nodig.
Rationale: deze tool doet uitsluitend selfrostering. HR reviewt de roosters 1,5 maand vóór de
effectieve datum (bijv. op 19/03 wordt mei vrijgegeven). Er zijn geen directe loon- of
aanwervingsgevolgen aan een nieuw account.

Bij elke koppeling/aanmaak:
- Directe push-notificatie naar de beheerder van de locatie
- Omkeervenster van 24u: beheerder kan het lidmaatschap annuleren via één actie
- `AuditLog`-entry met: `planner_id`, `team_id`, `doelgebruiker_id`, `volledige_naam`, `bron_locatie_id`, `timestamp`
- Beheerder heeft een dashboard-view met alle recente lidmaatschapswijzigingen op zijn locatie

**d) Rate limiting:**
- Zoek-endpoint: max 3 zoekopdrachten/uur per user-sessie (niet per IP — gedeeld NAT op productievloer)
- Aanmaak-endpoint: max 3 nieuwe gebruikersprofielen per planner per 24u (reset om middernacht), per user-sessie
- Beheerder heeft verhoogde limieten voor bulk-acties
- Elke mislukte zoekopdracht (gebruikersnaam niet gevonden) wordt gelogd voor nationaal audit
- Zoekbereik blijft nationaal — vereist voor multi-locatie gebruik

---

### MEDIUM-1 — DB `CHECK` constraint op `GebruikerRol`

Toevoegen in de Alembic-migratie:

```sql
ALTER TABLE gebruiker_rollen ADD CONSTRAINT chk_scope_combinatie CHECK (
    (rol = 'super_beheerder' AND scope_locatie_id IS NULL AND scope_area_id IS NULL)
    OR (rol = 'beheerder'    AND scope_locatie_id IS NOT NULL AND scope_area_id IS NULL)
    OR (rol = 'hr'           AND scope_locatie_id IS NULL)
);
```

Aanvullend: `@validates` op het SQLAlchemy-model als tweede laag.
Zonder deze constraint kan een `beheerder` met beide FKs NULL doorvallen naar
`locatie_id=None` → ongefiltered lezen als super_beheerder.

### MEDIUM-2 — HR read-only afdwingen via expliciete dependency

`vereiste_hr_of_hoger()` in `dependencies.py` geeft HR momenteel ook schrijftoegang.
Nieuwe conventie: alle mutatie-endpoints gebruiken `vereiste_schrijfrechten()`,
een nieuwe dependency die `hr` expliciet uitsluit:

```python
def vereiste_schrijfrechten():
    """Staat toe: planner (via Lidmaatschap), beheerder, super_beheerder. Blokkeert: hr."""
```

Documenteer deze conventie in `CLAUDE.md` zodat toekomstige routes het niet missen.

### MEDIUM-3 — Rode Lijn cross-locatie: structureel afdwingen

`LidmaatschapService` krijgt een aparte methode die intern **altijd** `locatie_id=None` gebruikt:

```python
def haal_alle_actieve_team_ids_nationaal(self, gebruiker_id: int) -> list[int]:
    """Geeft alle actieve team-ids van de gebruiker over ALLE locaties.
    Bewust zonder locatie-filter — voor Rode Lijn CAO-validatie."""
```

Nooit de gewone `haal_team_ids()` gebruiken in de Rode Lijn — naam maakt het onderscheid expliciet.

### MEDIUM-4 — Orphan user bij mislukte transactie → HTTP 403, niet None-filter

Als `haal_actieve_locatie_id()` voor een gebruiker geen enkel actief lidmaatschap vindt:
- Geef HTTP 403 terug ("account onvolledig")
- Log als data-integriteitswaarschuwing voor de beheerder
- Nooit `None` teruggeven (want `None` = super_beheerder-filter in `BaseRepository`)

---

### Kritieke implementatievolgorde (Gap C)

`dependencies.py` bevat 4 functies die `GebruikerRol.scope_id` queryen:
`heeft_rol_in_team`, `haal_primaire_team_id`, `haal_planner_team_ids`, `heeft_rol_in_locatie`.

**Stap 6 van de migratie verwijdert die kolom.** Code moet herschreven zijn
**vóór** de migratie draait — anders runtime errors op alle 14+ routers.

Verplichte volgorde:
1. Herschrijf `dependencies.py` (queries naar `Lidmaatschap` / `scope_locatie_id`)
2. Herschrijf alle routers die deze functies aanroepen
3. **Dan pas** Alembic-migratie uitvoeren

---

## Verificatie

---

## Verificatie

### Happy path
- [ ] Seed opnieuw uitvoeren, DB schoon
- [ ] Werknemer ziet enkel eigen team-planning
- [ ] Planner ziet en schrijft enkel zijn teams
- [ ] Planner kan via Zoek-en-Koppel teamlid toevoegen zonder beheerder
- [ ] Beheerder kan instellingen en personeelsbeheer doen
- [ ] Area HR ziet enkel locaties in zijn area
- [ ] Nationaal HR (geen scope) ziet alles
- [ ] Super_beheerder ziet en schrijft alles
- [ ] Multi-locatie gebruiker: locatie-switcher verschijnt en werkt
- [ ] Rode Lijn valideert over alle locaties, niet enkel actieve context
- [ ] Gebruiker aanmaken zonder `team_id` → geweigerd door service
- [ ] Laatste lidmaatschap verwijderen → geweigerd door service

### Negatieve testcases (security)
- [ ] Planner manipuleert `locatie_context` cookie naar andere tenant → eigen data, niet vreemde data
- [ ] Planner probeert planning te schrijven voor team zonder `is_planner=True` → HTTP 403
- [ ] HR (nationaal) probeert POST op planning-endpoint → HTTP 403
- [ ] HR (area) probeert data op te halen van locatie buiten zijn area → HTTP 403
- [ ] Beheerder probeert shift te schrijven → HTTP 403
- [ ] `actief_perspectief=beheerder` cookie zonder beheerder-rol → geen extra rechten
- [ ] `GebruikerRol(rol='beheerder', scope_locatie_id=NULL)` aanmaken → DB constraint error
- [ ] Orphan user (geen lidmaatschap) logt in → HTTP 403, niet ongefiltered
- [ ] Planner zoekt username meer dan 3x/uur → rate limit actief (per user-sessie)
- [ ] Planner maakt meer dan 3 nieuwe profielen/24u aan → rate limit actief (per user-sessie)
- [ ] Planner koppelt `team_id` van een team waarop hij geen planner is → HTTP 403
- [ ] Planner probeert `is_planner=True` te zetten via API → genegeerd of HTTP 403
- [ ] Beheerder-aanmaak heeft verhoogde limieten t.o.v. planner
- [ ] Nieuwe koppeling door planner → AuditLog-entry aanwezig, zichtbaar voor beheerder
