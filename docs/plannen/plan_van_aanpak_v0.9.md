# Plan van Aanpak: Planningtool v0.9

## Context

**Startpunt:**
- `code_v07/src/` — **Primaire broncode.** Volwassen PyQt6 desktop app (v0.7.51), live en productiegekwalificeerd. ~178 Python-bestanden, waarvan ~120 puur businesslogica (services/applicatie, services/domein, services/repo). De GUI-laag (~59 bestanden) vervalt — die functie neemt de web-frontend over.
- `code_v08/backend/` — **Infrastructuurreferentie.** FastAPI-geraamte, Docker-setup, PostgreSQL/Alembic-patronen, JWT/TOTP-auth, HTMX-templates. De businesslogica in v0.8 is onvolledig en minder volwassen dan v0.7.

**Strategie:**
> v0.7 businesslogica porten naar een FastAPI/PostgreSQL-weblaag, met v0.8 als infrastructuurreferentie.

Niet: v0.8 uitbreiden met features uit v0.7.
Wel: v0.7 services/domein/validators/repo's aanpassen voor PostgreSQL + SQLAlchemy 2.x + FastAPI, en de GUI vervangen door Jinja2/HTMX-templates.

**Waarom niet gewoon v0.8 uitbreiden?**
- v0.8 businesslogica is onvolledig (mist validators, rode lijn, ADV, typetabellen, schermrechten, ...)
- v0.7 heeft die logica al correct geïmplementeerd, live getest en in gebruik
- Herbouwen vanaf v0.8 = al die logica opnieuw schrijven; porten vanuit v0.7 = bewezen code hergebruiken

---

## Organisatiestructuur (Realiteit)

Het bedrijf heeft ~10 productielocaties verdeeld over 5 area's, nationaal. De app moet dat ondersteunen:

```
Nationaal
  └── Area (label, niet apart niveau in de app)
        └── Locatie  ← beheerniveau (beheerder per locatie)
              └── Team (PAT, TO, ...)  ← planning-eenheid
                    └── Gebruiker (full lid of reserve)
```

**Huidig gebruik:** 1 locatie, 2 teams (PAT + TO), aparte SQLite databases → samenvoegen.

---

## Datamodel Architectuur (KERN)

### Drie-domein principe

Het datamodel is bewust opgedeeld in drie gescheiden domeinen. Een nieuw model hoort altijd in precies één domein thuis.

```
1️⃣  ORGANISATIE          2️⃣  AUTORISATIE         3️⃣  OPERATIES
────────────────          ─────────────────        ──────────────────
Locatie                   GebruikerRol             Planning
Team                                               PlanningWijziging
Gebruiker                                          Verlof
                                                   VerlofTeamStatus
                                                   Notitie
                                                   Shiftcode
                                                   NationaleHRRegel
                                                   LocatieHROverride
                                                   RodeLijnConfig
                                                   AuditLog
```

**Relatieschema:**
```
                Gebruiker
                    │
     ┌──────────────┼──────────────┐
     │              │              │
GebruikerRol    GebruikerRol     Verlof
(teamlid/planner) (beheerder/hr)   │
     │              │        VerlofTeamStatus
     └──── Team ────┘              │
              │                    │
              └────────────────────┘
              │
           Locatie
              │
      LocatieHROverride
              │
       NationaleHRRegel

Team ──── Planning
          PlanningWijziging

RodeLijnConfig    (nationaal — exact één record, referentiedatum)
Notitie           (van/naar Gebruiker, via scope)
AuditLog          (elke mutatie)
```

**Regel:** Domein 1 (Organisatie) kent Domein 2 en 3 niet. Domein 2 (Autorisatie) verwijst naar Domein 1. Domein 3 (Operaties) verwijst naar Domein 1; nooit rechtstreeks naar Domein 2. Permissies worden altijd via de service/router afgedwongen, nooit ingebakken in operationele modellen.

---

### Modellen

```python
class NationaleHRRegel:          # beheerd door super_beheerder
    id, code, waarde, ernst_niveau, richting ("max"/"min"), beschrijving, is_actief
    # Voorbeeld: code="MAX_DAGEN_OP_RIJ", waarde=7, richting="max"

class Locatie:
    id, naam, code, area_label, is_actief

class LocatieHROverride:         # beheerd door lokale beheerder
    id, nationale_regel_id → NationaleHRRegel
    locatie_id → Locatie
    waarde    # STRENGER dan nationaal:
              #   richting="max" → waarde <= nationale.waarde (bv. 5 ≤ 7)
              #   richting="min" → waarde >= nationale.waarde (bv. 12 ≥ 11)

class Team:                      # was "Groep" in v0.8 — HERNOEMD
    id, naam, code, locatie_id → Locatie, is_actief

class Gebruiker:
    id, gebruikersnaam, wachtwoord_hash, totp_actief, taal, is_actief
    # GEEN 'rol' veld meer — rollen zitten in GebruikerRol

class GebruikerRol:              # NIEUW — vervangt Gebruiker.rol + GebruikerGroep
    id
    gebruiker_id → Gebruiker
    rol          # Enum: zie rollenlijst hieronder
    scope_id     # team_id (voor teamlid/planner)
                 # locatie_id (voor beheerder/hr)
                 # NOOIT None — super_beheerder krijgt scope_id van de vaste 'Nationaal' locatie
    is_reserve   # bool, default False — enkel relevant bij rol=teamlid
                 # True → lid verschijnt in grid maar kan worden uitgefilterd
    is_actief
    # ARCHITECTUURBESLISSING — Polymorfische FK (bewuste trade-off):
    # scope_id is een integer die ofwel naar teams.id ofwel naar locaties.id wijst,
    # afhankelijk van de rol. De database kan deze relatie NIET afdwingen via een FK-constraint.
    # Dit is een bewuste keuze voor eenvoud; de applicatielaag is verantwoordelijk voor correctheid.
    #
    # De rol-waarde bepaalt de betekenis van scope_id:
    #   teamlid/planner  → scope_id = team_id      (teams.id)
    #   beheerder/hr     → scope_id = locatie_id   (locaties.id, echte locatie)
    #   super_beheerder  → scope_id = locatie_id   (locaties.id, altijd Locatie(code='NAT'))
    #
    # Gebruik altijd de service-helper interpreteer_scope(rol, scope_id) → (type, object)
    # en NOOIT rechtstreeks scope_id zonder de rol mee te controleren.
    #
    # CODEREGEL (afdwingbaar via code review):
    #   ❌ VERBODEN:  db.query(GebruikerRol).filter(GebruikerRol.scope_id == x)
    #   ✅ VERPLICHT: scope_service.haal_leden_op(rol, scope_id)  of  interpreteer_scope(rol, scope_id)

class Verlof:                    # persoonlijke aanvraag — niet gekoppeld aan één team
    id
    gebruiker_id      → Gebruiker   # voor wie is het verlof
    ingediend_door_id → Gebruiker | None
    # None = teamlid heeft zelf ingediend
    # ingevuld = planner heeft ingediend namens het teamlid (eigen team, beperkte permissie)
    reden_namens: str | None
    # Verplicht als ingediend_door_id ingevuld is, anders None
    # Wordt opgenomen in automatische notitie naar het teamlid
    datum_van, datum_tot
    type          # jaarlijks | ziekte | ADV | ...
    opmerking
    aangemaakt_op
    # Geen globale status — status wordt per team bijgehouden in VerlofTeamStatus

class VerlofTeamStatus:          # per-team status — aangemaakt voor elk team waar gebruiker lid van is
    id
    verlof_id  → Verlof
    team_id    → Team
    status        # aangevraagd | goedgekeurd | geweigerd
    aangemaakt_op # timestamp aanmaak — audit: "wanneer ontving de planner dit?"
    behandeld_door_id → Gebruiker  # nullable — wie heeft beslist?
    behandeld_op                   # nullable — wanneer is er beslist?

class PlanningWijziging:         # audit log specifiek voor grid-bewerkingen
    id
    gebruiker_id → Gebruiker
    team_id      → Team
    locatie_id   → Locatie       # gedenormaliseerd voor directe BaseRepository-filter
    datum        # de planningsdag die gewijzigd werd
    oude_shift   # nullable — shift-code voor de wijziging
    nieuwe_shift # nullable — shift-code na de wijziging
    tijdstip     # wanneer de wijziging plaatsvond
    # Basis voor toekomstige undo / history / diff viewer

class Shiftcode:                 # werkshift of speciale code
    id, code, naam, kleur
    locatie_id   → Locatie       # nullable — None = nationaal beschikbaar voor alle locaties
    type         # 'werk' | 'rust' | 'verlof' | 'speciaal'
    telt_als_werkdag: bool        # telt mee voor de 19-dagenregel in rode lijn periode
    is_nachtprestatie: bool       # activeert de nacht-vervolgingsbeperking
    reset_nacht: bool             # heft de nacht-vervolgingsbeperking op voor de volgende shift
    is_actief: bool

class RodeLijnConfig:            # EXACT ÉÉN globaal record — nationaal
    id
    referentie_datum: date        # alle cyclussen berekend als referentie_datum + n×28
    # Beheerd door super_beheerder
    # Rode lijn datums worden NOOIT als lijst opgeslagen — altijd berekend
    # Blokgrootte staat in NationaleHRRegel(code='RODE_LIJN_BLOK_GROOTTE')

# NationaleHRRegel seed:
# code='RODE_LIJN_BLOK_GROOTTE', waarde=1, richting='max', beschrijving='Aantal aaneengesloten rode-lijn-periodes per blok'
# richting='max' → locatie override mag LAGER (strenger = kleiner blok)
# Voorbeeld: nationaal=3 → locatie kan terugzetten naar 1 of 2

# Blokberekening (services/domein/rode_lijn.py — pure Python):
# periode_nr = (datum - referentie_datum).days // 28
# blok_nr    = periode_nr // blok_grootte         ← vaste blokken, GEEN rolling window
# blok_start = referentie_datum + blok_nr * blok_grootte * 28 dagen
# blok_einde = blok_start + blok_grootte * 28 - 1 dagen
# max_werkdagen = blok_grootte × 19

# Vaste systeemlocatie (aangemaakt bij initialisatie, nooit verwijderbaar):
# Locatie(id=1, naam='Nationaal', code='NAT', area_label=None, is_actief=True)
```

