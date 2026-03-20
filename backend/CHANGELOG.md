# Changelog — Planningtool

Alle noemenswaardige wijzigingen worden hier bijgehouden.
Formaat gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.0.0/).

---

## [0.9.1] — In ontwikkeling

### Nieuw
- Locatiebeheer voor super_beheerder: gebruikers toewijzen aan een locatie via het bewerkformulier
- Locatie context switcher in de navbar: super_beheerder kan via een dropdown wisselen tussen locaties zonder van rol te wisselen; context wordt opgeslagen in een cookie (`locatie_context`)
- Gebruikersbeheer en teamsbeheer respeiteren de actieve locatiecontext (`haal_actieve_locatie_id` dependency)
- `scripts/maak_super_beheerder.py`: bootstrap-script om een gebruiker tot super_beheerder te promoveren
- Aankondigingensysteem: super_beheerder kan systeemberichten aanmaken (gepland onderhoud, updates, ...) die als banner of dialoogbox verschijnen bij alle ingelogde gebruikers; beheerbaar via `/beheer/aankondigingen` in het menu Nationaal Beheer; ondersteuning voor tijdvensters (zichtbaar van/tot), ernstniveaus (info/waarschuwing/kritiek) en direct activeren/deactiveren

### Opgelost
- Aankondigingenbanner werd niet weergegeven: de HTMX-partial miste de `t()` vertaalfunctie in zijn template-context, waardoor sjabloonteksten niet konden worden opgezocht
- Activeren/deactiveren van aankondiging gaf internal server error: `zet_actief()` logde nog `obj.titel` na hernoem naar `obj.sjabloon`
- Formulier "Gebruiker bewerken" werd nooit opgeslagen: geneste `<form>` elementen (teamkoppelingen) verbraken de buitenste form; teamkoppelingen-sectie verplaatst naar buiten `</form>`
- Super_beheerder kon gebruikersbeheer niet bereiken: routes vereisten `beheerder` of `planner`, niet `super_beheerder`; alle gebruikersbeheer-routes omgezet naar `vereiste_beheerder_of_hoger`
- Cross-locatie bewerken mislukte: `bewerk()` gebruikte `gebruiker.locatie_id` (NAT) voor de opzoeking, nu `bewerkt.locatie_id`
- Bij locatieverplaatsing bleef `GebruikerRol.scope_id` van beheerder/hr-rollen wijzen naar de oude locatie; `bewerk()` updatet nu ook de scope van locatie-gebonden rollen mee
- NAT-locatie ontbrak in de locatie-switcher dropdown: `LocatieService.haal_alle()` sluit NAT bewust uit; switcher queryet nu direct inclusief NAT

### Gewijzigd
- Rolkeuze in gebruikersformulier: "gebruiker" vervangen door "teamlid" (correct rolnaam)
- Hardcoded Tailwind-kleurcodes (`text-blue-600`, `focus:ring-blue-500`) in gebruikersformulier vervangen door semantische klassen

---

## [0.9.0] — In ontwikkeling

### Strategie
v0.7 Python-businesslogica (services, domein, validators) geport naar FastAPI/PostgreSQL.
v0.8 dient als infrastructuurreferentie (Docker, Alembic, JWT-auth).

### Nieuw
- Multi-locatie architectuur: `Nationaal → Area (label) → Locatie → Team → Gebruiker`
- `GebruikerRol` tabel: rollen zijn meervoudig, scopegebonden en niet-hiërarchisch
  - Rollen: `super_beheerder | beheerder | hr | planner | teamlid`
  - `is_reserve` vlag op teamlid-rol (uitfilterbaar in planninggrid)
