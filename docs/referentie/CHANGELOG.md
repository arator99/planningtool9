# Changelog — Planning Tool v0.8

Alle noemenswaardige wijzigingen in de web-migratie (FastAPI + PostgreSQL + Jinja2/HTMX).

Formaat gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.0.0/).

> **Testomgeving online:** [planningtool.org](https://planningtool.org)

---

## [0.9.1] — 2026-03-22

### Toegevoegd

-   **Team filter in gebruikersbeheer** — dropdown in de filterbalk om gebruikers te filteren op teamlidmaatschap
-   **Ledenkolom in teambeheer** — overzichtspagina toont direct de actieve leden per team als badges
-   **Ex-leden sectie in planningsgrid** — inklapbaar greyed-out paneel onderaan het grid; toont voormalige teamleden met hun historische shifts (read-only, geen nieuwe shifts mogelijk)
-   **Alembic migratie 009** — `verwijderd_op` en `verwijderd_door_id` kolommen op `gebruiker_rollen` tabel

### Gewijzigd

-   **Planningsgrid laadt shifts per medewerker** — query gebruikt `gebruiker_id` i.p.v. `team_id`, zodat de volledige shift-geschiedenis meebeweegt wanneer een medewerker van team wisselt
-   **`verwijder_lid` gebruikt soft delete** — `GebruikerRol.is_actief = False` + `verwijderd_op` + `verwijderd_door_id` i.p.v. fysiek verwijderen; historische shifts blijven zichtbaar voor het oude team

### Opgelost

-   **TOTP-setup 401 "niet ingelogd"** voor geïmporteerde gebruikers — `bevestig_totp_geforceerde_setup` gebruikte `Depends(verifieer_csrf)` wat een `toegangs_token` vereiste op een pre-auth route; vervangen door inline CSRF-check op basis van `gebruiker_id` uit `totp_setup_token`
-   **Planningsgrid team-filter crashte bij "alle teams"** — lege `team_id=` querystring kon niet als `int` worden geparsed; dropdown stuurt nu geen `team_id` parameter wanneer "alle teams" geselecteerd is

---

## [0.8.11] — 2026-03-15

### Toegevoegd

-   **CSRF-beveiliging** — synchronizer token pattern via `itsdangerous` op alle state-muterende POST-endpoints
-   **Rate limiting** — `slowapi` geactiveerd: 5 pogingen/minuut op login en TOTP-verificatie, 3/minuut op TOTP-instelling
-   **Security response headers** — `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy` (productie) via middleware
-   **Opstartcontrole** — applicatie weigert te starten als development-standaardsleutel in productie-omgeving wordt gebruikt
-   **JWT audience-claims** — `aud`-claim scheidt access tokens van TOTP-tussenstap tokens

### Gewijzigd

-   **Sessiecookies** — `secure` conditioneel op basis van omgeving, `samesite="strict"` op sessie- en TOTP-tokens
-   **Uvicorn** — geen `--reload` meer in productie; conditioneel opstartcommando in Dockerfile
-   **Inlogfoutmeldingen** — gedeactiveerde accounts geven dezelfde generieke foutmelding als ongeldig wachtwoord
-   **Verlof-router** — directe `db.query()` vervangen door `GebruikerService.haal_actieve_medewerkers()`
-   **Redirect-URLs** — vrije foutmeldingen vervangen door vaste foutcodes; echte fout wordt intern gelogd
-   **TOTP-instelpagina** — `Cache-Control: no-store` header toegevoegd
-   **Docker** — expliciete netwerk-isolatie (`intern` bridge); live volume-mount verplaatst naar `docker-compose.override.yml`

### Opgelost

-   Wachtwoord niet meer zichtbaar in applicatielog bij eerste opstart
-   `db.query()` rechtstreeks in verlof-router (architectuurschending) verholpen

---

## [0.8.12] — 2026-03-15

### Toegevoegd

-   **Multi-team ondersteuning via `GebruikerGroep` junction table**:
    -   Nieuw model `GebruikerGroep` — many-to-many koppeling tussen gebruiker en groep met `is_reserve` flag
    -   Gebruikers kunnen nu vast lid zijn van meerdere groepen, of als reserve worden gekoppeld
    -   Alembic migratie `001_gebruiker_groepen.py` — tabel aanmaken + automatisch populeren vanuit bestaande `gebruikers.groep_id`
-   **Groepenbeheer scherm** (`/groepen`, beheerder only):
    -   Overzicht van alle groepen
    -   Nieuwe groep aanmaken (naam, code, beschrijving)
    -   Ledenbeheer per groep: leden toevoegen, verwijderen, wissel vast ↔ reserve
-   **Reserves panel in planningsgrid** — uitschuifbaar panel onder de grid:
    -   Toont alle reservemedewerkers gekoppeld aan de actieve groep
    -   Per reserve: HTMX beschikbaarheidscheck over alle groepen (welke shifts zijn al gepland door een ander team?)
-   **Teamkoppelingen in gebruiker bewerken** — tabel per groep met koppelstatus (vast/reserve) en directe wissel/verwijder acties
-   **Navbar** — "Groepen" link toegevoegd in Beheer-dropdown (beheerder only)

### Gewijzigd

-   **`GebruikerService.haal_alle()`** en **`haal_actieve_medewerkers()`** — filteren nu via junction table (enkel niet-reserves van de groep)
-   **`GebruikerService.maak_aan()`** — maakt automatisch een `GebruikerGroep` record aan bij aanmaken van een gebruiker
-   **`PlanningService`-aanroep in planning router** — geeft `reserves` mee aan template context

### Nieuw (services)

-   `GebruikerService.haal_reserves(groep_id)` — reservemedewerkers voor een groep
-   `GebruikerService.haal_reserve_bezetting(gebruiker_id, datum_van, datum_tot)` — shifts van een reserve over alle groepen
-   `GET /planning/reserve/{id}/beschikbaarheid` — HTMX fragment met shifts per reserve per maand

---

## [Unreleased]

### Toegevoegd

-   **Database Beheer module** (`/beheer/database`, super_beheerder only):
    -   **Automatische backups** — dagelijks, wekelijks en maandelijks via `pg_dump` bij app-opstart; bewaarbeleid (30/12/12)
    -   **Handmatige backup** — aanmaken via GUI met optioneel label; download als `.dump`
    -   **Restore** — herstel vanuit bestaande backup of geüpload `.dump`-bestand; pre-restore backup wordt automatisch aangemaakt
    -   **JSON-export** — volledige database exporteren als `.json` (download)
    -   **Import/Merge** — upload een JSON-export van een andere instantie; voorvertoning toont hoeveel records nieuw zijn vs. al aanwezig; samenvoegen op UUID (bestaande records worden overgeslagen)
    -   Navbar-link en dashboard-tegel voor super_beheerder
-   **Migratiescript meerdere databases** (`scripts/migreer_sqlite_multi.py`):
    -   Verwerkt meerdere v0.7 SQLite-bestanden tegelijk (PAT + TO)
    -   Leidt locatie_code automatisch af uit bestandsnaam
    -   Werkposten deduplicatie op naam (case-insensitive)
    -   Shiftcodes zonder UUID krijgen deterministisch uuid5
    -   Robuuste ID-remapping — geen conflicten bij overlappende SQLite integer-IDs
-   **`BackupService`** — pg_dump/pg_restore wrapper met pre-restore backupbescherming
-   **`DatabaseExportService`** — SQLAlchemy → JSON serialisatie voor alle operationele tabellen
-   **`DatabaseImportService`** — JSON merge met uuid-gebaseerde conflictdetectie en voorvertoning
-   **`SqliteImportService`** — importeer een v0.7 SQLite `.db` bestand rechtstreeks via de GUI:
    -   Locatiecode automatisch afgeleid uit bestandsnaam (`database.PAT.db` → PAT)
    -   Voorvertoning toont per entiteitstype (teams, werkposten, shiftcodes, gebruikers, planning, verlof): totaal in bestand vs. nieuw te importeren
    -   Dezelfde conflict-strategie als JSON-merge: skip bestaande records op uuid/naam/gebruikersnaam
    -   Pre-import backup vóór uitvoering
    -   Endpoints: `POST /beheer/database/import/sqlite/voorvertoning` en `/uitvoeren`
    -   Import-tab uitgebreid met aparte upload-sectie voor `.db` bestanden
-   **i18n** — backup/restore/import/sqlite sleutels toegevoegd in nl/fr/en

### Gewijzigd

-   **Dockerfile** — `postgresql-client` toegevoegd (vereist voor `pg_dump`/`pg_restore` in app-container)
-   **docker-compose.yml** — `backup_data` volume toegevoegd, gemount op `/backups` in app-container

---

## Eerder gepland (verplaatst)

-   Fase 8: Typetabellen beheer
-   Fase 9: Geavanceerd beschikbaarheidsbeheer (ADV)

---

## [0.8.10] — 2026-03-15

### Toegevoegd

-   **Taalwisselaar in navbar** — nieuw item in de account dropdown om de taal te wijzigen:
    -   Native `<dialog>` met drie taalopties (🇳🇱 Nederlands, 🇫🇷 Français, 🇬🇧 English)
    -   Actieve taal gemarkeerd met vinkje en blauwe achtergrond
    -   Huidige taalcode zichtbaar als badge naast het menu-item
    -   `POST /account/taal` — slaat keuze op in `gebruiker.taal` en herlaadt pagina

### Gewijzigd

-   **Navbar volledig vertaald** — alle menukoppelingen, dropdown-items en tooltips via `t()`:
    -   Menukoppelingen: Dashboard, Planning, Verlof, Shiftcodes, HR Regels, Gebruikers, Rapporten, Notities
    -   Account dropdown: Wachtwoord wijzigen, 2FA instellen/beheren, Taal wijzigen, Uitloggen
    -   Help dropdown: Changelog
    -   Rolbadge in account dropdown via `t("rol.beheerder")` etc.
    -   Taal dialoog: titel, Annuleer, Opslaan
-   **Dashboard vertaald** — tegeltitels en omschrijvingen via `t()`, hardcoded kleuren vervangen door CSS custom properties

### Opgelost

-   `'t' is undefined` op dashboard na login — `main.py` gaf geen `t` mee aan template context
-   HTML-escaping van apostrof in Fransstalige login (`Nom d&#39;utilisateur`) — JS vertalingen worden nu als Python dict via `| tojson` doorgegeven in plaats van inline Jinja2 rendering

---

## [0.8.9] — 2026-03-15

### Toegevoegd

-   **Help menu met Changelog** — nieuw vraagteken-icoon in de navbar:
    -   Dropdown met link naar `/help/changelog`
    -   Changelog pagina rendert `CHANGELOG.md` als opgemaakt HTML via `markdown` library
    -   Stijlklasse `.changelog` voor koppen, lijsten, tabellen, code en blockquotes
-   `api/routers/help.py` — nieuwe router met `GET /help/changelog`
-   `markdown==3.7` toegevoegd aan `requirements.txt`

---

## [0.8.8] — 2026-03-15

### Toegevoegd

-   **Fase 2b: i18n infrastructuur** — meertalige ondersteuning voorbereid:
    -   Nieuwe map `i18n/` met `__init__.py` (`vertaal()`, `maak_vertaler()`), lazy loading + fallback naar Nederlands
    -   `i18n/nl.json` — master vertaalbestand (~100 sleutels over alle modules)
    -   `i18n/fr.json` + `i18n/en.json` — stubs, vallen terug op Nederlands tot vertaald
    -   Alle 8 routers: `t = maak_vertaler(gebruiker.taal)` beschikbaar in elke template via `_context()`
    -   Jinja2 global `t_global(sleutel, taal)` voor edge cases buiten request-context
    -   Sleutelstructuur: `nav.*`, `algemeen.*`, `status.*`, `verlof.*`, `planning.*`, `gebruiker.*`, `fout.*`
-   Bestaande templates nog niet gemigreerd — aparte pass na Fase 7

---

## [0.8.7] — 2026-03-15

### Toegevoegd

-   **Fase 2: Verlof Saldo & FIFO** — volledig saldo beheer systeem:
    -   Nieuwe DB tabellen: `verlof_saldi` (saldo per gebruiker per jaar) + `verlof_saldo_mutaties` (volledige audit trail)
    -   `services/domein/verlof_saldo_domein.py` — pure FIFO berekening, business rule constanten (`MAX_KD_OVERDRACHT=35`, `VV_VERVAL_MAAND=5`), validatie
    -   `services/verlof_saldo_service.py` — saldo ophalen/aanmaken, handmatige correcties, jaar overdracht, 1-mei verval
    -   Saldo panel in verlofformulier: toont VV + KD restant met FIFO detail (recht, overgedragen, opgenomen, in behandeling)
    -   1-mei waarschuwing in formulier als er nog overgedragen VV-dagen zijn vóór de vervaldatum
    -   Nieuw scherm `/verlof/saldo` voor behandelaars: overzicht alle medewerkers, correctie per medewerker (met audit trail), jaar overdracht knop, 1-mei verval knop
-   **Cloudflare Tunnel** — app bereikbaar via publiek domein zonder open poorten op ISP-niveau

### Business rules (FIFO verlof)

-   VV overdracht: alle resterende dagen worden overgedragen naar volgend jaar
-   VV verval: overgedragen dagen vervallen op 1 mei
-   KD overdracht: maximaal 35 dagen, rest vervalt
-   Negatief saldo: wordt afgetrokken van het totaal van volgend jaar
-   FIFO: opgenomen en aangevraagde dagen worden eerst verrekend met de overgedragen pot

---

## [0.8.6] — 2026-03-14

### Gewijzigd

-   **3-laags architectuur volledig ingevoerd** — strikte scheiding Router / Service / Domein:
    -   Nieuwe map `services/domein/` aangemaakt als "Domeinlaag": pure Python, geen SQLAlchemy
    -   9 domeinmodules geëxtraheerd uit de bestaande services:
        -   `planning_domein.py` — `SHIFT_TYPE_CONFIG`, `MAAND_NAMEN`, `DAG_NAMEN`, `RUST_CODES`, `STANDBY_CODES` + `bouw_dag_info()`, `bereken_navigatie()`, `groepeer_shiftcodes()`
        -   `auth_domein.py` — `hash_wachtwoord()`, `verifieer_wachtwoord()`, `valideer_wachtwoord_sterkte()`, JWT token functies
        -   `gebruiker_domein.py` — `GEBRUIKERSNAAM_PATROON`, `valideer_gebruikersnaam_formaat()`
        -   `verlof_domein.py` — `BEHANDELAAR_ROLLEN`, `valideer_verlof_periode()`, `bereken_verlof_dagen()`
        -   `validatie_domein.py` — `ValidatieFout`, 6 shifthelpers, 7 validators als pure functies, `VALIDATORS` register
        -   `rapport_domein.py` — `bouw_csv_inhoud()`, `groepeer_verlof_per_medewerker()`
        -   `shiftcode_domein.py` — `SHIFT_TYPES`, `DAG_TYPES`, `normaliseer_shiftcode()`
        -   `hr_domein.py` — `ERNST_NIVEAUS`, `valideer_ernst_niveau()`, `valideer_interval_dagen()`
        -   `notitie_domein.py` — `PRIORITEITEN`, `valideer_bericht()`, `valideer_prioriteit()`
    -   Alle 8 services bijgewerkt: importeren nu hun constanten en hulpfuncties uit de domeinlaag
    -   `validatie_service.py` geslonken van 619 naar ~160 regels — validators verhuisd naar domeinlaag

### Opgelost

-   **Duplicate code geëlimineerd**: `_valideer_wachtwoord_sterkte` bestond in zowel `auth_service.py` als `gebruiker_service.py` met subtiel verschillende implementaties → geünificeerd in `auth_domein.py`
-   **Cross-service import opgelost**: `rapport_service.py` importeerde `MAAND_NAMEN` en `DAG_NAMEN` rechtstreeks uit `planning_service.py` (verboden koppeling tussen services) → beide importeren nu uit `planning_domein.py`

---

## [0.8.5] — 2026-03-14

### Toegevoegd

-   **HR Validatie Engine (Fase 1)** — kern van de planning tool:
    -   `services/validatie_service.py`: 7 validators op basis van arbeidstijdregels
        -   `_kritieke_shifts` — CRITICAL als een kritieke shiftcode onbezet is
        -   `_max_dagen_op_rij` — waarschuwing bij > N aaneengesloten werkdagen
        -   `_nachtshift_opvolging` — CRITICAL bij vroege/dag shift direct na nachtshift
        -   `_max_weekends_op_rij` — waarschuwing bij > N weekenden op rij gewerkt
        -   `_rode_lijn` — overtredingen per rode lijn cyclus (configureerbaar interval)
        -   `_max_uren_week` — waarschuwing bij > N werkuren in een kalenderweek
        -   `_min_rusttijd` — CRITICAL bij < N uur rust tussen twee shifts
    -   `ValidatieFout` dataclass met: `gebruiker_id`, `datum`, `validator_code`, `ernst`, `bericht`, `heeft_override`
    -   14 dagen lookback-venster voor cross-maand detectie (bijv. 6 werkdagen in maart + 2 in april)
    -   HR regelwaarden worden uit de database geladen (configureerbaar per groep via `HRRegel` tabel)
    -   `ValidatieService.maak_override()` — slaat planneroverride op via bestaand `PlanningOverride` model
-   **`GET /planning/valideer`** — HTMX endpoint dat validatie uitvoert en fragment terugstuurt
-   **`POST /planning/override`** — slaat afwijkingsreden op, hervalideert en stuurt bijgewerkt paneel terug
-   **`templates/pages/planning/_validatie_paneel.html`** — HTMX fragment:
    -   Groen "geen overtredingen" banner indien schoon
    -   Kleur-coded overtredingenlijst (rood = CRITICAL, oranje = WARNING, blauw = INFO)
    -   Badge-tellers per ernst in de samenvatting
    -   "Afwijking toestaan" knop bij CRITICAL fouten → native `<dialog>` met redenformulier
    -   Goedgekeurde overrides worden grijs doorgestreept weergegeven
    -   JavaScript markeert de bijbehorende planning-cellen in de grid
-   **Planningsgrid uitgebreid** (`templates/pages/planning/maand.html`):
    -   "Valideer" knop in de toolbar met HTMX GET en laad-spinner
    -   `#validatie-paneel` div onder de planningtabel
    -   CSS cel-markers: rode/oranje/blauwe outline per ernst (`.cel-kritiek`, `.cel-waarschuwing`, `.cel-info`)

### Opgelost

-   Bug in `_kritieke_shifts`: dubbele `dag + timedelta(days=1)` binnen inner loop veroorzaakte dag-skip

---

## [0.8.4] — 2026-03-13

### Toegevoegd

-   **Account dropdown menu** (`templates/layouts/app.html`):
    -   Ingelogde gebruikersnaam als klikbare trigger (vervangen door dropdown-knop)
    -   Dropdown bevat: gebruikersnaam/groep header, wachtwoord wijzigen, 2FA instellen/beheren, uitloggen
    -   Click-outside-to-close handler via JavaScript
-   **Wachtwoord wijzigen** (`api/routers/account.py`, `templates/pages/account/wachtwoord.html`):
    -   `GET /account/wachtwoord` — formulier
    -   `POST /account/wachtwoord` — verifieert huidig wachtwoord, valideert sterkte, slaat nieuw hash op
    -   Client-side wachtwoordsterktemeter (zwak/matig/goed/sterk kleurenbalk)
    -   Client-side match-controle bij bevestigingsveld
    -   2FA-statusblok onderaan (met link naar instellen indien niet actief)
-   `AuthService.wijzig_wachtwoord()` — valideert huidig wachtwoord en nieuwe sterkte
-   `AuthService._valideer_wachtwoord_sterkte()` — controleert min. 8 tekens, hoofdletter, kleine letter, cijfer, speciaal teken
-   **Rapportenmodule** (`api/routers/rapporten.py`, `templates/pages/rapporten/index.html`):
    -   `GET /rapporten` — maandoverzicht read-only + verlofoverzicht per jaar
    -   `GET /rapporten/maandplanning/csv` — CSV export met UTF-8-SIG (BOM) voor Excel-compatibiliteit
    -   Afdrukstijl via `@media print` (navbar verborgen)
    -   Toegang voor: beheerder, planner, hr
-   **Notitiesmodule** (`api/routers/notities.py`, `templates/pages/notities/lijst.html`):
    -   Inbox/verzonden tabbladen met ongelezen badge
    -   "Alles gelezen" markeerknop
    -   Nieuw bericht sturen via inline dialog
    -   URL-parameter `?tab=verzonden` schakelt automatisch naar het juiste tabblad

### Gewijzigd

-   Dashboard (`templates/pages/dashboard.html`): Rapporten- en Notitiestegel geactiveerd
-   Navbar: Rapporten (beheerder/planner/hr) en Notities (iedereen) toegevoegd als navigatielinks

---

## [0.8.3] — 2026-03-12

### Toegevoegd

-   **HR Regels** (`api/routers/hr.py`, `templates/pages/hr/`):
    -   Configuratie van HR-regelwaarden per groep via de interface
    -   Rode lijn instelling (max werkdagen per cyclus)
    -   Toegang voor: beheerder, hr
-   **Shiftcodes beheer** (`api/routers/shiftcodes.py`, `templates/pages/shiftcodes/`):
    -   CRUD voor shiftcodes (code, tijden, shift_type, is_kritisch)
    -   Floating HUD op de planningpagina (sleepbaar, per categorie gekleurd)

---

## [0.8.2] — 2026-03-11

### Toegevoegd

-   **Planningsgrid** (`api/routers/planning.py`, `templates/pages/planning/maand.html`):
    -   Maandgrid met inline bewerkbare cellen (HTMX UPSERT bij `change`-event)
    -   Toetsenbordnavigatie: pijltjestoetsen, Tab, Enter
    -   Concept/gepubliceerd statusbeheer met publiceer/concept-terugzet knoppen
    -   Shiftcode HUD (floating, kleur per categorie, sleepbaar)
-   **Verlofmodule** (`api/routers/verlof.py`, `templates/pages/verlof/`):
    -   Verlof aanvragen, goedkeuren, weigeren
    -   Overzicht per medewerker en per maand

---

## [0.8.1] — 2026-03-10

### Toegevoegd

-   **Gebruikersbeheer** (`api/routers/gebruikers.py`, `templates/pages/gebruikers/`):
    -   CRUD: lijst, aanmaken, bewerken, deactiveren
    -   Wachtwoord reset door beheerder
    -   Rollen: beheerder, planner, hr, medewerker
-   **Auth** (`api/routers/auth.py`):
    -   Login met JWT (cookie-based)
    -   TOTP 2FA instellen en verifiëren
    -   Uitloggen

---

## [0.8.0] — 2026-03-09

### Toegevoegd

-   Initiële projectstructuur voor v0.8 web-migratie
-   FastAPI applicatie met Jinja2 templates en HTMX
-   PostgreSQL via SQLAlchemy ORM (multi-tenant via `groep_id`)
-   Docker Compose setup (`docker-compose.yml`, `backend/Dockerfile`)
-   Database migrations via Alembic
-   Light/dark theming via CSS custom properties
-   Seed: testgroep + beheerdersaccount bij lege database
-   Basismodellen: `Groep`, `GroepConfig`, `Gebruiker`, `Planning`, `Shiftcode`, `VerlofAanvraag`, `HRRegel`, `RodeLijn`, `Notitie`, `PlanningOverride`, `SpecialCode`
-   MigratieScript `scripts/migreer_sqlite.py` voor overzetten van v0.7 SQLite data