### Modelconventies (gelden voor alle hoofdmodellen)

**Soft delete:**
Alle hoofdmodellen (`Gebruiker`, `Team`, `Locatie`, `Verlof`, `GebruikerRol`, ...) hebben:
```python
is_actief:         bool      # default True
verwijderd_op:     datetime | None   # default None
verwijderd_door_id: int | None       # FK → Gebruiker, default None
```
Records worden nooit fysiek verwijderd. Queries filteren standaard op `is_actief=True` in de `BaseRepository`.

**UUID voor API-paden:**
Modellen die via API-endpoints blootgesteld worden krijgen een extra `uuid` kolom:
```python
uuid: str   # server-side gegenereerd (uuid4), uniek, geïndexeerd
```
- Interne queries: altijd op `id` (integer, performance)
- API-paden: altijd op `uuid` (bijv. `/teams/9f12c45a-...`, `/gebruikers/3b8e1f2c-...`)
- Voorkomt enumeration-aanvallen; makkelijkere export/import

**Notitie mailbox — toekomstig uitbreidingspad:**
Huidig model (`gelezen bool`) is voldoende voor een interne tool. Mocht later per-gebruiker read-status, threads of mentions nodig zijn, wordt uitgebreid naar:
```python
# Toekomstig (nu NIET bouwen):
class NotitieOntvanger:
    notitie_id → Notitie
    gebruiker_id → Gebruiker
    gelezen: bool
```
Huidig `Notitie.gelezen` blijft tot die tijd.

**Validators** lezen: `LocatieHROverride.waarde` indien aanwezig voor die locatie, anders `NationaleHRRegel.waarde`.

### Architectuurbeslissing: Area als label (geen model)

**Beslissing: Area is een string-label op `Locatie`, geen apart databankobject.**

```python
class Locatie:
    id, naam, code, area_label, is_actief   # area_label = bijv. "West-Vlaanderen"
```

**Motivatie:** Area is puur organisatorisch. Er zijn geen rechten, geen queries, geen dashboards op area-niveau nodig in de huidige scope. Een apart `Area`-model zou infrastructuur toevoegen zonder directe meerwaarde.

**Toekomstige uitbreiding:** Als rapportage of rechten per area nodig worden, wordt `area_label` vervangen door een FK `area_id → Area(id, naam)`. Migratie is een simpele `ALTER TABLE`; geen dataloss.

---

### Architectuurbeslissing: Rode lijnen — arbeidscyclussysteem

**Rode lijnen zijn GEEN geblokkeerde periodes.** Het zijn de grenzen van een nationaal arbeidscyclussysteem van 28 dagen.

**Regels:**
- Elke cyclus duurt exact **28 dagen**, startend van een nationale referentiedatum
- Binnen elke cyclus: max **19 gewerkte of gelijkgestelde dagen** (bepaald door `Shiftcode.telt_als_werkdag`)
- Binnen elke cyclus: elke **CXW (zaterdag)** en **RXW (zondag)** die erin valt moet ingepland zijn
- Cyclussen worden **nooit als records opgeslagen** — altijd berekend als `referentie_datum + n × 28`

**Blokgrootte (samenvoegen van periodes):**
- Beheerd via `NationaleHRRegel(code='RODE_LIJN_BLOK_GROOTTE', waarde=1, richting='max')`
- Blokken zijn **vast en niet-overlappend**: periodes 0-2 = blok 1, periodes 3-5 = blok 2, enz. — GEEN rolling window
- Blok van grootte 3: max 57 werkdagen, alle CXW/RXW van de 3 periodes moeten opgenomen zijn
- Locatie kan blokgrootte **verlagen** (strenger), nooit verhogen: `LocatieHROverride.waarde ≤ nationale.waarde`
- Huidige situatie: blokgrootte = 1 (nationale standaard); samenvoegen nog niet van toepassing

**Nachtprestatie-beperking (via Shiftcode):**
- Shiftcodes met `is_nachtprestatie=True` activeren een beperking op de eerstvolgende shift
- Na een nachtprestatie moet er een shift met `reset_nacht=True` staan vóór een gewone shift mogelijk is
- `RXGapValidator` en `DubbeleShiftValidator` valideren dit

**Planninggrid weergave:**
- Rode lijn datums worden berekend en visueel als rode verticale lijn getoond op het grid
- Teller per gebruiker: gewerkte dagen in huidige periode/blok (vóór en na de rode lijn)
- Validator waarschuwt bij overschrijding 19-dagenregel of ontbrekende CXW/RXW

### Rollen — ontkoppeld en meervoudig

Rollen zijn **niet hiërarchisch** — iemand kan meerdere rollen tegelijk hebben met verschillende scopes:

| Rol | Scope | Rechten |
|---|---|---|
| `super_beheerder` | Nationaal (scope_id = Locatie 'NAT') | Nationale HR defaults beheren, locaties aanmaken, beheerders aanduiden |
| `beheerder` | Locatie | Gebruikers aanmaken, **teams aanmaken**, **planner aanduiden per team**, HR overrides, instellingen. Leesr. op alle teams. Bemoeit zich NIET met individuele teamleden. |
| `hr` | Locatie | Read-only op planning/teams/verlof van die locatie. Niets aanpassen. |
| `planner` | Team | **Teamleden toevoegen/verwijderen**, **vast of reserve markeren** (`is_reserve`), planning bewerken, verlof goedkeuren |
| `teamlid` | Team | Eigen planning zien, verlof aanvragen. Verschijnt als rij in planning. `is_reserve=True` → uitfilterbaar. |

**Werkstroom teamopbouw:**
```
1. Beheerder maakt team aan: Team(naam="PAT – Permanentie Algemeen Toezicht", code="PAT")
2. Beheerder duidt planner aan: GebruikerRol(rol=planner, scope_id=team_PAT)
3. Planner voegt leden toe:    GebruikerRol(rol=teamlid, scope_id=team_PAT, is_reserve=False)
                                GebruikerRol(rol=teamlid, scope_id=team_PAT, is_reserve=True)
   → Beheerder ziet dit maar past het NIET aan
```

**Voorbeelden:**
```
Gebruiker X (jijzelf):
  teamlid   (PAT – Permanentie Algemeen Toezicht, is_reserve=False)
  planner   (PAT – Permanentie Algemeen Toezicht)
  beheerder (Locatie Antwerpen)
  super_beheerder (NAT)

Alice:  teamlid (PAT, is_reserve=False) + teamlid (TO, is_reserve=True)
        → staat als vaste rij in PAT-planning, uitfilterbaar in TO-planning

Bob:    beheerder (Locatie Antwerpen)  [geen teamlidmaatschap]
        → maakt teams aan, duidt planners aan
        → ziet alle planningen van de locatie (read)
        → staat NIET als rij in enige planning

Carole: hr (Locatie Antwerpen)
        → ziet planning/teams/verlof (read-only), past NIETS aan
```

### Planninggrid filtering

- **Leden in grid:** enkel gebruikers met `rol IN (teamlid, planner)` voor dat `team_id`
- **Reservefilter:** gebruikers met `is_reserve=True` kunnen worden uitgefilterd via een toggle in de UI
- **Beheerder/HR zonder teamlidmaatschap:** ziet het grid, staat er NIET in als rij
- **Beheerder/HR mét teamlidmaatschap:** staat WEL als rij in het grid van dat team

### Verlof — per-team status

Bij het aanmaken van een verlofaanvraag:
1. Systeem maakt één `Verlof` record aan
2. Systeem zoekt alle teams waar gebruiker `teamlid` of `planner` is
3. Systeem maakt per team een `VerlofTeamStatus(status='aangevraagd')` aan → belandt in mailbox van alle betrokken planners

**Planner-view (per team):**
- Lijst aanvragen van hun teamleden, elk met status `aangevraagd | goedgekeurd | geweigerd`
- Heatmap: `COUNT` van verloven per dag (alle statussen zichtbaar, kleurcodering per drukte)