- `VerlofTeamStatus`: per-team verlofstatus (`aangevraagd | goedgekeurd | geweigerd`)
- `PlanningWijziging`: audit log voor gridwijzigingen met gedenormaliseerde `locatie_id`
- Twee-laagse HR-regels: `NationaleHRRegel` + `LocatieHROverride` (locatie kan enkel verstrengen)
- `RodeLijnConfig`: één nationaal record met `referentie_datum`; cyclussen berekend als `n × 28 dagen`
- `Shiftcode.telt_als_werkdag`, `is_nachtprestatie`, `reset_nacht` flags
- Blokgrootte rode lijn configureerbaar via `NationaleHRRegel(code='RODE_LIJN_BLOK_GROOTTE')`
- Notities mailboxhiërarchie: teamlid → planners → beheerders → super_beheerders; `naar_rol` + `naar_scope_id` vervangt `team_id`
- Locatiebeheer router `/beheer/locaties` (super_beheerder only): CRUD via UUID
- `LocatieService`: haal_alle, maak_aan, bewerk, deactiveer
- Gebruikerslijst toont rollen als gekleurde badges met scope-code
- Planner kan verlof indienen namens teamlid (`ingediend_door_id` + verplichte `reden_namens`)
- Light/dark thema via CSS custom properties; voorkeur per gebruiker
- **CSS build-pipeline**: Tailwind CLI (standalone binary, geen npm/node) genereert `static/css/output.css` tijdens Docker build — geen CDN, geen runtime JS-parser, geen SyntaxError-risico
- Herbruikbare UI-componenten: `knop.html`, `kaart.html`, `formulier_veld.html`, `badge.html`, `alert.html`
- Mobile-first responsive design; consumptie-views (dashboard, verlof, notities) op mobile
- `BaseRepository._locatie_filter()`: automatische tenant-isolatie op alle queries
- `heeft_rol()`, `heeft_rol_in_locatie()`, `interpreteer_scope()` helpers voor permissiechecks
- Soft delete op alle hoofdmodellen: `verwijderd_op` + `verwijderd_door_id`
- UUID-kolom op alle via API blootgestelde modellen; API-paden gebruiken uuid (nooit integer)
- Vaste systeemlocatie `Locatie(code='NAT', naam='Nationaal')` — aangemaakt bij init, nooit verwijderbaar
- Keyboard-navigatie planninggrid: pijltoetsen, Enter/Escape, Ctrl+C/V, Ctrl+Shift+V (smart copy), Delete
- Optimistic UI voor celbewerking: visuele update direct, servervalidatie op achtergrond
- Typetabellen beheer: configureerbare shift-roostertemplates per locatie (CRUD + grid editor + activeren)
- ADV-toekenningen: dag-van-week patronen per medewerker met optioneel einddatum
- `SchermRecht` model: hybrid access control — DB-overrides per (route, rol, locatie) overschrijven hardcoded defaults
- Schermrechten-matrix UI (`/beheer/rechten`): toggle per rol per route, reset naar standaard
- Logboek filteerbaar op datum-range, gebruiker en actie (HTMX, geen page reload)
- Urenrapport (`/rapporten/uren`): shifts × shift-duur per medewerker per maand
- Verlof maandgrid (`/rapporten/verlof-maandgrid`): per-dag capaciteitsrij (groen/amber/rood)
- PWA: Service Worker (cache-first statisch, network-first navigatie, network-only API) + Web App Manifest
- Offline fallback pagina (`/offline`) — geen auth vereist, standalone HTML
- i18n volledigheidscheck: nl/fr/en nu volledig synchroon (alle sleutels aanwezig in alle taalbestanden)
- `migreer_sqlite.py` uitgebreid: Gebruikers + GebruikerRol, Planning, VerlofAanvraag + VerlofTeamStatus, VerlofSaldo, Notities
- `scripts/bcrypt_audit.py`: hulpscript voor post-go-live controle van resterende bcrypt-hashes

### Gewijzigd
- `Groep` hernoemd naar `Team` overal (code, DB, templates, i18n, routes)
- `groep_id` → `team_id` in Planning, Notitie, Shiftcode, AuditLog
- `Verlof` verliest `groep_id`; status per team via `VerlofTeamStatus`
- Wachtwoord hashing: `passlib` (EOL) vervangen door `argon2-cffi`; bcrypt als read-only legacy-pad
- `Gebruiker.thema`: hernoemd van `theme_voorkeur`, default gewijzigd van `light` naar `systeem`
- Dashboard interactiever en rol-afhankelijk per rol
- Menu conditioneel per rol
- HR-validators lezen `haal_effectieve_waarde(regel_code, locatie_id)` i.p.v. directe HRRegel-lookup
- `ValidatieContext` wordt éénmaal geladen per batch, niet per cel

