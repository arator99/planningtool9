# Changelog — Planningtool

Alle noemenswaardige wijzigingen worden hier bijgehouden.
Formaat gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.0.0/).

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
- Notities mailboxhiërarchie: teamlid → planners → beheerders → super_beheerders
- Planner kan verlof indienen namens teamlid (`ingediend_door_id` + verplichte `reden_namens`)
- Light/dark thema via CSS custom properties (`static/css/theme.css`); voorkeur per gebruiker
- Herbruikbare UI-componenten: `knop.html`, `kaart.html`, `formulier_veld.html`, `badge.html`, `alert.html`
- Mobile-first responsive design; consumptie-views (dashboard, verlof, notities) op mobile
- `BaseRepository._locatie_filter()`: automatische tenant-isolatie op alle queries
- `heeft_rol()`, `heeft_rol_in_locatie()`, `interpreteer_scope()` helpers voor permissiechecks
- Soft delete op alle hoofdmodellen: `verwijderd_op` + `verwijderd_door_id`
- UUID-kolom op alle via API blootgestelde modellen; API-paden gebruiken uuid (nooit integer)
- Vaste systeemlocatie `Locatie(code='NAT', naam='Nationaal')` — aangemaakt bij init, nooit verwijderbaar
- Keyboard-navigatie planninggrid: pijltoetsen, Enter/Escape, Ctrl+C/V, Ctrl+Shift+V (smart copy), Delete
- Optimistic UI voor celbewerking: visuele update direct, servervalidatie op achtergrond

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