**Teamlid-view:**
- Eigen aanvragen + status per team
- Verlofoverzicht van het team: heatmap wie wanneer verlof heeft (ook `geweigerd` zichtbaar → collega's zien bezette periodes)

**Multi-team gebruiker:** dient één aanvraag in, planners van **alle** teams ontvangen notificatie en behandelen onafhankelijk van elkaar.

**Planner dient in namens teamlid:**
- Planner kan verlof indienen voor elk lid van **hun eigen team** (`ingediend_door_id` wordt ingevuld)
- `reden_namens` is **verplicht** als `ingediend_door_id` ingevuld is — planner moet motiveren
- Na aanmaken stuurt het systeem automatisch een **notitie** naar het teamlid:
  `"[Planner X] heeft verlof ingediend voor [datum_van – datum_tot]. Reden: [reden_namens]"`
- Verdere verwerking identiek aan zelf-ingediend verlof
- Teamlid ziet de aanvraag in hun eigen verlofoverzicht, met vermelding wie het indiende en de reden
- Audit trail: `ingediend_door_id` + `reden_namens` maken duidelijk wie de aanvraag aanmaakte en waarom

### Permissies checken (helper)

```python
def heeft_rol(gebruiker_id, rollen: list[str], scope_id: int | None = None) -> bool:
    # Kijkt of gebruiker minstens één van de opgegeven rollen heeft
    # voor de gegeven scope (team_id of locatie_id of nationaal)
    ...
```

Voorbeeldgebruik in routers/services:
```python
NAT_LOCATIE_CODE = "NAT"  # systeemconstante

# Mag alleen planner van dit team:
heeft_rol(user.id, ["planner"], scope_id=team_id)

# Mag beheerder van deze locatie OF super_beheerder (via NAT-locatie):
heeft_rol(user.id, ["beheerder"], scope_id=locatie_id) or
heeft_rol(user.id, ["super_beheerder"], scope_id=nat_locatie_id)

# Is teamlid of planner van ENIG team in deze locatie:
heeft_rol_in_locatie(user.id, ["teamlid", "planner"], locatie_id=locatie_id)
```

### Data-isolatie

- Alle queries filteren op `locatie_id` via de rollen van de ingelogde gebruiker
- Planning queries filteren op `team_id`
- `super_beheerder`: geen locatie-filter (ziet alles)
- `beheerder` + `hr`: lezen alle teams van hun locatie, schrijven enkel via beheerder-rechten

### Notities & Mailboxhiërarchie

Berichten volgen de organisatiehiërarchie. Er zijn **4 berichttypen**:

```python
class Notitie:
    id
    van_gebruiker_id  → Gebruiker

    # Optie A: direct naar een persoon
    naar_gebruiker_id → Gebruiker (nullable)

    # Optie B: naar een gedeelde rolmailbox
    naar_rol          # 'planners' | 'beheerders' | 'super_beheerders' (nullable)
    naar_scope_id     # team_id | locatie_id | nat_locatie_id
    # Constraint: precies één van (naar_gebruiker_id, naar_rol) is ingevuld

    bericht, prioriteit, gelezen, aangemaakt_op
```

**Mailboxhiërarchie:**

| Van | Naar mailbox | scope_id |
|---|---|---|
| teamlid (vast of reserve) | `planners` | team_id van afzender |
| planner | `beheerders` | locatie_id van afzender |
| beheerder | `super_beheerders` | nat_locatie_id (NAT) |
| Iedereen | direct naar gebruiker | — |

**Wie ziet welke mailbox:**
- `planners`-mailbox van team X → zichtbaar voor alle gebruikers met `planner`-rol voor team X
- `beheerders`-mailbox van locatie Y → zichtbaar voor alle gebruikers met `beheerder`-rol voor locatie Y
- `super_beheerders`-mailbox → zichtbaar voor alle gebruikers met `super_beheerder`-rol

**Stuur-rechten:**
- Teamlid (vast of reserve) stuurt naar `planners` van hun eigen team(s)
- Planner stuurt naar `beheerders` van hun locatie
- Beheerder stuurt naar `super_beheerders`
- Iedereen kan direct berichten sturen naar een andere gebruiker (zelfde locatie)

**Migratie:** PAT.db notities → `naar_rol='planners'`, `naar_scope_id=team_PAT_id`; TO.db → idem voor TO

### Hernoeming: Groep → Team

Alle verwijzingen naar `Groep`/`groep` in v0.8 code worden hernoemd naar `Team`/`team`:
- `models/groep.py` → `models/team.py`
- `groep_id` → `team_id` (in Planning, Notitie, Shiftcode, AuditLog)
- `Verlof` verliest `team_id` → status per team via `VerlofTeamStatus`
- `GebruikerGroep` → vervangen door `GebruikerRol` (met `is_reserve` vlag ipv aparte reserve-rol)
- `GroepConfig` → `TeamConfig`
- Router `/groepen` → `/teams`
- i18n sleutels `groep.*` → `team.*`

---

## Wat komt waarvandaan

### Uit v0.7 — businesslogica (PRIMAIRE BRON)

v0.7-bestanden worden geport: SQLite-specifieke databasetoegang vervangen door SQLAlchemy 2.x, PyQt6-GUI-imports verwijderd, aanpassen aan multi-locatie architectuur.

| v0.7 component | Bestand(en) | Port-aanpak |
|---|---|---|
| **Domeinlaag** | `services/domein/*.py` (~20 bestanden) | Direct hergebruiken — pure Python, geen DB-afhankelijkheden |
| **Validators** (10 stuks) | `services/domein/validators/*.py` | Direct hergebruiken — pure Python |
| **Planning** | `services/applicatie/planning_service.py` | SQLite → SQLAlchemy; `groep_id` → `team_id + locatie_id` |
| **Verlof** | `services/applicatie/verlof_service.py`, `verlof_saldo_service.py` | Aanpassen: multi-team `VerlofTeamStatus` ipv één status |
| **Rode lijn** | `services/applicatie/rode_lijn_service.py` | Aanpassen: `RodeLijnConfig` model, blokgrootte via `NationaleHRRegel` |
| **Shiftcodes** | `services/applicatie/shiftcode_service.py`, `services/domein/shiftcode_domein.py` | Aanpassen: `locatie_id` nullable, nationale vs. lokale codes |
| **HR-regels** | `services/applicatie/hr_regel_beheer_service.py` | Aanpassen: twee-laags (`NationaleHRRegel` + `LocatieHROverride`) |
| **Gebruikers** | `services/applicatie/gebruiker_service.py` | Aanpassen: `GebruikerRol` ipv `Gebruiker.rol` |
| **Teams** | `services/applicatie/team_service.py` | Aanpassen: `Team.locatie_id` toevoegen |
| **Notities** | `services/applicatie/notitie_service.py` | Herbouwen: mailboxhiërarchie per rol/scope |
| **ADV** | `services/applicatie/adv_service.py` | Direct porten |
| **Typetabellen** | `services/applicatie/typetabel_service.py` | Direct porten |
| **Schermrechten** | `services/applicatie/scherm_rechten_service.py` | Direct porten |
| **Logboek** | `services/applicatie/logboek_service.py` | Direct porten |
| **Rapporten/export** | `services/applicatie/rapport_service.py`, `rapport_excel_export.py` | Direct porten |
| **Rotatie/suggesties** | `services/applicatie/rotatie_service.py`, `suggestie_service.py` | Direct porten |
| **Auto-scheduling** | `services/applicatie/auto_scheduling_service.py` | Direct porten |
| **Repositories** | `services/repo/*.py` (~18 bestanden) | Herschrijven: SQLite → SQLAlchemy 2.x + BaseRepository |

### Uit v0.8 — infrastructuur (REFERENTIE)

v0.8 wordt NIET gekopieerd als startpunt. Wel als referentie voor patronen.

| v0.8 component | Gebruik |
|---|---|
| `docker-compose.yml` patroon | Init-container migratie, named volumes, healthcheck |
| `Dockerfile` | Python 3.12-image, dependencies, startup |
| FastAPI app-structuur (`main.py`, `api/`, `database.py`) | Router-structuur, lifespan, middleware-volgorde |
| Auth: JWT httpOnly cookie + TOTP | Referentie-implementatie — ported met argon2-cffi ipv passlib |
| CSRF + rate limiting | Referentie-implementatie |
| Alembic-setup | `alembic.ini`, `env.py`, migratie-patronen |
| Jinja2 templates (43) | Referentie voor HTMX-patronen en template-structuur |
| i18n mechanisme | Referentie — zelfde sleutels, uitgebreid met v0.7-vocabulaire |

---

## Wat te bouwen (per laag)

### Nieuw in v0.9 (niet in v0.7 of v0.8)
1. **Multi-locatie architectuur** — `Locatie` model, `Team.locatie_id`, `BaseRepository._locatie_filter()`
2. **GebruikerRol tabel** — vervangt `Gebruiker.rol` (enkelvoudig) door meervoudige, scopegebonden rollen
3. **NationaleHRRegel + LocatieHROverride** — twee-laagse HR-regels (v0.7 had één plat niveau)
4. **VerlofTeamStatus** — per-team status (v0.7 had één globale status per aanvraag)
5. **PlanningWijziging tabel** — audit log voor grid-bewerkingen met gedenormaliseerde `locatie_id`
6. **Notities mailboxhiërarchie** — rolgebonden mailboxes (planner/beheerder/super) ipv directe berichten
7. **Soft delete** — `verwijderd_op` + `verwijderd_door_id` op alle hoofdmodellen
8. **UUID voor API-paden** — integer intern, uuid extern (enumeration-preventie)

### Te porten vanuit v0.7 (businesslogica aanwezig, web-laag toevoegen)
9. **Alle 10 validators** — pure Python, minimale aanpassingen nodig
10. **Planning, verlof, rode lijn, shiftcodes, HR-regels** — repo's herschrijven voor SQLAlchemy
11. **ADV, typetabellen, schermrechten** — direct porten
12. **Logboek, rapporten, Excel-export** — direct porten
13. **Rotatie, suggesties, auto-scheduling** — direct porten

### Web-laag (nieuw — vervangt PyQt6 GUI)
14. **Rol-afhankelijk menu** — Jinja2 conditioneel op rollen
15. **Interactief dashboard** — HTMX-widgets, badges, 7-daagse preview
16. **Planning grid** — keyboard-navigatie via vanilla JS module
17. **Mobile-first** — consumptie-views op mobile, productie-views desktop-only
18. **PWA service worker** — offline fallback
19. **Docker Compose** — init-container Alembic patroon, productiedeploy op NAS

---

## Technologie stack (ongewijzigd t.o.v. v0.8)

| Component | Keuze |
|---|---|
| Backend | Python 3.12 + FastAPI 0.115 |
| ORM | SQLAlchemy 2.x + Alembic |
| Database | PostgreSQL 16 (Docker) |
| Frontend | HTMX 1.9 + Jinja2 + Tailwind CSS (CDN) |
| Auth | JWT httpOnly cookie + TOTP (pyotp) + **argon2-cffi** (wachtwoord hashing) |
| Deploy | Docker Compose op Synology NAS |
| Tunnel | Cloudflare Tunnel |

---

## Stijlsysteem (cross-cutting, opgezet in Fase 0)

### Light & Dark thema

Tailwind `darkMode: ['attribute', 'data-theme']` — het `data-theme="dark"` attribuut staat op `<html>`. Voorkeur opgeslagen in `Gebruiker.thema` (`light | dark | systeem`, default `systeem`). Een inline JS-snippet in `<head>` (vóór Tailwind laadt) zet het attribuut op basis van een cookie → geen flash bij laden.

**Twee CSS-systemen naast elkaar:**
- `stijlen.py` — Python-bestand dat dynamisch CSS custom properties genereert en via `{{ thema_css | safe }}` injecteert in de `<head>`. Gebruikt variabelenamen zónder prefix (`--primair`, `--achtergrond`, etc.) en dark mode via `[data-theme='dark']`.
- `static/css/theme.css` — statisch CSS-bestand, statische referentiedefinities met `--kleur-*` prefix en `html.dark`. Wordt gelinkt als stylesheet maar de semantische Tailwind-klassen verwijzen naar de `stijlen.py` variabelen.

De Tailwind semantische klassen verwijzen naar de variabelen van `stijlen.py`:

```python
# stijlen.py (selectie relevante variabelen):
LIGHT_KLEUREN = {
    "primair":            "#2563eb",
    "primair-hover":      "#1d4ed8",
    "achtergrond":        "#f1f5f9",
    "achtergrond-widget": "#ffffff",   # ← 'oppervlak' in Tailwind
    "tekst":              "#0f172a",
    "tekst-secundair":    "#64748b",   # ← 'tekst-zacht' in Tailwind
    "rand":               "#e2e8f0",
    "succes":             "#10b981",
    "fout":               "#ef4444",   # ← 'gevaar' in Tailwind
    "waarschuwing":       "#f59e0b",
    "info":               "#3b82f6",
    "msg-succes-bg":      "#d1fae5",   # ← 'succes-zacht' in Tailwind
    "msg-fout-bg":        "#fee2e2",   # ← 'gevaar-zacht' in Tailwind
    ...
}
# Dark mode via [data-theme='dark'] selector (niet html.dark)
```

Tailwind config (inline `<script>` vóór Tailwind CDN in `app.html`):
```js
tailwind = { config: {
  darkMode: ['attribute', 'data-theme'],
  theme: { extend: { colors: {
    'oppervlak':          'var(--achtergrond-widget)',
    'achtergrond':        'var(--achtergrond)',
    'primair':            'var(--primair)',
    'primair-hover':      'var(--primair-hover)',
    'tekst':              'var(--tekst)',
    'tekst-zacht':        'var(--tekst-secundair)',
    'rand':               'var(--rand)',
    'succes':             'var(--succes)',
    'succes-zacht':       'var(--msg-succes-bg)',
    'gevaar':             'var(--fout)',
    'gevaar-zacht':       'var(--msg-fout-bg)',
    'waarschuwing':       'var(--waarschuwing)',
    'waarschuwing-zacht': 'var(--msg-waarschuwing-bg)',
    'info':               'var(--info)',
    'info-zacht':         'var(--msg-info-bg)',
  }}}
} };
```

Templates gebruiken altijd **semantische klassen**, nooit hardcoded Tailwind-kleurcodes:
```html
<!-- ✅ correct -->
<div class="bg-oppervlak border border-rand text-tekst">
<button class="bg-primair hover:bg-primair-hover text-white">

<!-- ❌ fout — werkt niet in dark mode -->
<div class="bg-white text-gray-900">
```

Herbruikbare componenten in `templates/components/`: knoppen, kaarten, formuliervelden, badges, alerts — elk in één template snippet zodat stijl op één plek beheerd wordt.

### `Gebruiker.thema` veld

```python
class Gebruiker:
    ...
    thema: str  # 'light' | 'dark' | 'systeem' — default 'systeem'
```

`systeem` = volgt OS-voorkeur via `prefers-color-scheme` media query als fallback.

---

## i18n (verplicht vanaf dag 1)

v0.8 heeft nl/fr/en i18n. Regel voor v0.9:

> **Nooit hardcoded tekst in templates of Python-code.** Altijd via de vertaalfunctie.

```html
{# Templates #}
{{ _('verlof.aanvragen') }}
{{ _('fout.verplicht_veld', veld=_('gebruiker.naam')) }}
```

```python
# Python (foutmeldingen, domein)
from services.i18n import t
raise VerlofFout(t('verlof.overlap', taal=gebruiker.taal))
```

- Taalvoorkeur opgeslagen per gebruiker (`Gebruiker.taal`: `nl | fr | en`, default `nl`)
- Geen browser-header fallback — altijd de ingestelde taal van de gebruiker
- Nieuwe vertalingssleutels toevoegen in **alle drie** taalbestanden bij elke nieuwe feature
- Ontbrekende sleutel → fallback naar `nl`, nooit een crash

Structuur:
```
locales/
  nl/messages.json   ← standaard, altijd volledig
  fr/messages.json
  en/messages.json
```

---

## Architectuur (NON-NEGOTIABLE)

```
Router (api/routers/) — DUN: parse request, auth, call service, render template
    ↓
Service (services/) — Orchestratie: DB + domein logica
    ↓
Domein (services/domein/) — Pure Python, geen DB, geen service/model imports
Models (models/)          — SQLAlchemy ORM, geen businesslogica
```

Dependency regels:
- Routers → Services ✅ | Routers → Models ❌ | Routers → Domein ❌
- Services → Models ✅ | Services → Domein ✅ | Services → andere Services ❌
- Domein → Python stdlib ✅ | Domein → Models ❌ | Domein → Services ❌

---

## Data-isolatie: Tenant-leak preventie (NON-NEGOTIABLE)

Elke databasequery die locatiegebonden data ophaalt **moet** automatisch gefilterd worden op `locatie_id` van de ingelogde gebruiker. Dit wordt **niet** per service-functie geregeld, maar op één centraal niveau.

### BaseRepository

```python
# services/repository.py
class BaseRepository:
    def __init__(self, db: Session, locatie_id: int | None):
        self.db = db
        self.locatie_id = locatie_id  # None = super_beheerder (geen filter)

    def _locatie_filter(self, model):
        """Voeg automatisch WHERE locatie_id = :id toe, tenzij super_beheerder."""
        if self.locatie_id is not None:
            return model.locatie_id == self.locatie_id
        return True  # super_beheerder ziet alles
```

Alle concrete repositories erven van `BaseRepository` en roepen `_locatie_filter()` aan in elke query. Services instantiëren repositories altijd via de `locatie_id` van de ingelogde gebruiker (uit de JWT-context).

### Security middleware

FastAPI middleware valideert bij elke request:
1. JWT geldig en niet verlopen
2. `locatie_id` in JWT komt overeen met de resource die opgevraagd wordt
3. `super_beheerder` bypasses locatie-filter (bewust, gelogd in AuditLog)

```python
# api/middleware/locatie_guard.py
# Elke request die een :locatie_id of :team_id in het pad heeft,
# wordt gecontroleerd tegen de rollen van de ingelogde gebruiker.
```

**Regel:** Als een service-functie vergeten wordt te filteren, valt de app terug op de middleware als vangnet. Beide lagen zijn nodig.

---

## UI-snelheid & Keyboard Interactivity

### Stack: HTMX blijft — geen frontend framework

Vue of React toevoegen is een te grote architectuurwijziging. HTMX handelt server-side rendering; keyboard-interacties worden afgehandeld via een toegewijd vanilla JS-module.

### Planning grid keyboard module

```
static/js/planning-grid.js   ← dedicated module voor grid-interactie
```

Functionaliteiten:
- Pijltoetsen: cel-navigatie in het planninggrid
- `Enter` / `Escape`: cel bewerken / annuleren
- `Ctrl+C` / `Ctrl+V`: cel kopiëren / plakken (intercepted, niet browser-clipboard)
- `Ctrl+Shift+V`: Smart Copy — herhaalt laatste shift-patroon (v0.7-functie)
- `Delete`: cel leegmaken
- Muisklik + sleep: selecteer meerdere cellen

HTMX handelt de serverrounds af (opslaan, valideren). JS handelt de lokale grid-state af (selectie, clipboard, navigatie). Beide lagen zijn gescheiden.

### Optimistic UI

Voor snelle celbewerking:
1. JS past de cel direct visueel aan (optimistic update)
2. HTMX stuurt de wijziging naar de server op de achtergrond
3. Server-respons bevestigt of corrigeert (bij HR-validatiefout: cel teruggedraaid + foutmelding)

---

## Validator Performance

### Probleem

Bij batch-bewerkingen (planner past 30+ cellen tegelijk aan) moet de validator efficiënt werken. HR-regelcontext opnieuw laden per cel is onacceptabel.

### Oplossing

```python
# services/domein/validatie_context.py
class ValidatieContext:
    """Wordt éénmaal geladen per request/batch, niet per cel."""
    hr_regels: dict[str, int]   # code → effectieve waarde (override of nationaal)
    team_planning: dict         # gecachte planning van de betrokken periode
```

Werkwijze:
- **Enkelvoudige bewerking:** context inline laden, synchrone validatie, response < 200ms
- **Batch-bewerking (> 10 cellen):** context éénmaal laden, alle cellen valideren in één loop
- **Bulk-import (CSV/migratie):** background task via `asyncio` of FastAPI `BackgroundTasks`

HR-regelcontext wijzigt zelden → wordt gecached per locatie met invalidatie bij wijziging.

**Cache-sleutel bevat altijd `locatie_id`** — dit is verplicht in een multi-tenant omgeving:

```python
# ✅ correct — locatie-specifieke sleutel
cache_key = f"hr_regels_{locatie_id}"   # bijv. "hr_regels_101"

# ❌ fout — gedeelde sleutel, locatie A overschrijft locatie B
cache_key = "hr_regels"
```

**Cache-invalidator** — wordt getriggerd bij elke mutatie van HR-regels:

```python
# services/hr_service.py
def sla_locatie_override_op(locatie_id: int, ...):
    # ... opslaan in DB ...
    cache.delete(f"hr_regels_{locatie_id}")   # direct invalideren

# services/nationaal_hr_service.py
def sla_nationale_regel_op(...):
    # Nationale wijziging raakt ALLE locaties
    cache.delete_pattern("hr_regels_*")       # alle locatie-caches wissen
```

Invalidatieregels:
- Beheerder wijzigt lokale HR-override → cache van **die locatie** wissen
- Super_beheerder wijzigt nationale HR-regel → cache van **alle locaties** wissen (nationale default geldt voor iedereen zonder override)

---

## Mobile: Consumptie vs. Productie

### Formele split

| View | Doelgroep | Platform | Functionaliteit |
|---|---|---|---|
| **Consumptie-view** | Teamleden (120+) | Mobile-first | Eigen planning, verlof aanvragen, notities lezen, heatmap verlof |
| **Productie-view** | Planners, beheerders | Desktop only | Planning bewerken, grid-interactie, rapporten, admin |

### Regels

- Productie-views (`/planning`, `/admin/*`, `/rapporten`) tonen een melding op mobile: *"Deze pagina is beschikbaar op desktop."*
- Consumptie-views (`/mijn-planning`, `/verlof`, `/notities`, `/dashboard`) zijn volledig mobile-first
- `hr`-rol gebruikt de consumptie-view (read-only, past toch niets aan)

**Principe:** Probeer niet de volledige planningsinterface op een smartphonescherm te proppen. Mobile = consumptie. Desktop = productie.

---

## Secret Management

### Regels (direct uit security audit)

- **Nooit** wachtwoorden, tokens of sleutels in de code of git-history
- `.env` staat in `.gitignore` — altijd
- `.env.example` bevat placeholder-waarden en staat wél in git (documentatie)
- `requirements.txt` met **gepinde versies** (`pip freeze > requirements.txt`) na elke dependency-wijziging

### Productie (Docker Compose op NAS)

```yaml
# docker-compose.yml
services:
  app:
    env_file: .env          # buiten git, op NAS-volume
    secrets:
      - db_password
secrets:
  db_password:
    file: ./secrets/db_password.txt   # Docker Secrets, niet in env
```

Verplichte `.env`-variabelen:
```
SECRET_KEY=          # min. 32 willekeurige bytes, uniek per omgeving
POSTGRES_PASSWORD=   # sterk, uniek
POSTGRES_DB=
POSTGRES_USER=
ALLOWED_HOSTS=
TOTP_ISSUER=
```

### Wachtwoord hashing: argon2-cffi (vervangt passlib[bcrypt])

`passlib` ontvangt geen onderhoud meer sinds 2023 en is EOL. v0.9 gebruikt **argon2-cffi** rechtstreeks.

```
# requirements.txt
argon2-cffi>=23.1.0     # vervangt passlib[bcrypt]
# passlib en bcrypt worden NIET meer opgenomen
```

**Migratiestrategie voor bestaande bcrypt-hashes (v0.7-import):**

Bij eerste login na migratie detecteert de auth-service het hash-algoritme via het prefix:
- `$2b$` of `$2a$` → bcrypt (legacy) → verifieer, herhashen naar argon2 en opslaan
- `$argon2` → argon2 → direct verifiëren

Transparant voor de gebruiker; na eerste login heeft iedereen een argon2-hash.

```python
BCRYPT_PREFIXES = ("$2b$", "$2a$", "$2y$")

def verifieer_en_migreer(db, gebruiker, plain_password: str) -> bool:
    if gebruiker.wachtwoord_hash.startswith(BCRYPT_PREFIXES):
        if not bcrypt.checkpw(plain_password.encode(), gebruiker.wachtwoord_hash.encode()):
            return False
        gebruiker.wachtwoord_hash = argon2_hasher.hash(plain_password)
        db.commit()
        return True
    return argon2_hasher.verify(gebruiker.wachtwoord_hash, plain_password)
```

Bcrypt blijft als **read-only** dependency voor de migratieperiode.

**Concrete verwijderingsstrategie — trigger: 60 dagen na go-live:**

Je kan bestaande bcrypt-hashes niet proactief omzetten zonder de plaintext. Opties zijn wachten op login (onbepaald) of een geforceerde wachtwoordreset. Gekozen aanpak:

1. **60 dagen na go-live:** `scripts/bcrypt_audit.py` telt hoeveel accounts nog een bcrypt-hash hebben
   ```python
   # Hashes met bcrypt-prefix tellen:
   SELECT COUNT(*) FROM gebruikers WHERE wachtwoord_hash LIKE '$2%'
   ```
2. Als nog accounts met bcrypt-hash over zijn: **geforceerde wachtwoordreset** via e-mail voor die accounts (`moet_wachtwoord_wijzigen = True` flag op `Gebruiker`)
3. Zodra `COUNT = 0` bevestigd is: `bcrypt` verwijderen uit `requirements.txt`, `BCRYPT_PREFIXES`-pad verwijderen uit `AuthService`
4. Alembic-migratie: geen — puur code- en dependency-wijziging

**Maximale looptijd:** 60 dagen na go-live is bcrypt gegarandeerd weg, ongeacht hoeveel gebruikers ingelogd zijn.

### Checklist bij elke release

- [ ] `pip freeze > requirements.txt` bijgewerkt
- [ ] Geen secrets in git (`git log --all -S "password"`)
- [ ] Productie `.env` heeft andere `SECRET_KEY` dan development
- [ ] Geen `passlib` in requirements

---

## Fases

### Fase 0 — Projectsetup (Week 1)
**Doel:** Werkend FastAPI-geraamte op PostgreSQL, met stijlsysteem en i18n als fundament

**Basissetup:**
- [x] `backend/` map opbouwen: FastAPI-structuur gebaseerd op v0.8 patronen
- [x] `docker-compose.yml` aanmaken (app + PostgreSQL 16 + named volumes)
- [x] `.env.example` documenteren
- [x] Versie ophogen naar 0.9.0, nieuw CHANGELOG.md starten
- [x] Lokaal testen: `docker compose up --build`
- [x] Alembic migraties verifiëren
- [x] Alembic deployment-patroon instellen: **init-container** in `docker-compose.yml` voert `alembic upgrade head` uit vóór de app-container start (geen manuele stap, geen downtime-risico)

**Stijlsysteem:**
- [x] `backend/static/css/theme.css` aanmaken met CSS custom properties (light + dark, zie Stijlsysteem-sectie)
- [x] `backend/templates/layouts/app.html` aanpassen:
  - Inline `tailwind.config` script met semantische kleuraliassen (zie Stijlsysteem-sectie)
  - Theme-init snippet in `<head>` (zet `data-theme="dark"` op `<html>` vóór render op basis van cookie `thema`)
  - Tailwind CDN laden ná config
  - `theme.css` linken
- [x] `backend/templates/components/` map aanmaken met basiscomponenten:
  - `knop.html` (primair / secundair / gevaar variant)
  - `kaart.html`
  - `formulier_veld.html`
  - `badge.html`
  - `alert.html`
- [x] Theme-toggle knop in navbar (POST naar `/account/thema`, slaat op in `Gebruiker.thema`)
- [x] `Gebruiker.thema` veld toevoegen aan model (`light | dark | systeem`, default `systeem`) + Alembic migratie 002

**i18n controle:**
- [x] Bestaande v0.8 i18n-mechanisme verifiëren (werkt `t()` in templates? — ja, alle 14 routers geven `t` door; fallback nl→sleutel werkt)
- [x] Controleren of alle bestaande templates hardcoded tekst bevatten → inventariseren (22 van 28 pagina-templates bevatten nog hardcoded Dutch, wordt opgelost in Fase 1-6 bij template-herwerk)
- [x] Regel vastleggen in `CONTRIBUTING.md`: nooit hardcoded tekst, altijd vertaalsleutel

**Secrets & dependencies:**
- [x] `.env.example` aanmaken met alle verplichte variabelen (placeholder-waarden)
- [x] `.env` toevoegen aan `.gitignore`
- [x] `secrets/` map toevoegen aan `.gitignore`
- [x] `pip freeze > requirements.txt` uitvoeren na setup (sqlalchemy 2.0.48, pydantic 2.12.5 gepind)
- [x] Scannen van v0.8 code op hardcoded secrets → geen echte secrets gevonden (sentinel-string in config.py + seed-wachtwoord in main.py zijn bewust en acceptabel)
- [x] `passlib` verwijderen uit requirements, vervangen door `argon2-cffi` + `bcrypt` (read-only voor migratie)
- [x] `AuthService.verifieer_wachtwoord()` herschrijven met argon2 + bcrypt legacy-pad

**Verificatie:** `http://localhost:8000/health` → `{"status": "ok"}`, login werkt, light/dark toggle werkt, geen secrets in git

---

### Fase 1 — Hernoeming Groep → Team + Nieuw rolmodel (Week 2-3)
**Doel:** Correcte datamodel-fundament leggen vóór verdere ontwikkeling

**Dit moet als eerste — alle latere fases bouwen hierop.**

**Hernoeming Groep → Team:**
- [x] `models/groep.py` → `models/team.py`; `Groep` → `Team`, `GroepConfig` → `TeamConfig`
- [x] `models/locatie.py` aanmaken: `Locatie(id, naam, code, area_label, is_actief)`
- [x] `Team.locatie_id` FK toevoegen
- [x] Alle `groep_id` velden hernoemd naar `team_id` in: Planning, Notitie, AuditLog
- [x] `Verlof` verliest `groep_id` → aparte `VerlofTeamStatus`-tabel (zie datamodel)
- [x] Router `/groepen` → `/teams`; alle route-strings bijwerken
- [x] Templates: alle verwijzingen naar "groep" → "team"
- [x] i18n: `groep.*` → `team.*` sleutels

**Nieuwe operationele modellen (port vanuit v0.7):**
- [x] `Shiftcode` model uitbreiden met:
  - `locatie_id → Locatie` (nullable — None = nationaal beschikbaar)
  - `telt_als_werkdag: bool` — telt mee voor de 19-dagenregel
  - `is_nachtprestatie: bool` — activeert nacht-vervolgingsbeperking
  - `reset_nacht: bool` — heft nacht-vervolgingsbeperking op
  - Referentie: `code_v07/src/services/domein/shiftcode_domein.py`
- [x] `RodeLijnConfig` model aanmaken (exact één record):
  - `id, referentie_datum: date`
  - Rode lijn datums worden NOOIT opgeslagen, altijd berekend als `referentie_datum + n × 28`
  - Blokgrootte via `NationaleHRRegel(code='RODE_LIJN_BLOK_GROOTTE')`
  - Referentie: `code_v07/src/services/applicatie/rode_lijn_service.py`
- [x] `VerlofTeamStatus` model aanmaken: `(id, verlof_id, team_id, status, aangemaakt_op, behandeld_door_id, behandeld_op)`
- [x] `PlanningWijziging` model aanmaken met gedenormaliseerd `locatie_id` (via `Team.locatie_id` ingevuld bij aanmaak)

**Nieuw rolmodel (`GebruikerRol`):**
- [x] `Gebruiker.rol` veld verwijderen
- [x] `GebruikerGroep` tabel verwijderen
- [x] `models/gebruiker_rol.py` aanmaken:
  ```
  GebruikerRol(id, gebruiker_id, rol, scope_id, is_reserve, is_actief)
  rol: super_beheerder | beheerder | hr | planner | teamlid
  scope_id: team_id (teamlid/planner) | locatie_id (beheerder/hr) | nat_locatie_id (super_beheerder)
  is_reserve: bool (default False, enkel relevant bij rol=teamlid)
  ```
- [x] `heeft_rol(gebruiker_id, rollen, scope_id)` helper in `api/dependencies.py`
- [x] `heeft_rol_in_locatie(gebruiker_id, rollen, locatie_id)` helper in `api/dependencies.py`:
  - zoekt alle `GebruikerRol`-records voor de gebruiker
  - voor `teamlid/planner`: lookup `Team.locatie_id` via `scope_id` → vergelijk met `locatie_id`
  - voor `beheerder/hr`: vergelijk `scope_id` direct met `locatie_id`
  - voor `super_beheerder`: altijd `True`
  - **vereist in Fase 2 door HR-validators en locatie-gebaseerde permissiechecks**
- [x] `interpreteer_scope(rol, scope_id)` helper — geeft `('team', team_obj)` of `('locatie', locatie_obj)` terug (zie polymorfische FK-beslissing)
- [x] Alle router dependencies aanpassen: `vereiste_rol()` gebruikt nieuwe helpers
- [x] `GebruikerService` aanpassen: CRUD voor rollen toewijzen/intrekken
- [x] Planning grid query: enkel gebruikers met `teamlid|planner` voor dat team; `is_reserve` als uitfilterbare vlag

**Modelconventies toepassen:**
- [x] Alle hoofdmodellen uitbreiden met `verwijderd_op: datetime | None` en `verwijderd_door_id: int | None`
- [x] Alle via API blootgestelde modellen uitbreiden met `uuid: str` kolom (server-side uuid4, geïndexeerd)
- [x] `BaseRepository._locatie_filter()` filtert automatisch op `is_actief=True` en `verwijderd_op IS NULL`
- [x] API-routers gebruiken `uuid` in paden, services zoeken intern op `id`

**Alembic migratie:**
- [x] Migratie: hernoeming + Locatie + GebruikerRol + soft delete kolommen + uuid kolommen + PlanningWijziging + data migratie

**Seed data:**
- [x] Vaste systeemlocatie aanmaken: `Locatie(code='NAT', naam='Nationaal')` — nooit verwijderbaar
- [x] 1 echte Locatie + 2 Teams (PAT, TO)
- [x] Admin account: `super_beheerder` rol met `scope_id = id van Locatie(code='NAT')`

**Verificatie:** Login werkt, admin heeft super_beheerder-toegang, teams scherm toont correct, planning grid toont enkel teamleden

---

### Fase 2 — Nationale HR-regels + Locatie-overrides (Week 3)
**Doel:** Twee-laagse HR-regels: nationale defaults + strengere lokale overrides

**Referentie:** `code_v07/src/services/applicatie/hr_regel_beheer_service.py`

- [x] Model `NationaleHRRegel(id, code, waarde, ernst_niveau, richting, beschrijving, is_actief)`
  - `richting`: `"max"` (lagere waarde = strenger, bv. MAX_DAGEN_OP_RIJ) of `"min"` (hogere waarde = strenger, bv. MIN_RUSTTIJD)
- [x] Model `LocatieHROverride(id, nationale_regel_id, locatie_id, waarde)`
  - Constraint: `richting="max"` → `waarde <= nationale.waarde`; `richting="min"` → `waarde >= nationale.waarde`
- [x] Bestaande `HRRegel` model vervangen door bovenstaande
- [x] Alembic migratie (`002_hr_twee_laags.py`)
- [x] `HRService.haal_effectieve_waarde(regel_code, locatie_id)` → override indien aanwezig, anders nationaal
- [x] `ValidatieService`: validators gebruiken twee-laags lookup i.p.v. directe HRRegel query
- [x] Router `/beheer/hr-nationaal` (super_beheerder only): CRUD nationale defaults
- [x] Router `/hr` (beheerder): nationale defaults zien + lokale overrides instellen
- [x] Templates: nationale waarden tonen als referentie naast lokale invoer
- [x] Seed: nationale defaults
  - `MAX_DAGEN_OP_RIJ=7, MIN_RUSTTIJD=11, MAX_UREN_PER_WEEK=50`
  - `RX_MAX_GAP=7` (max dagen tussen RX-rustdagen)
  - `RODE_LIJN_BLOK_GROOTTE=1` (aantal aaneengesloten 28-daagse periodes per blok; override kan verlagen)
- [x] Seed: `RodeLijnConfig` aanmaken met nationale `referentie_datum` — via `migreer_sqlite.py` uit PAT.db (`rode_lijnen_config.start_datum = 2024-07-29`, interval=28)
- [x] Seed: v0.7 shiftcodes importeren met correcte flags — via `migreer_sqlite.py` (mapping: `reset_12u_rust→reset_nacht`, `shift_type='nacht'→is_nachtprestatie`)

**Verificatie:** Lokale override MAX_DAGEN_OP_RIJ=5 → validator gebruikt 5; locatie zonder override gebruikt 7; rode lijn datums correct berekend vanuit referentiedatum

---

### Fase 3 — Locatiebeheer + Notities herbouwen (Week 4)
**Doel:** Locaties beheerscherm voor super_beheerder; notities correct gescoopt per team

**Locatiebeheer (rollen zijn al aangemaakt in Fase 1):**
- [ ] Router `/beheer/locaties` (super_beheerder): locaties aanmaken/bewerken, beheerders toewijzen
- [ ] Router `/beheer/gebruikers` uitbreiden: rollen toewijzen UI (tabel: gebruiker → rollen + scopes)
- [ ] Menu: super_beheerder krijgt sectie "Nationaal Beheer"
- [ ] Gebruikersbeheer template: toon alle rollen van een gebruiker als badges (bv. "planner (PAT)", "teamlid (TO)")

**Notities herbouw (referentie: `code_v07/src/services/applicatie/notitie_service.py`):**
- [ ] `Notitie` model herbouwen met `naar_gebruiker_id` (nullable) + `naar_rol` + `naar_scope_id`
- [ ] Constraint: precies één van `(naar_gebruiker_id, naar_rol)` is ingevuld
- [ ] `NotitieService` herbouwen:
  - `stuur_naar_gebruiker(van, naar_gebruiker_id, bericht, prioriteit)`
  - `stuur_naar_mailbox(van, naar_rol, naar_scope_id, bericht, prioriteit)`
  - `haal_persoonlijke_inbox(gebruiker_id)` — direct ontvangen berichten
  - `haal_mailbox(naar_rol, naar_scope_id)` — gedeelde rolmailbox
  - `haal_alle_inboxen(gebruiker_id)` — alles per tab (persoonlijk + mailboxen obv rollen)
- [ ] Router `/notities`: tabs per mailbox die de gebruiker kan zien:
  - Tab "Inbox" (persoonlijke berichten)
  - Tab "Planners [Team X]" (als je planner bent van Team X)
  - Tab "Beheerders [Locatie Y]" (als je beheerder bent van Locatie Y)
  - Tab "Super_beheerders" (als je super_beheerder bent)
- [ ] Sturen: dropdown "Naar wie?" toont opties obv rol van afzender
- [ ] Badges in navbar: totaal ongelezen berichten over alle inboxen

**Verificatie:** Teamlid → planners mailbox PAT; planner → beheerders mailbox locatie; beheerder → super mailbox; tabs kloppen per rol; hr ziet geen mailbox-tabs (enkel leesrechten op planning)

---

### Fase 4 — Multi-team filtering planning (Week 5)
**Doel:** Planner filtert grid per team; teamlid ziet collega-shifts

- [ ] `PlanningService.haal_maand_grid(locatie_id, team_id=None)`
- [ ] Planning router: `?team_id=` queryparameter
- [ ] Planning grid template: team-filter dropdown (HTMX)
- [ ] Export per team: CSV/Excel met `team_id` filter
- [ ] `MijnPlanningService`: teamlid ziet collega-shifts van eigen team (read-only)
- [ ] Mijn Planning template: collega-selector gefilterd op team

**Verificatie:** Filter op "Team PAT" → enkel PAT-rijen; export correct; teamlid ziet collega-shifts

---

### Fase 5 — Rol-afhankelijk menu + Dashboard (Week 6-7)
**Doel:** Menu per rol; interactief dashboard

**Referentie:** `code_v07/src/gui/dashboard.py`, `code_v07/src/kern/scherm_registry.py`

- [ ] Menu in `templates/layouts/app.html` per rol:
  - `teamlid`: Dashboard, Mijn Planning, Verlof, Notities, Account
  - `planner`: + Planning, Verlof Beheer, Teams, HR, Rapporten
  - `hr`: Planning (read-only), Teams (read-only), Verlof (read-only)
  - `beheerder`: + Gebruikers, Teams, Locatie-instellingen, Logboek, Rechten
  - `super_beheerder`: + Nationaal Beheer (HR defaults, Locaties)
- [ ] Dashboard per rol:
  - **Teamlid:** 7-daagse eigen shifts preview, verlof saldo, snelkoppelingen
  - **Planner:** + verlofaanvragen teller, planner mailbox badge, HR warnings
  - **HR:** planning overzicht locatie (read-only tiles)
  - **Beheerder:** + logboek, jaar-overdracht trigger, team-overzicht
  - **Super_beheerder:** + locaties overzicht, nationale HR status
- [ ] HTMX widgets: badges polling, verlofteller per team
- [ ] 7-daagse preview component (partieel template)

**Verificatie:** Menu + dashboard correct per rol

---

### Fase 6 — Mobile-first Design (Week 8)
**Doel:** App bruikbaar op smartphone

- [ ] Navbar: hamburger menu (`sm:hidden` / `hidden sm:flex`)
- [ ] Dashboard: cards stacked (`grid-cols-1 md:grid-cols-2`)
- [ ] Planning grid: `overflow-x-auto`, compacte kolombreedte
- [ ] Mijn Planning: week-weergave op mobile
- [ ] Verlof formulier: touch-friendly (`py-3 px-4`)
- [ ] Notities: leesbaar op small screen
- [ ] Admin schermen: `hidden md:block`

| Feature | Mobile | Desktop |
|---|---|---|
| Mijn planning | ✅ Week-weergave | ✅ Maandgrid |
| Verlof aanvragen | ✅ | ✅ |
| Notities | ✅ | ✅ |
| Planning bewerken | ❌ | ✅ |
| Rapporten/export | ❌ | ✅ |
| Admin | ❌ | ✅ |

**Verificatie:** Kritieke functies bruikbaar op 375px breedte

---

### Fase 7 — Ontbrekende HR Validators (Week 9)
**Doel:** Volledige validator suite: alle 10 validators actief

**Bestaande v0.8 validators (al aanwezig, enkel `haal_effectieve_waarde()` aanpassen in Fase 2):**
- `MaxDagenOpRijValidator` — `code_v07/src/services/domein/validators/max_dagen_op_rij_validator.py`
- `MinRusttijdValidator` — `code_v07/src/services/domein/validators/min_rusttijd_validator.py`
- `MaxUrenPerWeekValidator` — `code_v07/src/services/domein/validators/max_uren_per_week_validator.py`
- `KrietiekeShiftValidator` — `code_v07/src/services/domein/validators/kritieke_shift_validator.py`
- `MaxWeekendsOpRijValidator` — `code_v07/src/services/domein/validators/max_weekends_op_rij_validator.py`
- `RXFDeadlineValidator` — `code_v07/src/services/domein/validators/rxf_deadline_validator.py`
- `RodeLijnValidator` (telt werkdagen in periode, was al aanwezig) — `code_v07/src/services/domein/validators/rode_lijn_validator.py`

**Nieuwe validators te porten:**
- [ ] `DubbeleShiftValidator` porten — `code_v07/src/services/domein/validators/dubbele_shift_validator.py`
  - Grid-niveau validator (geen gebruiker-id); detecteert kritieke shift die meerdere keren op dezelfde dag ingepland staat
  - Gebruikt `Shiftcode.is_kritisch` + `Shiftcode.dag_type`
- [ ] `RXGapValidator` porten — `code_v07/src/services/domein/validators/rx_gap_validator.py`
  - Max `RX_MAX_GAP` dagen tussen opeenvolgende RXW/RXF rustdagen (CXW telt NIET)
  - Lege cellen breken het segment (edge case: zie v0.7 implementatie)
  - Gebruikt `ValidatieContext` voor maandgrens-context (dagen sinds laatste RX vorige maand)
- [ ] `NachtshiftOpvolgingValidator` porten — `code_v07/src/services/domein/validators/nachtshift_opvolging_validator.py`
  - Na een shift met `is_nachtprestatie=True` mag de volgende shift pas als er een shift met `reset_nacht=True` tussenin staat
  - Gebruikt `Shiftcode.is_nachtprestatie` + `Shiftcode.reset_nacht` flags

**Bijhorende taken:**
- [ ] `ValidatieService` uitbreiden met de 3 nieuwe validators
- [ ] Unit tests: 100% coverage op alle nieuw geporteerde validators
- [ ] i18n: foutmeldingen in nl/fr/en voor `DUBBELE_SHIFT`, `RX_MAX_GAP`, `NACHT_OPVOLGING`

**Verificatie:** Dubbele kritieke shift, RX-gap en nachtshift-opvolging geven foutmelding in validatiepaneel; unit tests groen

---

### Fase 8 — Typetabellen & ADV Beheer (Week 10-11)
**Doel:** Configureerbare dropdowns en ADV-toekenning

**Referentie:** `code_v07/src/services/applicatie/typetabel_service.py`, `adv_service.py`

- [ ] Models `Typetabel` + `TypetabelEntry` (per locatie) + migratie
- [ ] `TypetabelService` porten; router `/typetabellen` (beheerder only)
- [ ] Models `AdvToekenning` + `AdvPatroon` + migratie
- [ ] `AdvService` porten; router `/verlof/adv`

**Verificatie:** Typetabellen beheerbaar, ADV werkt

---

### Fase 9 — Schermrechten, Rapporten & Logboek (Week 12)
**Doel:** Hybrid access control UI; volledigere rapportage

- [ ] Model `SchermRecht(route_naam, rol, locatie_id, toegestaan)` + migratie
- [ ] `SchermRechtenService` porten; router `/beheer/rechten` met toggle UI
- [ ] Logboek: filters datum/gebruiker/actie (HTMX)
- [ ] Uren rapport (shifts × uren per gebruiker per maand)
- [ ] Verlof overzicht maandgrid + capaciteitsrij
- [ ] Excel export verbeteren (HR-formaat)

**Verificatie:** Rechten aanpasbaar, logboek filterbaar, rapporten exporteerbaar

---

### Fase 10 — PWA & Afwerking (Week 13)

- [ ] Service Worker + Web App Manifest
- [ ] Changelog pagina correct renderen
- [ ] i18n volledigheidscheck (alle nieuwe strings in nl/fr/en)
- [ ] Dark mode verfijnen in nieuwe templates

---

### Fase 11 — Database Migratie & Go-Live (Week 14)
**Doel:** v0.7 data importeren, live op NAS

- [ ] `migreer_sqlite.py` uitbreiden:
  - PAT.db → Locatie + Team PAT (met team_id op alle records)
  - TO.db → Team TO (zelfde locatie)
  - Notities: `team_id` invullen, planner mailbox berichten correct mappen
- [ ] Migratietesten lokaal
- [ ] Deploy naar NAS (`/volume1/docker/planningtool/`)
- [ ] Cloudflare Tunnel voor v0.9
- [ ] Productie `.env` (unieke `SECRET_KEY`, sterke `POSTGRES_PASSWORD`)
- [ ] Gebruikersacceptatietests
- [ ] Datum noteren: **go-live datum + 60 dagen** = deadline bcrypt-verwijdering → taak inplannen

**Post-go-live (dag 60):**
- [ ] `scripts/bcrypt_audit.py` uitvoeren — tel resterende bcrypt-hashes
- [ ] Bij count > 0: geforceerde wachtwoordreset sturen naar betrokken accounts
- [ ] Zodra count = 0: `bcrypt` uit `requirements.txt` verwijderen, legacy-pad uit `AuthService` verwijderen

**Verificatie:** App bereikbaar via Cloudflare URL, PAT + TO data correct, notities per team

---

## Alembic Deployment Strategie

### Init-container patroon (geen manuele stap bij deploy)

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16
    ...

  migrate:                          # init-container — stopt na uitvoering
    build: ./backend
    command: alembic upgrade head
    env_file: .env
    depends_on:
      db:
        condition: service_healthy

  app:
    build: ./backend
    depends_on:
      migrate:
        condition: service_completed_successfully   # start pas na migratie
    ...
```

**Werkwijze bij elke deploy op de NAS:**
1. `docker compose pull` (nieuw image ophalen)
2. `docker compose up -d` — migrate-container draait automatisch vóór app
3. App start pas als migratie geslaagd is

**Rollback:** `alembic downgrade -1` via `docker compose run migrate alembic downgrade -1`, daarna `docker compose up -d` met het vorige image.

---

## Teststrategie

### Wat testen en wanneer

| Laag | Type | Wanneer schrijven |
|---|---|---|
| `services/domein/` | Unit tests | Samen met de code — pure Python, geen DB, geen framework |
| `services/` (services) | Integratietests | Na elke nieuwe service, met test-DB |
| `api/routers/` | HTTP-integratietests | Bij complexe flows (auth, CSRF, role checks) |
| Templates / UI | Manuele verificatie | Per fase, geen geautomatiseerde UI-tests |

### Prioriteit: domeinlaag

`services/domein/` is pure Python — geen SQLAlchemy, geen FastAPI, geen DB. Dit is het makkelijkst te testen én het meest kritisch (validators, berekeningslogica, HR-regels). Elke validator krijgt unit tests bij implementatie.

```
tests/
  domein/
    test_validators.py       # alle 10 HR-validators
    test_verlof_logica.py
    test_planning_berekeningen.py
  services/
    test_verlof_service.py   # integratietest met test-DB
    test_auth_service.py
  api/
    test_auth_routes.py      # login, TOTP, rate limiting
```

### Testregel per fase

Elke fase-verificatiestap bevat naast manuele checks ook:
- Domeinlaag: **unit tests vereist** vóór merge
- Services: integratietest voor kritieke paden
- Validators (Fase 7): 100% unit test coverage op alle 10 validators

---

## Security Checklist (elke nieuwe route)

- [ ] `vereiste_rol()` of `vereiste_login` dependency
- [ ] CSRF token op alle POST-formulieren (`{{ csrf_token }}`)
- [ ] `locatie_id` filter op alle queries (nooit cross-locatie); `team_id` voor planning-data
- [ ] `super_beheerder` bypasses locatie-filter (bewust, niet per ongeluk)
- [ ] Rate limiting op gevoelige endpoints
- [ ] `AuditLog` entry bij elke mutatieactie

---

## Kritieke referentiebestanden

| Bestand | Doel |
|---|---|
| **v0.7 — businesslogica (primaire bron)** | |
| `code_v07/src/services/applicatie/` | Alle 34 applicatieservices — port naar SQLAlchemy |
| `code_v07/src/services/domein/` | Alle 23 domeinbestanden — grotendeels direct hergebruiken |
| `code_v07/src/services/domein/validators/` | Alle 10 validators — grotendeels direct hergebruiken |
| `code_v07/src/services/repo/` | Alle 18 repositories — herschrijven voor SQLAlchemy 2.x |
| `code_v07/src/services/applicatie/planning_service.py` | Kern planning-logica |
| `code_v07/src/services/applicatie/verlof_service.py` | Verlof-logica (aanpassen voor VerlofTeamStatus) |
| `code_v07/src/services/applicatie/rode_lijn_service.py` | Rode lijn berekeningslogica (referentiedatum + n×28) |
| `code_v07/src/services/applicatie/hr_regel_beheer_service.py` | HR-regels (aanpassen voor twee-laags systeem) |
| `code_v07/src/services/applicatie/notitie_service.py` | Notities (herbouwen: mailboxhiërarchie) |
| `code_v07/src/services/domein/shiftcode_domein.py` | Shiftcode domein (telt_als_werkdag, is_nachtprestatie, reset_nacht) |
| `code_v07/src/gui/dashboard.py` | Dashboard features referentie (voor web-vertaling) |
| `code_v07/src/kern/scherm_registry.py` | Menu/rechten systeem referentie |
| **v0.8 — infrastructuurreferentie** | |
| `code_v08/backend/main.py` | FastAPI app-setup, lifespan, middleware-volgorde |
| `code_v08/backend/api/dependencies.py` | JWT-auth dependencies, rol-checks referentie |
| `code_v08/backend/database.py` | SQLAlchemy session-setup referentie |
| `code_v08/backend/` (Dockerfile, alembic.ini) | Docker + Alembic opzetpatronen |
| **Testdata** | |
| `docs/referentie/database.PAT.db` + `database.TO.db` | Testdata voor migratie |
| `docs/referentie/v0.7/database_schema.md` | Migratie referentie |

---

## Versie naamgeving

- Nieuwe map: `backend/` in root van Planningtool9
- Naam: "Planningtool v0.9"
- CHANGELOG.md: v0.9.0 als eerste entry
- v0.8 code blijft beschikbaar in `code_v08/` als referentie

---

## Toekomstbestendigheid (multi-locatie)

Architectuur ondersteunt:
- Nieuwe locaties aanmaken (super_beheerder)
- Per locatie eigen beheerder + teams
- HR-regels: nationale defaults gelden automatisch voor nieuwe locaties
- Area is enkel een label (`Locatie.area_label`) — geen apart databankobject nodig