### Verwijderd
- `Gebruiker.rol` enkelvoudig veld (vervangen door `GebruikerRol`)
- `GebruikerGroep` tabel (vervangen door `GebruikerRol` met `is_reserve` vlag)
- `passlib` dependency (EOL)
- Legacy `backend/api/routers/groepen.py` en `backend/models/groep.py` verwijderd

### Security
- **XSS** — Changelog HTML gesaniteerd met `bleach` vóór `| safe` rendering (`help.py`)
- **Cookie expiry** — `max_age` toegevoegd aan `toegangs_token` cookie (gelijk aan JWT-verlooptijd)
- **HSTS** — `Strict-Transport-Security: max-age=31536000; includeSubDomains` in productie
- **Rate limiting** — Rate limiter leest `CF-Connecting-IP` voor correct IP achter Cloudflare Tunnel
- **Health endpoint** — Versie en omgeving alleen zichtbaar in development, niet in productie
- **Seed** — Productieguard toegevoegd aan `seed_test_data()`; seed-wachtwoord via `SEED_ADMIN_WACHTWOORD` env var
- **Override API** — `/planning/override` gebruikt UUID i.p.v. integer ID; team-membership check toegevoegd
- **TOTP setup** — Foutantwoord bij onjuiste TOTP-code bevat nu CSRF-token en hergenereert het geheim niet

---

## [0.8.0] — 2026

Eerste webversie. FastAPI + PostgreSQL + HTMX als vervanging voor de PyQt6 desktopapp.

### Nieuw
- FastAPI 0.115 backend met 3-laags architectuur (Router → Service → Domein)
- PostgreSQL 16 via Docker; Alembic voor migraties
- HTMX 1.9 + Jinja2 + Tailwind CSS frontend
- JWT httpOnly cookie authenticatie + TOTP 2FA (pyotp)
- CSRF synchronizer tokens op alle POST-formulieren
- Rate limiting via slowapi
- i18n nl/fr/en via JSON locale-bestanden
- Planninggrid (maandweergave), verlof, notities, gebruikersbeheer
- `Groep`-model als planningseenheid (hernoemd naar `Team` in v0.9)
- SQLite → PostgreSQL migratiedienst (`scripts/migreer_sqlite.py`)

### Beperkingen (opgelost in v0.9)
- Businesslogica minder volledig dan v0.7 (miste validators, rode lijn, ADV, typetabellen, ...)
- `Groep`-model architecturaal onduidelijk; geen locatieniveau
- `Gebruiker.rol` enkelvoudig — geen meervoudige scoped rollen
- Notities niet correct gescoopt per team
- Geen mobile support
- Geen multi-locatie ondersteuning

---

## [0.7.51] — 2026 (live)

Laatste versie van de PyQt6 desktopapp. Live in productie op 2 teams (PAT + TO), aparte SQLite databases.

### Functies
- Volledig planninggrid met keyboard-navigatie, smart copy, celvalidatie
- Verlof: aanvragen, goedkeuren, weigeren, saldo bijhouden, ADV-patronen
- 10 HR-validators: max dagen op rij, min rusttijd, max uren/week, max weekends op rij,
  kritieke shift, RXF-deadline, rode lijn (19-dagenregel), RX-gap, dubbele shift, nachtshift-opvolging
- Rode lijnen: 28-daagse arbeidscyclus met referentiedatum, visuele markering in grid
- Shiftcodes met `telt_als_werkdag`, `is_nachtprestatie`, `reset_nacht` flags
- Notities en interne mailbox (planner per team)
- Teams en gebruikersbeheer
- Typetabellen: configureerbare dropdowns per groep
- Schermrechten: hybrid access control per rol configureerbaar
- Logboek: audit trail van alle mutaties
- Rapporten en Excel-export
- Rotatie-suggesties en auto-scheduling
- TOTP 2FA authenticatie
- SQLite database (per team aparte .db-file)
- nl/fr/en vertalingen

### Beperkingen (opgelost in v0.9)
- PyQt6 desktopapp — niet toegankelijk via browser
- Aparte SQLite per team — geen centrale database, geen multi-locatie
- Enkelvoudige rol per gebruiker
- Geen mobile support
